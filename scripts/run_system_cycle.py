"""Run a mock-only circuit traversal or closed-loop solve and archive diagnostics.

Exit 0: single-pass evaluated OR closed-loop converged; 1: solve/evaluation failure;
2: invalid input or I/O failure. No database, GUI, optimizer or implicit retry.
"""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from pydantic import ValidationError

from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.solvers.system_cycle import (
    CircuitResult,
    ConvergenceRequest,
    ConvergenceResult,
    SyntheticScenario,
    evaluate_circuit,
    solve_circuit,
)
from agent_hvac.solvers.system_cycle.operating_map import (
    OperatingMapRequest,
    OperatingMapResult,
    operating_map_csv,
    solve_operating_map,
)
from agent_hvac.solvers.system_cycle.room_sizing import (
    RoomSizingRequest,
    RoomSizingResult,
    size_room_cooling,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("single-pass", "closed-loop", "map", "room-sizing"),
        default="single-pass",
    )
    parser.add_argument(
        "--csv", type=Path, help="Optional map summary; JSON retains full histories"
    )
    args = parser.parse_args()
    try:
        if args.input.resolve() == args.output.resolve():
            raise ValueError("output must differ from input")
        if args.csv is not None:
            if args.mode != "map":
                raise ValueError("--csv requires --mode map")
            if args.csv.resolve() in {args.input.resolve(), args.output.resolve()}:
                raise ValueError("CSV, JSON and input paths must differ")
        raw = args.input.read_bytes()
        result: CircuitResult | ConvergenceResult | OperatingMapResult | RoomSizingResult
        if args.mode == "room-sizing":
            result = size_room_cooling(
                CoolPropBackend(), RoomSizingRequest.model_validate_json(raw)
            )
        elif args.mode == "map":
            result = solve_operating_map(
                CoolPropBackend(), OperatingMapRequest.model_validate_json(raw)
            )
        elif args.mode == "closed-loop":
            result = solve_circuit(CoolPropBackend(), ConvergenceRequest.model_validate_json(raw))
        else:
            scenario = SyntheticScenario.model_validate_json(raw)
            result = evaluate_circuit(CoolPropBackend(), scenario)
        root = Path(__file__).resolve().parents[1]
        try:
            commit = subprocess.check_output(
                [
                    "git",
                    "-c",
                    f"safe.directory={root.as_posix()}",
                    "-C",
                    str(root),
                    "rev-parse",
                    "HEAD",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            dirty: bool | None = bool(
                subprocess.check_output(
                    [
                        "git",
                        "-c",
                        f"safe.directory={root.as_posix()}",
                        "-C",
                        str(root),
                        "status",
                        "--porcelain",
                        "--untracked-files=normal",
                    ],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
            )
        except (OSError, subprocess.CalledProcessError):
            commit, dirty = "UNKNOWN", None
        # Hash actual source bytes even when the checkout is dirty or git is unavailable.
        source_hashes = {
            p.relative_to(root).as_posix(): _sha256(p.read_bytes().replace(b"\r\n", b"\n"))
            for p in sorted((root / "src/agent_hvac").rglob("*.py"))
        }
        source_hashes["scripts/run_system_cycle.py"] = _sha256(
            Path(__file__).read_bytes().replace(b"\r\n", b"\n")
        )
        fluid = (
            result.scenario.refrigerant
            if isinstance(result, CircuitResult)
            else result.request.scenario.refrigerant
            if isinstance(result, ConvergenceResult)
            else result.request.base.scenario.refrigerant
        )
        artifact = {
            "artifact_version": "synthetic-hvac-map-v1",
            "mode": args.mode,
            "metadata": {
                "is_mock": True,
                "db_version": "N/A - no DB",
                "code_commit": commit,
                "working_tree_dirty": dirty,
                "source_sha256": source_hashes,
                "lock_sha256": _sha256((root / "uv.lock").read_bytes().replace(b"\r\n", b"\n")),
                "python": platform.python_version(),
                "coolprop": version("CoolProp"),
                "canonical_fluid": fluid,
                "property_model": (
                    "COOLPROP_BUILTIN_PSEUDOPURE_R410A"
                    if fluid == "R410A"
                    else "COOLPROP_PURE_FLUID"
                ),
                "property_source": (
                    "https://coolprop.org/fluid_properties/fluids/R410A.html; "
                    "Lemmon2003, DOI10.1023/A:1025048800563; CAS R410A.PPF; default reference state"
                    if fluid == "R410A"
                    else "CoolProp built-in pure fluid; default reference state"
                ),
                "input_sha256": _sha256(raw),
            },
            "original_input": json.loads(raw),
            "result": result.model_dump(mode="json"),
        }
        encoded = json.dumps(artifact, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        if isinstance(result, RoomSizingResult):
            print(
                f"{result.status}; design_target_satisfied={result.design_target_satisfied}; "
                f"{result.reason}; output={args.output}"
            )
            return 0 if result.design_target_satisfied else 1
        if isinstance(result, OperatingMapResult):
            if args.csv is not None:
                args.csv.parent.mkdir(parents=True, exist_ok=True)
                args.csv.write_text(operating_map_csv(result), encoding="utf-8", newline="")
            print(
                f"map: {result.converged_count} converged / {result.failed_count} failed; "
                f"output={args.output}"
            )
            return 0 if result.failed_count == 0 else 1
        print(
            f"{result.status}; cycle_converged={str(result.cycle_converged).lower()}; "
            f"output={args.output}"
        )
        if isinstance(result, CircuitResult):
            if result.failed_stage:
                print(f"{result.failed_stage}: {result.message}", file=sys.stderr)
            return 0 if result.status == "evaluated" else 1
        if not result.cycle_converged:
            print(f"{result.reason}: {result.message}", file=sys.stderr)
        return 0 if result.cycle_converged else 1
    except (OSError, ValidationError, ValueError) as exc:
        print(f"input/output error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
