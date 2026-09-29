import io
import json
import logging

import pytest
from pydantic import ValidationError

from agent_hvac.schemas.results import FinalDesignPackage
from agent_hvac.utils.logging import configure_logging
from agent_hvac.utils.provenance import file_sha256, load_package, save_package


def test_archive_roundtrip_and_no_overwrite(tmp_path, fixture_data):
    package = FinalDesignPackage.model_validate(fixture_data("final_design_package"))
    path = tmp_path / "run.json"
    save_package(package, path)
    assert load_package(path) == package
    assert len(file_sha256(path)) == 64
    with pytest.raises(FileExistsError):
        save_package(package, path)


def test_tampered_archive_rejected(tmp_path, fixture_data):
    data = fixture_data("final_design_package")
    data["release_ready"] = True
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_package(path)


def test_log_is_json_and_configuration_is_idempotent():
    root_handlers = tuple(logging.getLogger().handlers)
    stream = io.StringIO()
    configure_logging(stream)
    logger = configure_logging(stream)
    logger.info("검증 이벤트")
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["message"] == "검증 이벤트"
    assert tuple(logging.getLogger().handlers) == root_handlers
