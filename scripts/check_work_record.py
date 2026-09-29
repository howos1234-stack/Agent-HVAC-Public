"""Require a state update and substantive work record for a pull request."""

import argparse
import subprocess
from pathlib import Path

REQUIRED = ("## 수행 내용", "## 결정, 가정 및 출처", "## 검증 결과", "## 종료 및 인수인계")


def record_errors(text: str) -> list[str]:
    errors = []
    for heading in REQUIRED:
        if heading not in text:
            errors.append(f"Missing heading: {heading}")
            continue
        body = text.split(heading, 1)[1].split("\n## ", 1)[0].strip()
        if len(body) < 15 or body in ("TODO", "미정"):
            errors.append(f"Empty or placeholder section: {heading}")
    for label in ("- Phase / Workstream:", "- 작업 상태:"):
        if label not in text or not text.split(label, 1)[1].splitlines()[0].strip():
            errors.append(f"Missing value: {label}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    args = parser.parse_args()
    paths = subprocess.check_output(
        ["git", "diff", "--name-only", f"{args.base}...HEAD"], text=True
    ).splitlines()
    errors = []
    if "CURRENT_STATE.md" not in paths:
        errors.append("CURRENT_STATE.md must be updated")
    records = [
        Path(p)
        for p in paths
        if p.startswith("docs/development_log/")
        and p.endswith(".md")
        and not p.endswith("SESSION_TEMPLATE.md")
        and Path(p).is_file()
    ]
    if not records:
        errors.append("Add or update a session record")
    for path in records:
        errors.extend(
            f"{path}: {error}" for error in record_errors(path.read_text(encoding="utf-8"))
        )
    if errors:
        print("\n".join(errors))
        return 1
    print("Work record and CURRENT_STATE update present; human content review still required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
