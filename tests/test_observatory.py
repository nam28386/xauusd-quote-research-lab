import hashlib
import json
import os
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from shutil import copytree
from threading import Thread

import pytest

from xauusd_quote_lab.factorial_experiment import run
from xauusd_quote_lab.observatory import (
    MAX_LINE,
    Observatory,
    handler,
    json_bytes,
    load_dataset,
    scan_lines,
)
from xauusd_quote_lab.observatory_schema import InvalidArtifact, decode
from xauusd_quote_lab.replay import replay
from xauusd_quote_lab.sampling_experiments import write_experiment

TEST_SHA = "a" * 40
LOCK_SHA = "b" * 64


@pytest.fixture(scope="module")
def artifact_root(tmp_path_factory):
    external = os.environ.get("P3_ARTIFACT_ROOT")
    if external:
        return Path(external)
    root = tmp_path_factory.mktemp("observatory-generated")
    (root / "p1").mkdir()
    (root / "p1/evidence.json").write_bytes(replay(TEST_SHA).to_json().encode("ascii"))
    write_experiment(root / "p2", TEST_SHA, LOCK_SHA)
    run(root / "p21", TEST_SHA, LOCK_SHA)
    return root


@pytest.fixture(scope="module")
def app(artifact_root, tmp_path_factory):
    root = tmp_path_factory.mktemp("observatory-cache")
    return Observatory(
        {
            key: load_dataset(key, artifact_root / key, root / key, None)
            for key in ("p1", "p2", "p21")
        }
    )


def test_real_artifacts_use_bounded_jsonl_index_and_labeled_provenance(app):
    datasets = {d["id"]: d for d in json.loads(app.dispatch("/api/v1/datasets", {})[0])["datasets"]}
    assert datasets["p2"]["row_count"] == 384
    assert datasets["p21"]["row_count"] == 6912
    assert datasets["p1"]["verification"] == "fixture-reference-only"
    assert datasets["p21"]["verification"] == "manifest-consistency"
    assert (
        datasets["p21"]["artifacts"]["truth-inputs.jsonl"]["classification"] == "synthetic-source"
    )
    assert datasets["p21"]["artifacts"]["results.jsonl"]["classification"] == "derived"
    table = app.datasets["p21"].tables["p21"]
    assert table.rows is None
    assert len(table.offsets) == 6912
    assert table.offsets == sorted(table.offsets)


def test_filtered_pages_links_exact_source_and_reproducible_exports(app):
    filters = {
        "scenario": "isolated",
        "phase_percent": "0",
        "transport_ms": "0",
        "processing_ms": "0",
        "interval_ms": "250",
        "limit": "2",
    }
    first = app.envelope("p21", filters)
    second = app.envelope("p21", {**filters, "offset": "2"})
    assert first["total"] == second["total"] == 6
    assert [r["data"]["duration_ms"] for r in first["rows"]] == [25, 50]
    assert [r["data"]["duration_ms"] for r in second["rows"]] == [100, 250]
    ordinal = first["rows"][0]["ordinal"]
    assert app.envelope("p21", {}, str(ordinal))["row"] == first["rows"][0]
    source_hash = first["rows"][0]["data"]["input_sha256"]
    assert app.envelope("truth", {"input_sha256": source_hash})["total"] == 1
    view = {**filters, "view_metric": "recall", "view_session": "isolated-alpha-session"}
    a = app.dispatch("/api/v1/export/p21", view)
    b = app.dispatch("/api/v1/export/p21", dict(reversed(list(view.items()))))
    assert a == b
    export = json.loads(a[0])
    assert export["view"]["session_id"] == "isolated-alpha-session"
    assert export["rows"] == first["rows"]
    assert export["artifact_sha256"] == app.datasets["p21"].artifacts["results.jsonl"]["sha256"]


def test_exact_decimals_timestamps_and_unavailable_reasons(app):
    data = app.envelope(
        "p2",
        {"scenario": "stable", "interval_ms": "100", "tolerance_ms": "100", "phase_percent": "0"},
    )["rows"][0]["data"]
    stream = data["streams"][0]
    assert stream["events"]["recall"] is None
    assert stream["events"]["recall_unavailable"] == "no_truth_episodes"
    assert stream["coverage"].startswith("0.954545454545454545454545")
    assert len(stream["coverage"]) > 50
    assert stream["covered_ns"] == "2100000000"
    assert data["broker"]["points"][0]["decision_wall_ns"] == "0"


@pytest.mark.parametrize("raw", [b'{"x":0.1}', b'{"x":NaN}', b'{"x":1,"x":2}', b"\xff"])
def test_invalid_json_wire_rejected(raw):
    with pytest.raises(InvalidArtifact):
        decode(raw)


