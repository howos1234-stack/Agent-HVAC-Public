"""Archive a finite synthetic design study. Exit 0: a load match; 1: none; 2: input/I/O."""

import argparse
import hashlib
import json
import platform
import subprocess
from importlib.metadata import version
from pathlib import Path

from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.solvers.system_cycle.design_study import (
    DesignPoint,
    DesignStudyRequest,
    design_study_csv,
    solve_design_study,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = args.input.read_bytes()
        request = DesignStudyRequest.model_validate_json(raw)
        paths = ["metadata.json", "result.json", "summary.csv"] + [
            f"case-{i:03}.json" for i in range(len(request.cases))
        ]
        if args.input.resolve() in {(args.output_dir / p).resolve() for p in paths}:
            raise ValueError("output must not overwrite the input")
        root = Path(__file__).resolve().parents[1]
        git = ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root)]
        try:
            commit = subprocess.check_output(
                git + ["rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
            ).strip()
            dirty = bool(
                subprocess.check_output(
                    git + ["status", "--porcelain"], text=True, stderr=subprocess.DEVNULL
                ).strip()
            )
        except (OSError, subprocess.CalledProcessError):
            commit, dirty = "UNKNOWN", None

        def sha(data: bytes) -> str:
            return hashlib.sha256(data).hexdigest()

        metadata = {
            "is_mock": True,
            "source_ref": request.source_ref,
            "code_commit": commit,
            "dirty": dirty,
            "python": platform.python_version(),
            "coolprop": version("CoolProp"),
            "canonical_fluid": request.refrigerant,
            "property_model": (
                "CoolProp built-in R410A pseudo-pure"
                if request.refrigerant == "R410A"
                else "CoolProp pure-fluid model"
            ),
            "input_sha256": sha(raw),
            "lock_sha256": sha((root / "uv.lock").read_bytes().replace(b"\r\n", b"\n")),
            "source_sha256": {
                p.relative_to(root).as_posix(): sha(p.read_bytes().replace(b"\r\n", b"\n"))
                for p in sorted((root / "src/agent_hvac").rglob("*.py"))
            },
            "runner_sha256": sha(Path(__file__).read_bytes().replace(b"\r\n", b"\n")),
            "original_input": json.loads(raw),
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        index = 0

        def record(point: DesignPoint) -> None:
            nonlocal index
            (args.output_dir / f"case-{index:03}.json").write_text(
                point.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
            print(
                f"{index + 1}/{len(request.cases)} {point.case.case_id}: {point.cycle.reason}; "
                f"Q={point.cooling.value if point.cooling else None}; "
                f"matched={point.load_balance_satisfied}",
                flush=True,
            )
            index += 1

        result = solve_design_study(CoolPropBackend(), request, on_point=record)
        (args.output_dir / "result.json").write_text(
            result.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        (args.output_dir / "summary.csv").write_text(
            design_study_csv(result), encoding="utf-8", newline=""
        )
        matched = sum(p.load_balance_satisfied for p in result.points)
        print(f"Completed {len(result.points)} cases; {matched} load matches.")
        return 0 if matched else 1
    except (ValueError, OSError) as exc:
        print(f"input/output error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
