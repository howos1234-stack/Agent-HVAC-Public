import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location(
    "source_manifest", ROOT / "scripts/source_manifest.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_repository_manifest_matches_sources_and_fixtures():
    assert module.check(ROOT) == []


@pytest.fixture
def inventory_root(tmp_path):
    source = tmp_path / "tests/fixtures/example.json"
    source.parent.mkdir(parents=True)
    source.write_bytes(b'{"value": 1}\n')
    manifest = tmp_path / module.MANIFEST
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps(module.inventory(tmp_path)), encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("mutation", ["change", "add", "delete", "duplicate_manifest_entry"])
def test_inventory_detects_drift(inventory_root, mutation):
    source = inventory_root / "tests/fixtures/example.json"
    if mutation == "change":
        source.write_bytes(b'{"value": 2}\n')
    elif mutation == "add":
        source.with_name("new.json").write_bytes(b"{}\n")
    elif mutation == "delete":
        source.unlink()
    else:
        manifest = inventory_root / module.MANIFEST
        rows = json.loads(manifest.read_text(encoding="utf-8"))
        manifest.write_text(json.dumps(rows + rows), encoding="utf-8")
    assert module.check(inventory_root)


def test_line_endings_follow_git_lf_policy(inventory_root):
    source = inventory_root / "tests/fixtures/example.json"
    source.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
    assert module.check(inventory_root) == []