def test_correct_pin_and_wrong_independent_pin(artifact_root, tmp_path):
    src = artifact_root / "p1"
    pin = hashlib.sha256((src / "evidence.json").read_bytes()).hexdigest()
    accepted = load_dataset("p1", src, tmp_path / "pinned", pin)
    assert accepted.metadata()["verification"] == "independently-pinned-digest"
    with pytest.raises(InvalidArtifact, match="SHA-256 mismatch"):
        load_dataset("p1", src, tmp_path / "rejected", "0" * 64)
    assert (accepted.root / "evidence.json").read_bytes() == (src / "evidence.json").read_bytes()


def test_byte_corruption_rejected_before_parsing(artifact_root, tmp_path):
    src = Path(copytree(artifact_root / "p2", tmp_path / "broken"))
    path = src / "results.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(InvalidArtifact, match="SHA-256 mismatch"):
        load_dataset("p2", src, tmp_path / "cache", None)


@pytest.mark.parametrize(
    ("old", "new", "error"),
    [
        (b'"interval_ms":100', b'"interval_ms":999', "design factor"),
        (b'"decision_wall_ns":"0"', b'"decision_wall_ns":0', "nanosecond"),
        (b'"fewer_than_three_eligible_brokers"', b'"invented_reason"', "reason code"),
    ],
)
def test_rehashed_invalid_schema_still_rejected(artifact_root, tmp_path, old, new, error):
    src = Path(copytree(artifact_root / "p2", tmp_path / "malformed"))
    content = (src / "results.json").read_bytes()
    assert old in content
    content = content.replace(old, new, 1)
    (src / "results.json").write_bytes(content)
    manifest = json.loads((src / "manifest.json").read_bytes())
    manifest["artifacts"]["results.json"] = {
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    (src / "manifest.json").write_bytes(json_bytes(manifest))
    with pytest.raises(InvalidArtifact, match=error):
        load_dataset("p2", src, tmp_path / "cache", None)


def test_manifest_rejects_paths_unsupported_version_and_excessive_size(artifact_root, tmp_path):
    src = tmp_path / "inputs"
    src.mkdir()
    original = json.loads((artifact_root / "p2/manifest.json").read_bytes())
    rejected = (
        (
            {**original, "artifacts": {"../outside.json": {"bytes": 1, "sha256": "a" * 64}}},
            "inventory",
        ),
        ({**original, "versions": ["unknown-v1"]}, "versions"),
        (
            {
                **original,
                "artifacts": {
                    **original["artifacts"],
                    "results.json": {"bytes": 10**9, "sha256": "a" * 64},
                },
            },
            "size limit",
        ),
    )
    for index, (manifest, message) in enumerate(rejected):
        (src / "manifest.json").write_bytes(json_bytes(manifest))
        with pytest.raises(InvalidArtifact, match=message):
            load_dataset("p2", src, tmp_path / str(index), None)


def test_private_verified_snapshot_is_independent_of_original(artifact_root, tmp_path):
    source = Path(copytree(artifact_root / "p1", tmp_path / "source"))
    cache = load_dataset("p1", source, tmp_path / "cache", None)
    original = (cache.root / "evidence.json").read_bytes()
    (source / "evidence.json").write_bytes(b"replaced")
    assert (cache.root / "evidence.json").read_bytes() == original


def test_jsonl_single_line_is_bounded(tmp_path):
    path = tmp_path / "large.jsonl"
    path.write_bytes(b" " * (MAX_LINE + 1))
    with pytest.raises(InvalidArtifact, match="row limit"):
        scan_lines(path, lambda _: None)


def test_local_http_rejects_writes_cross_origin_and_path_traversal(app):
    with ThreadingHTTPServer(("127.0.0.1", 0), handler(app)) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()

        def check(method, path, headers=None):
            conn = HTTPConnection("127.0.0.1", server.server_port, timeout=4)
            try:
                conn.request(method, path, headers=headers or {})
                response = conn.getresponse()
                return response.status, dict(response.headers), response.read()
            finally:
                conn.close()

        try:
            assert check("GET", "/api/v1/datasets")[0] == 200
            assert check("HEAD", "/api/v1/datasets")[2] == b""
            assert check("POST", "/api/v1/datasets")[0] == 405
            assert check("GET", "/api/v1/datasets", {"Host": "remote.invalid"})[0] == 403
            assert check("GET", "/api/v1/datasets", {"Origin": "https://remote.invalid"})[0] == 403
            assert check("GET", "/api/v1/artifact/p2/%2e%2e")[0] == 400
            assert check("GET", "/api/v1/artifact/p21/results.jsonl")[0] == 404
            assert check("GET", "/api/v1/table/p21?limit=101")[0] == 400
            assert check("GET", "/api/v1/table/p21?limit=1&limit=2")[0] == 400
            status, headers, raw = check("GET", "/api/v1/artifact/p2/manifest.json")
            assert status == 200
            assert headers["Content-Disposition"].endswith('"manifest.json"')
            assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
            assert raw == (app.datasets["p2"].root / "manifest.json").read_bytes()
        finally:
            server.shutdown()
            worker.join(timeout=5)
