"""Run bounded synthetic analysis. Exit 0 target, 1 no target, 2 input/I/O, 3 solver error."""

import argparse
import hashlib
import json
import platform
import subprocess
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.solvers.system_cycle.analysis_input import CompactAnalysisInput, expand_analysis
from agent_hvac.solvers.system_cycle.analysis_manager import AnalysisRequest, run_analysis
from agent_hvac.solvers.system_cycle.design_study import DesignPoint


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("expanded", "compact"), default="expanded")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = args.input.read_bytes()
        request = (
            expand_analysis(CompactAnalysisInput.model_validate_json(raw))
            if args.format == "compact"
            else AnalysisRequest.model_validate_json(raw)
        )
        # Exclusive run directory prevents replacement of prior evidence.
        args.output_dir.mkdir(parents=True, exist_ok=False)
    except (ValueError, OSError) as exc:
        print(f"input/output error: {exc}")
        return 2

    def write(name, data):
        (args.output_dir / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )

    root = Path(__file__).resolve().parents[1]
    git = ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root)]
    try:
        head = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
        dirty = bool(subprocess.check_output(git + ["status", "--porcelain"], text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        head, dirty = "UNKNOWN", None

    def sha(path):
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()

    completed = 0
    try:
        write(
            "metadata.json",
            {
                "started_utc": datetime.now(UTC).isoformat(),
                "code_commit": head,
                "dirty": dirty,
                "is_mock": True,
                "db": None,
                "python": platform.python_version(),
                "coolprop": version("CoolProp"),
                "input_sha256": hashlib.sha256(raw).hexdigest(),
                "lock_sha256": sha(root / "uv.lock"),
                "source_sha256": {
                    p.relative_to(root).as_posix(): sha(p)
                    for p in sorted((root / "src/agent_hvac").rglob("*.py"))
                },
                "runner_sha256": sha(Path(__file__)),
                "original_input": json.loads(raw),
                "input_format": args.format,
                "expanded_request": request.model_dump(mode="json"),
                "preset_sha256": {
                    p.name: sha(p)
                    for p in sorted(
                        (root / "src/agent_hvac/solvers/system_cycle/presets").glob("*.json")
                    )
                },
            },
        )

        def record(point: DesignPoint) -> None:
            nonlocal completed
            write(f"case-{completed:03}.json", point.model_dump(mode="json"))
            completed += 1
            print(
                f"{completed}/{len(request.study.cases)} {point.case.case_id}: "
                f"{point.cycle.reason}; target={point.load_balance_satisfied}",
                flush=True,
            )

        # Unexpected solver errors are archived as ERROR, never treated as ordinary infeasibility.
        try:
            report = run_analysis(CoolPropBackend(), request, on_point=record)
        except OSError:
            raise
        except Exception as exc:
            write(
                "error.json",
                {
                    "status": "ERROR",
                    "category": "UNEXPECTED_SOLVER_ERROR",
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                    "completed_cases": completed,
                    "target_found": False,
                    "next_action": "Reproduce and inspect; no automatic code or physics changes.",
                },
            )
            print(f"solver error ({type(exc).__name__}): {exc}")
            return 3
        write("report.json", report.model_dump(mode="json"))
        print(f"{report.conclusion}; closest eligible case={report.closest_eligible_case_id}")
        return 0 if report.target_found else 1
    except OSError as exc:
        print(f"archive I/O error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
