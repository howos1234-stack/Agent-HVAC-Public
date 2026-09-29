"""Protect the physical core from GUI/agent dependencies before implementations arrive."""

import ast
from pathlib import Path


def test_core_does_not_import_gui_or_agent_dependencies():
    root = Path(__file__).parents[2] / "src" / "agent_hvac"
    forbidden = (
        "streamlit",
        "openai",
        "agents",
        "fastapi",
        "PySide6",
        "agent_hvac.agents",
        "agent_hvac.app",
        "agent_hvac.reporting",
    )
    for name in ("physics", "properties", "components", "solvers", "schemas", "utils"):
        for path in (root / name).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                imports = []
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    imports = [node.module or ""]
                assert not any(
                    m == f or m.startswith(f + ".") for m in imports for f in forbidden
                ), path
