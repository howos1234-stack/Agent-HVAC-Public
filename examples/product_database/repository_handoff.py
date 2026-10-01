"""Inspect public synthetic product workbooks through the existing repository API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent_hvac.database.index import ExcelComponentRepository
from agent_hvac.schemas.components import ProductRecord


def _use_status(record: Any) -> dict[str, Any]:
    status = record.use_status
    return {
        "automatic_selection": status.automatic_selection.value,
        "reasons": [reason.value for reason in status.reasons],
    }


def product_inventory(product: ProductRecord) -> dict[str, Any]:
    """Return record-level availability without claiming product calculability."""
    return {
        "product_id": product.product_id,
        "component_type": product.component_type.value,
        "is_mock": product.is_mock,
        "source_ids": [source.source_id for source in product.data_sources],
        "rated_points": {
            record.rated_point_id: _use_status(record) for record in product.rated_points
        },
        "performance_maps": {
            record.map_id: _use_status(record) for record in product.performance_maps
        },
        "operating_envelopes": {
            record.envelope_id: _use_status(record) for record in product.operating_envelopes
        },
    }


def inspect_repository(root: Path) -> dict[str, Any]:
    repository = ExcelComponentRepository(root)
    summary = repository.reload()
    return {
        "database_version": summary.database_version,
        "valid_files": summary.valid_files,
        "rejected_files": summary.rejected_files,
        "loaded_products": summary.loaded_products,
        "errors": list(summary.errors),
        "products": [product_inventory(product) for product in repository.records],
        "consumer_warning": (
            "A listed product is not calculable unless its required detailed record exists "
            "and is ELIGIBLE. Revalidate selections whenever database_version changes."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect synthetic Excel product data without changing repository state."
    )
    parser.add_argument("root", type=Path, help="Directory containing synthetic .xlsx files")
    args = parser.parse_args()
    print(json.dumps(inspect_repository(args.root), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
