import json
from pathlib import Path

import pytest


@pytest.fixture
def fixture_data():
    def read(name):
        path = Path(__file__).parent / "fixtures" / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    return read
