"""Validated JSON archives and SHA-256 identities for reproducibility."""

import hashlib
from pathlib import Path

from agent_hvac.schemas.results import FinalDesignPackage


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def save_package(package: FinalDesignPackage, path: Path) -> None:
    """Create a new archive; never silently replace an earlier run."""
    validated = FinalDesignPackage.model_validate_json(package.model_dump_json())
    with path.open("x", encoding="utf-8") as target:
        target.write(validated.model_dump_json(indent=2))
        target.write("\n")


def load_package(path: Path) -> FinalDesignPackage:
    return FinalDesignPackage.model_validate_json(path.read_text(encoding="utf-8"))
