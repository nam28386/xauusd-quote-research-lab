from pathlib import Path

import pytest

from xauusd_quote_lab.synthetic import FIXTURE_PATH, FIXTURE_SHA256, load_fixture


def test_golden_bytes_and_provenance():
    data, digest = load_fixture()
    assert digest == FIXTURE_SHA256
    assert data["provenance"] == "SYNTHETIC"
    assert len(data["streams"]) == 4


def test_modified_fixture_rejected(tmp_path: Path):
    path = tmp_path / FIXTURE_PATH
    path.parent.mkdir(parents=True)
    path.write_text('{"provenance":"SYNTHETIC"}', encoding="utf-8")
    with pytest.raises(ValueError, match="bytes"):
        load_fixture(tmp_path)
