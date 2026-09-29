"""In-memory implementation of the frozen ComponentRepository contract."""

from __future__ import annotations

import hashlib
from pathlib import Path

from agent_hvac.database.excel_loader import (
    LOADER_VERSION,
    SCHEMA_VERSION,
    discover_workbooks,
    load_product_workbook_with_diagnostics,
    read_workbook_snapshot,
)
from agent_hvac.schemas.components import ComponentQuery, ProductRecord, ReloadSummary
from agent_hvac.schemas.provenance import Parameter
from agent_hvac.utils.exceptions import DatabaseValidationError
from agent_hvac.utils.units import Quantity


class ExcelComponentRepository:
    """Reloadable product index backed only by validated Excel workbook bytes."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._records: tuple[ProductRecord, ...] = ()
        self._last_summary: ReloadSummary | None = None

    @property
    def records(self) -> tuple[ProductRecord, ...]:
        return self._records

    @property
    def last_summary(self) -> ReloadSummary | None:
        return self._last_summary

    def reload(self) -> ReloadSummary:
        paths = discover_workbooks(self._root)
        errors: list[str] = []
        records_by_file: dict[Path, tuple[ProductRecord, ...]] = {}
        rejected: set[Path] = set()
        fingerprints: list[tuple[str, str]] = []

        for path in paths:
            relative = path.relative_to(self._root).as_posix()
            fingerprint = "unreadable"
            try:
                snapshot = read_workbook_snapshot(path)
                fingerprint = snapshot.sha256
                loaded = load_product_workbook_with_diagnostics(
                    path, database_root=self._root, snapshot=snapshot
                )
                records_by_file[path] = loaded.records
                errors.extend(loaded.diagnostics)
            except DatabaseValidationError as exc:
                rejected.add(path)
                errors.append(f"{relative}: {exc}")
            fingerprints.append((relative, fingerprint))

        locations: dict[str, list[Path]] = {}
        for path, records in records_by_file.items():
            for record in records:
                locations.setdefault(record.product_id, []).append(path)
        for product_id, owners in sorted(locations.items()):
            if len(owners) > 1:
                rejected.update(owners)
                names = ", ".join(sorted(p.relative_to(self._root).as_posix() for p in owners))
                errors.append(f"duplicate product_id {product_id!r} across files: {names}")

        records = tuple(
            sorted(
                (
                    record
                    for path, loaded in records_by_file.items()
                    if path not in rejected
                    for record in loaded
                ),
                key=lambda record: (record.component_type.value, record.product_id),
            )
        )
        summary = ReloadSummary(
            valid_files=len(paths) - len(rejected),
            rejected_files=len(rejected),
            loaded_products=len(records),
            database_version=_database_version(fingerprints),
            errors=tuple(sorted(errors)),
        )
        self._records = records
        self._last_summary = summary
        return summary

    def search(self, query: ComponentQuery) -> list[ProductRecord]:
        """Apply compatibility and exact typed filters in deterministic order."""
        return [
            record
            for record in self._records
            if record.component_type == query.component_type
            and query.refrigerant.casefold()
            in {refrigerant.casefold() for refrigerant in record.supported_refrigerants}
            and all(_matches_filter(record, item) for item in query.filters)
        ]


def _database_version(fingerprints: list[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    digest.update(f"loader={LOADER_VERSION}\nschema={SCHEMA_VERSION}\n".encode())
    for relative, fingerprint in fingerprints:
        digest.update(f"{relative}\0{fingerprint}\n".encode())
    return f"sha256:{digest.hexdigest()}"


def _matches_filter(record: ProductRecord, expected: Parameter) -> bool:
    candidates = (
        *record.attributes,
        *record.rated_conditions,
        *record.operating_limits,
    )
    for actual in candidates:
        if actual.name != expected.name:
            continue
        if isinstance(actual.value, Quantity) and isinstance(expected.value, Quantity):
            return (
                actual.value.unit == expected.value.unit
                and actual.value.value == expected.value.value
            )
        return actual.value == expected.value
    return False
