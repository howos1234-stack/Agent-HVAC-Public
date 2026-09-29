"""Reject restricted product evidence from the public repository."""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

TEMPLATE = Path("docs/product_data/templates/Agent-HVAC_ProductData_0.2.0_template.xlsx")
EXPECTED_SHEETS = (
    "products",
    "source_metadata",
    "data_sources",
    "derived_source_conditions",
    "rated_points",
    "rated_point_values",
    "performance_maps",
    "map_axes",
    "performance_points",
    "performance_point_values",
    "map_fixed_conditions",
    "operating_envelopes",
    "envelope_axes",
    "envelope_vertices",
    "envelope_fixed_conditions",
)
RESTRICTED_SUFFIXES = {
    ".gif",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".webp",
    ".xls",
    ".xlsb",
    ".xlsm",
    ".xlsx",
    ".zip",
}
EXCLUDED_PARTS = {
    ".artifact_work",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tools",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "artifacts",
    "build",
    "dist",
}


def repository_files(root: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and not EXCLUDED_PARTS.intersection(path.relative_to(root).parts)
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def check_restricted_artifacts(root: Path) -> list[str]:
    allowed = root / TEMPLATE
    return [
        f"Restricted public artifact: {path.relative_to(root).as_posix()}"
        for path in repository_files(root)
        if path.suffix.lower() in RESTRICTED_SUFFIXES and path != allowed
    ]


def check_component_data(root: Path) -> list[str]:
    component_root = root / "data/components"
    if not component_root.exists():
        return []
    return [
        f"Public component data must remain empty: {path.relative_to(root).as_posix()}"
        for path in sorted(component_root.rglob("*"))
        if path.is_file() and path.name != ".gitkeep"
    ]


def check_blank_template(root: Path) -> list[str]:
    path = root / TEMPLATE
    if not path.is_file():
        return [f"Missing public blank template: {TEMPLATE.as_posix()}"]

    workbook = load_workbook(path, read_only=False, data_only=False)
    try:
        errors: list[str] = []
        if tuple(workbook.sheetnames) != EXPECTED_SHEETS:
            errors.append(
                "Public template sheet contract differs: "
                f"expected {list(EXPECTED_SHEETS)!r}, got {workbook.sheetnames!r}"
            )
        for sheet in workbook.worksheets:
            for row_number, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                if any(value not in (None, "") for value in row):
                    errors.append(f"Public template contains data: {sheet.title}!{row_number}")
        return errors
    finally:
        workbook.close()


def check(root: Path) -> list[str]:
    return [
        *check_restricted_artifacts(root),
        *check_component_data(root),
        *check_blank_template(root),
    ]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = check(root)
    if errors:
        print("\n".join(errors))
        return 1
    print(
        "Public data boundary verified: one blank 15-sheet template, "
        "no restricted artifacts or component data"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
