import hashlib
import json
from pathlib import Path
from shutil import copytree

import pytest

from xauusd_quote_lab.observatory import json_bytes
from xauusd_quote_lab.offline_import import MAX_ROW, check_rows, save_receipt, validate

EXAMPLES = Path("fixtures/offline")


def cloned(tmp_path):
    return Path(copytree(EXAMPLES / "synthetic-valid", tmp_path / "input"))


def change_manifest(root, **edits):
    path = root / "manifest.json"
    value = json.loads(path.read_bytes())
    value.update(edits)
    path.write_bytes(json_bytes(value))
    return value


def replace_rows(root, *rows):
    payload = b"".join(json_bytes(row) for row in rows)
    (root / "observations.jsonl").write_bytes(payload)
    change_manifest(root, source_sha256=hashlib.sha256(payload).hexdigest())


def test_synthetic_fixture_preserves_decimal_bytes_and_visible_duplicates():
    path = EXAMPLES / "synthetic-valid"
    old = (path / "observations.jsonl").read_bytes()
    report = validate(path)
    assert report.admissibility == "SYNTHETIC_VALIDATED_NO_PROMOTION"
    assert (report.total_rows, report.parsed_rows, report.accepted_rows, report.rejected_rows) == (
        3,
        3,
        3,
        0,
    )
    assert report.quality_flags == {"duplicate_snapshot": 1}
    assert report.timestamp_diagnostics["counts"] == {"source_missing": 1}
    assert b'"ask":"2000.2500"' in old
    assert (path / "observations.jsonl").read_bytes() == old
    assert report.source_sha256 == hashlib.sha256(old).hexdigest()


def test_unknown_unit_missing_and_crossed_rows_are_quarantined(tmp_path):
    report = validate(EXAMPLES / "synthetic-invalid")
    assert report.admissibility == "QUARANTINED"
    assert report.unit_compatibility == "UNKNOWN"
    assert (report.total_rows, report.parsed_rows, report.accepted_rows, report.rejected_rows) == (
        3,
        3,
        1,
        2,
    )
    assert report.quality_flags == {"crossed": 1, "missing_ask": 1}
    receipt = save_receipt(report, tmp_path)
    assert receipt.parent.name == "quarantine"
    first = receipt.read_bytes()
    assert save_receipt(report, tmp_path) == receipt
    assert receipt.read_bytes() == first
    assert b"2000." not in first
    assert not list(tmp_path.rglob("*.jsonl"))


@pytest.mark.parametrize("environment", ["REAL", "DEMO", "UNKNOWN"])
def test_external_labels_are_hashed_but_never_parsed(tmp_path, environment):
    root = cloned(tmp_path)
    manifest = change_manifest(root, environment=environment)
    report = validate(root)
    assert report.admissibility == "QUARANTINED"
    assert report.source_sha256 == manifest["source_sha256"]
    assert report.environment == environment
    assert report.total_rows == report.parsed_rows == 0
    assert not report.scan_complete
    assert "external_environment_quarantined" in report.issues


def test_missing_provenance_and_unapproved_fields_do_not_echo_payload(tmp_path):
    root = cloned(tmp_path)
    change_manifest(root, source={"unapproved_field": "do-not-echo-this-value"})
    report = validate(root)
    assert report.missing_provenance == ("source.acquisition_method", "source.identity")
    assert "undeclared_manifest_fields" in report.issues
    assert report.source_sha256 is None
    assert "do-not-echo" not in repr(report)


def test_no_traversal_and_digest_corruption_does_not_parse(tmp_path):
    root = cloned(tmp_path)
    expected = json.loads((root / "manifest.json").read_bytes())["source_sha256"]
    change_manifest(root, data_file="../observations.jsonl")
    assert "unsafe_data_reference" in validate(root).issues
    change_manifest(root, data_file="observations.jsonl")
    with (root / "observations.jsonl").open("ab") as file:
        file.write(b" ")
    report = validate(root)
    assert report.source_sha256 != expected
    assert report.parsed_rows == 0
    assert "source_digest_mismatch" in report.issues


def test_clock_diagnostics_preserve_source_and_receive_domains(tmp_path):
    root = cloned(tmp_path)
    row = json.loads((root / "observations.jsonl").read_bytes().splitlines()[0])
    bad = {
        **row,
        "sequence": 1,
        "received_wall_ns": "99000000",
        "processing_wall_ns": "98000000",
        "source_time_ms": "300",
    }
    good = {
        **row,
        "sequence": 2,
        "received_wall_ns": "110000010",
        "processing_wall_ns": "110000020",
        "source_time_ms": "110",
    }
    replace_rows(root, row, bad, good)
    report = validate(root)
    assert report.accepted_rows == 2
    assert report.timestamp_diagnostics["counts"] == {
        "future_source_timestamp": 1,
        "processing_before_receive": 1,
        "processing_clock_reversal": 1,
        "receive_clock_reversal": 1,
    }
    clocks = json.loads((root / "manifest.json").read_bytes())["clocks"]
    clocks.update(source_comparable_to_receive=False, processing_domain="separate")
    change_manifest(root, clocks=clocks)
    report = validate(root)
    assert not report.timestamp_diagnostics["source_vs_receive_assessed"]
    assert not report.timestamp_diagnostics["processing_vs_receive_assessed"]
    assert "future_source_timestamp" not in report.quality_flags


@pytest.mark.parametrize(
    ("key", "bad", "flag"),
    [
        ("bid", "2e3", "invalid_decimal_encoding"),
        ("bid", 2000.25, "invalid_json"),
        ("received_wall_ns", 123, "invalid_timestamp_encoding"),
        ("received_wall_ns", "01", "invalid_timestamp_encoding"),
        ("sequence", True, "invalid_sequence_encoding"),
    ],
)
def test_strict_wire_shapes(tmp_path, key, bad, flag):
    root = cloned(tmp_path)
    row = json.loads((root / "observations.jsonl").read_bytes().splitlines()[0])
    replace_rows(root, {**row, key: bad})
    report = validate(root)
    assert (report.total_rows, report.parsed_rows, report.rejected_rows) == (1, 0, 1)
    assert report.quality_flags == {flag: 1}


def test_oversized_row_and_file_stop_scan(tmp_path, monkeypatch):
    root = cloned(tmp_path)
    data = b" " * (MAX_ROW + 1) + b"\n"
    (root / "observations.jsonl").write_bytes(data)
    change_manifest(root, source_sha256=hashlib.sha256(data).hexdigest())
    report = validate(root)
    assert not report.scan_complete
    assert report.quality_flags == {"row_oversized": 1}
    assert "incomplete_scan" in report.issues
    from xauusd_quote_lab import offline_import

    monkeypatch.setattr(offline_import, "MAX_BYTES", 3)
    assert "file_oversized" in validate(root).issues


def test_row_limit_is_explicit(monkeypatch):
    from xauusd_quote_lab import offline_import

    monkeypatch.setattr(offline_import, "MAX_ROWS", 1)
    root = EXAMPLES / "synthetic-valid"
    data = (root / "observations.jsonl").read_bytes()
    clocks = json.loads((root / "manifest.json").read_bytes())["clocks"]
    total, parsed, accepted, complete, flags, _ = check_rows(data, clocks)
    assert (total, parsed, accepted, complete) == (1, 1, 1, False)
    assert flags == {"row_limit_exceeded": 1}
