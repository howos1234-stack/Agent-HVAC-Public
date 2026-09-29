"""Generate/check the source inventory using repository LF text bytes, never JSON semantics."""

import argparse
import hashlib
import json
from pathlib import Path

MANIFEST = Path("docs/validation/p00-source-manifest.json")
SOURCE_ROOTS = ("src", "tests", "scripts")
EXCLUDED = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
CONFIG_FILES = ("pyproject.toml", "uv.lock", ".python-version", ".gitattributes")


def source_files(root: Path) -> list[Path]:
    paths = {
        p
        for folder in SOURCE_ROOTS
        for p in (root / folder).rglob("*")
        if p.is_file()
        and not EXCLUDED.intersection(p.relative_to(root).parts)
        and p.suffix not in (".pyc", ".pyo")
    }
    paths.update(root / name for name in CONFIG_FILES if (root / name).is_file())
    paths.update((root / ".github/workflows").glob("*.yml"))
    paths.update((root / ".github/workflows").glob("*.yaml"))
    return sorted(paths, key=lambda p: p.relative_to(root).as_posix())


def inventory(root: Path) -> list[dict[str, str]]:
    """Hash text files after CRLF-to-LF normalization matching .gitattributes.

    Source/fixture bytes otherwise remain unchanged. Binary product data is outside
    this inventory and must retain its raw source hash in ProductSource.
    """
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        }
        for path in source_files(root)
    ]


def check(root: Path) -> list[str]:
    path = root / MANIFEST
    if not path.is_file():
        return [f"Missing manifest: {MANIFEST}"]
    expected = json.loads(path.read_text(encoding="utf-8"))
    actual = inventory(root)
    if expected == actual:
        return []
    return [
        "Source manifest differs: changed, added, removed or duplicate entries; "
        "review changes and run python scripts/source_manifest.py --write"
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.write:
        path = root / MANIFEST
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(inventory(root), indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    else:
        errors = check(root)
        if errors:
            print("\n".join(errors))
            return 1
    print(
        f"Source manifest {'written' if args.write else 'verified'}: {len(inventory(root))} files"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
