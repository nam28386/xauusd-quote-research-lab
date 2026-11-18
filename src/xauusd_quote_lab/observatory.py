"""Verified artifact snapshots and loopback-only read API for P3."""

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import parse_qsl, urlsplit

from .observatory_schema import (
    COMMIT,
    FACTORS,
    P2,
    P2_NAMES,
    P21,
    P21_NAMES,
    SHA,
    ArtifactMeta,
    Row,
    check_versions,
    decode,
    evidence,
    history,
    instrument_versions,
    is_count,
    matches,
    object_keys,
    objects,
    published_row,
    quote,
    require,
    row_config,
    validate_fields,
)
from .synthetic import FIXTURE_SHA256

MAX_FILE = 96 * 1024 * 1024
MAX_JSON = 8 * 1024 * 1024
MAX_LINE = 256 * 1024
PACKET_LIMIT = 65536
API_VERSION = "p3-read-v1"
NAME = re.compile(r"[a-z0-9-]+\.(?:json|jsonl)")
ASSETS = re.compile(r"assets/[a-zA-Z0-9_.-]+")
P2_FILES = {"results.json", "sensitivity.json"} | {
    f"{group}-{scenario}.json" for scenario in P2_NAMES for group in ("input", "evidence")
}
P21_FILES = {
    "results.jsonl",
    "truth-inputs.jsonl",
    "ideal-intersection.json",
    "heatmap.json",
    "sensitivity.json",
    "tail-decomposition.json",
    "asof-results.jsonl",
    "asof-sensitivity.json",
    "identifiability.json",
    "evidence.json",
}


def json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        + "\n"
    ).encode("ascii")


def file_limit(name: str) -> int:
    if name.startswith("evidence"):
        return PACKET_LIMIT
    return MAX_FILE if name.endswith(".jsonl") else MAX_JSON


def snapshot(source: Path, target: Path, cap: int, expected: str | None = None) -> ArtifactMeta:
    require(source.resolve() == source and not source.is_symlink(), "Unsafe artifact path")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    # Check before open so an unexpected pipe cannot block startup.
    require(source.is_file(), "Expected a regular artifact")
    digest = hashlib.sha256()
    length = 0
    with os.fdopen(os.open(source, flags), "rb") as inp, target.open("xb") as out:
        info = os.fstat(inp.fileno())
        require(
            stat.S_ISREG(info.st_mode) and info.st_size <= cap, "Oversized or irregular artifact"
        )
        while block := inp.read(256 * 1024):
            length += len(block)
            require(length <= cap, "Artifact exceeds byte limit")
            digest.update(block)
            out.write(block)
    checksum = digest.hexdigest()
    require(expected is None or checksum == expected, f"SHA-256 mismatch for {source.name}")
    return {"sha256": checksum, "bytes": length}


FILTER_KEYS = set(FACTORS) | {"scenario", "tail", "input_sha256"}
TABLES = {
    "p2": ("p2", "results.json", None),
    "p2-sensitivity": ("p2", "sensitivity.json", "configurations"),
    "p2-phase": ("p2", "sensitivity.json", "phase_sensitivity"),
    "p21": ("p21", "results.jsonl", None),
    "p21-asof": ("p21", "asof-results.jsonl", None),
    "asof-sensitivity": ("p21", "asof-sensitivity.json", None),
    "heatmap": ("p21", "heatmap.json", None),
    "ideal": ("p21", "ideal-intersection.json", None),
    "tail": ("p21", "tail-decomposition.json", None),
    "p21-sensitivity": ("p21", "sensitivity.json", "by_width_interval"),
    "transport-processing": ("p21", "sensitivity.json", "by_transport_processing"),
    "identifiability": ("p21", "identifiability.json", None),
    "truth": ("p21", "truth-inputs.jsonl", None),
}


def filter_values(row: dict) -> dict:
    values = {key: row[key] for key in FILTER_KEYS & row.keys()}
    if isinstance(row.get("broker"), dict) and "tolerance_ms" in row["broker"]:
        values.setdefault("tolerance_ms", row["broker"]["tolerance_ms"])
    return values


@dataclass
class Table:
    filters: list[dict]
    rows: list[dict] | None = None
    path: Path | None = None
    offsets: list[int] = field(default_factory=list)

    def read(self, indices: list[int]) -> list[Row]:
        if self.rows is not None:
            return [{"ordinal": i, "data": self.rows[i]} for i in indices]
        with self.path.open("rb") as file:
            records = []
            for i in indices:
                file.seek(self.offsets[i])
                records.append({"ordinal": i, "data": decode(file.readline(MAX_LINE + 1))})
            return records

    def page(self, query: dict, offset: int, limit: int) -> dict:
        matching = [
            i
            for i, keys in enumerate(self.filters)
            if all(keys.get(k) == v for k, v in query.items())
        ]
        return {
            "total": len(matching),
            "offset": offset,
            "limit": limit,
            "rows": self.read(matching[offset : offset + limit]),
        }


@dataclass
class Dataset:
    family: str
    root: Path
    manifest: dict | None
    manifest_sha256: str | None
    pinned: bool
    artifacts: dict[str, ArtifactMeta]
    json_files: dict
    tables: dict[str, Table]

    @property
    def code_sha(self) -> str:
        return (
            self.manifest["code_sha"]
            if self.manifest
            else self.json_files["evidence.json"]["code_sha"]
        )

    def metadata(self) -> dict:
        return {
            "id": self.family,
            "classification": "SYNTHETIC",
            "declared_code_sha": self.code_sha,
            "manifest_sha256": self.manifest_sha256,
            "verification": "independently-pinned-digest"
            if self.pinned
            else "manifest-consistency"
            if self.manifest
            else "fixture-reference-only",
            "experiment": self.manifest["experiment_id"] if self.manifest else "golden-replay-v1",
            "scenarios": self.manifest.get(
                "scenarios", self.manifest.get("scenario_replications", [])
            )
            if self.manifest
            else [],
            "row_count": self.manifest.get("primary_rows", self.manifest.get("row_count"))
            if self.manifest
            else None,
            "metric_versions": self.manifest["versions"]
            if self.manifest
            else self.json_files["evidence.json"]["metric_versions"],
            "artifacts": self.artifacts,
        }


def classify(name: str) -> str:
    if name.startswith("input-") or name == "truth-inputs.jsonl":
        return "synthetic-source"
    return "research-evidence" if name.startswith("evidence") else "derived"


def scan_lines(path: Path, validator) -> Table:
    filters = []
    offsets = []
    with path.open("rb") as file:
        while True:
            offset = file.tell()
            line = file.readline(MAX_LINE + 1)
            if not line:
                break
            require(len(line) <= MAX_LINE and len(offsets) < 20_000, "JSONL row limit exceeded")
            row = decode(line)
            validator(row)
            offsets.append(offset)
            filters.append(filter_values(row))
    return Table(filters, path=path, offsets=offsets)


def assert_input(row):
    obj = object_keys(row, {"input_sha256", "input"})
    content = object_keys(
        obj["input"], {"version", "provenance", "cohorts", "scenario", "specs", "factors"}
    )
    require(
        content["version"] == "p21-factorial-truth-v1" and content["provenance"] == "SYNTHETIC",
        "Unsupported source schema",
    )
    specs = instrument_versions(content["specs"])
    for cohort in objects(content["cohorts"], max_items=4):
        for source in objects(
            object_keys(cohort, {"histories", "start_ns", "end_ns"})["histories"], max_items=4
        ):
            history(source, specs)
    validate_fields(row)
    require(
        hashlib.sha256(json_bytes(content)).hexdigest() == obj["input_sha256"],
        "Input hash mismatch",
    )


def load_dataset(family: str, source: Path, target: Path, pin: str | None) -> Dataset:
    source = source.resolve(strict=True)
    target.mkdir()
    if pin is not None:
        require(matches(SHA, pin), "Expected a lowercase SHA-256 pin")
    if family == "p1":
        meta = snapshot(source / "evidence.json", target / "evidence.json", PACKET_LIMIT, pin)
        packet = decode((target / "evidence.json").read_bytes())
        evidence(packet, "p1")
        require(
            len(packet["inputs"]) == 1 and packet["inputs"][0]["sha256"] == FIXTURE_SHA256,
            "P1 fixture reference mismatch",
        )
        return Dataset(
            family,
            target,
            None,
            None,
            pin is not None,
            {"evidence.json": {**meta, "classification": "research-evidence"}},
            {"evidence.json": packet},
            {},
        )

    p2 = family == "p2"
    manifest_meta = snapshot(source / "manifest.json", target / "manifest.json", 256 * 1024, pin)
    m = object_keys(
        decode((target / "manifest.json").read_bytes()),
        {
            "manifest_version",
            "experiment_id",
            "code_sha",
            "versions",
            "artifacts",
            "lock_sha256",
            "row_count" if p2 else "primary_rows",
            "scenarios" if p2 else "scenario_replications",
        },
    )
    require(
        m["manifest_version"] == f"{family}-experiment-manifest-v1"
        and m["experiment_id"]
        == ("p2-synthetic-robustness-v1" if p2 else "p21-factorial-identifiability-v1")
        and matches(COMMIT, m["code_sha"]),
        "Unsupported experiment manifest",
    )
    check_versions(
        m["versions"],
        (P2 | {"p2-synthetic-history-v1"}) if p2 else (P21 | {"p21-factorial-truth-v1"}),
    )
    check_versions(
        m["scenarios" if p2 else "scenario_replications"], set(P2_NAMES if p2 else P21_NAMES)
    )
    require(
        isinstance(m["artifacts"], dict)
        and m["artifacts"].keys() == (P2_FILES if p2 else P21_FILES),
        "Unexpected artifact inventory",
    )
    validate_fields(m)
    require(
        all(isinstance(x, dict) and is_count(x.get("bytes")) for x in m["artifacts"].values()),
        "Invalid artifact sizes",
    )
    require(
        sum(x["bytes"] for x in m["artifacts"].values()) <= MAX_FILE, "Dataset exceeds size limit"
    )

    metadatas = {}
    decoded = {}
    for name, entry in sorted(m["artifacts"].items()):
        require(
            matches(NAME, name) and matches(SHA, entry.get("sha256")),
            "Invalid artifact path or hash",
        )
        meta = snapshot(source / name, target / name, file_limit(name), entry["sha256"])
        require(meta["bytes"] == entry["bytes"], "Manifest byte count mismatch")
        metadatas[name] = {**meta, "classification": classify(name)}
        if name.endswith(".json"):
            value = decode((target / name).read_bytes())
            validate_fields(value)
            decoded[name] = value
    tables = {}
    if p2:
        for row in objects(decoded["results.json"]):
            row_config(row, family)
        for name in (f"input-{scenario}.json" for scenario in P2_NAMES):
            obj = object_keys(decoded[name], {"version", "provenance", "scenario", "specs"})
            require(
                obj["version"] == "p2-synthetic-history-v1" and obj["provenance"] == "SYNTHETIC",
                "Unsupported P2 input format",
            )
            specs = instrument_versions(obj["specs"])
            for source in objects(
                object_keys(obj["scenario"], {"histories"})["histories"], max_items=4
            ):
                history(source, specs)
    else:
        tables["truth"] = scan_lines(target / "truth-inputs.jsonl", assert_input)
        fingerprints = {row["input_sha256"] for row in tables["truth"].filters}
        require(
            len(fingerprints) == len(tables["truth"].filters) == m.get("unique_frozen_histories"),
            "Truth inventory mismatch",
        )

        def p21_check(row, *, asof=False):
            row_config(row, family, asof=asof)
            require(row["input_sha256"] in fingerprints, "Unlinked synthetic input")
            require(
                asof or row["broker"]["tolerance_ms"] == m.get("primary_asof_ms"),
                "Primary tolerance mismatch",
            )

        tables["p21"] = scan_lines(target / "results.jsonl", p21_check)
        tables["p21-asof"] = scan_lines(
            target / "asof-results.jsonl", lambda row: p21_check(row, asof=True)
        )
        for item in objects(decoded["identifiability.json"]):
            object_keys(
                item,
                {
                    "id",
                    "quiet",
                    "hidden",
                    "shared_sample",
                    "sample_sha256",
                    "observationally_equal",
                },
            )
            require(
                item["observationally_equal"] is True
                and hashlib.sha256(json_bytes(item["shared_sample"])).hexdigest()
                == item["sample_sha256"],
                "Unlinked shared sample",
            )
            for row in objects(
                object_keys(
                    object_keys(item["shared_sample"], {"stream"})["stream"], {"observations"}
                )["observations"],
                max_items=256,
            ):
                quote(row)
            for name in ("quiet", "hidden"):
                member = object_keys(
                    item[name], {"truth", "truth_sha256", "episodes", "oracle_tail"}
                )
                history(member["truth"])
                require(
                    is_count(member["episodes"])
                    and hashlib.sha256(json_bytes(member["truth"])).hexdigest()
                    == member["truth_sha256"],
                    "Unlinked counterexample truth",
                )

    for name, value in decoded.items():
        if not name.startswith("evidence"):
            continue
        evidence(value, family, m["code_sha"])
        parameters = dict(value["parameters"])
        if p2:
            scenario = name.removeprefix("evidence-").removesuffix(".json")
            input_name = f"input-{scenario}.json"
            require(
                parameters.get("results_sha256") == metadatas["results.json"]["sha256"]
                and len(value["inputs"]) == 1
                and value["inputs"][0]["fixture_id"] == scenario
                and value["inputs"][0]["sha256"] == metadatas[input_name]["sha256"]
                and object_keys(m.get("inputs"), {scenario})[scenario]
                == {
                    "artifact": input_name,
                    "sha256": metadatas[input_name]["sha256"],
                },
                "P2 evidence references do not match",
            )
        else:
            require(
                len(value["inputs"]) == 1
                and value["inputs"][0]["sha256"] == metadatas["truth-inputs.jsonl"]["sha256"]
                and all(
                    parameters.get(k) == item["sha256"]
                    for k, item in metadatas.items()
                    if k != "evidence.json"
                ),
                "P2.1 evidence references do not match",
            )

    for name, (owner, filename, member) in TABLES.items():
        if owner == family and name not in tables:
            data = decoded[filename]
            rows = objects(object_keys(data, {member})[member] if member is not None else data)
            for row in rows:
                published_row(name, row)
            tables[name] = Table([filter_values(row) for row in rows], rows)
    table = tables[family]
    keys = {tuple(sorted(item.items())) for item in table.filters}
    require(len(keys) == len(table.filters), "Duplicate configuration row")
    require(
        is_count(m["row_count" if p2 else "primary_rows"])
        and len(table.filters) == m["row_count" if p2 else "primary_rows"],
        "Row count mismatch",
    )
    return Dataset(
        family, target, m, manifest_meta["sha256"], pin is not None, metadatas, decoded, tables
    )


def request_query(raw: str) -> dict:
    pairs = parse_qsl(raw, strict_parsing=True, max_num_fields=12, keep_blank_values=True)
    result = dict(pairs)
    require(len(result) == len(pairs), "Duplicate query parameter")
    return result


def page_query(query: dict, table: Table) -> tuple[dict, int, int]:
    query = dict(query)
    offset = query.pop("offset", "0")
    limit = query.pop("limit", "24")
    require(offset.isascii() and offset.isdecimal() and len(offset) <= 5, "Invalid offset")
    require(
        limit.isascii() and limit.isdecimal() and len(limit) <= 3 and 1 <= int(limit) <= 100,
        "Invalid limit (1–100)",
    )
    supported = {key for row in table.filters for key in row}
    filters = {}
    for key, value in query.items():
        require(key in supported, f"Unsupported filter {key}")
        if key in FACTORS:
            require(value in {str(item) for item in FACTORS[key]}, f"Invalid value for {key}")
            filters[key] = int(value)
        else:
            require(
                (key == "scenario" and value in {*P2_NAMES, *P21_NAMES})
                or (key == "tail" and value in {"p95", "p99"})
                or (key == "input_sha256" and matches(SHA, value)),
                f"Invalid value for {key}",
            )
            filters[key] = value
    return filters, int(offset), int(limit)


@dataclass
class Observatory:
    datasets: dict[str, Dataset]
    web: Path | None = None

    def table(self, name: str) -> tuple[Dataset, str, Table]:
        if name not in TABLES:
            raise KeyError(name)
        family, filename, _ = TABLES[name]
        dataset = self.datasets[family]
        return dataset, filename, dataset.tables[name]

    def envelope(self, name: str, query: dict, ordinal: str | None = None) -> dict:
        dataset, filename, table = self.table(name)
        if ordinal is not None:
            require(
                not query and ordinal.isascii() and ordinal.isdecimal() and len(ordinal) <= 5,
                "Invalid row ordinal",
            )
            index = int(ordinal)
            if not 0 <= index < len(table.filters):
                raise KeyError(index)
            data = {"row": table.read([index])[0]}
        else:
            filters, offset, limit = page_query(query, table)
            data = {"filters": filters, **table.page(filters, offset, limit)}
        return {
            "api_version": API_VERSION,
            "dataset": dataset.family,
            "table": name,
            "classification": "SYNTHETIC",
            "source_experiment": dataset.metadata()["experiment"],
            "manifest_sha256": dataset.manifest_sha256,
            "declared_code_sha": dataset.code_sha,
            "artifact": filename,
            "artifact_sha256": dataset.artifacts[filename]["sha256"],
            "metric_versions": dataset.metadata()["metric_versions"],
            **data,
        }

    def dispatch(self, path: str, query: dict) -> tuple[bytes | Path, str, str | None]:
        parts = path.split("/")
        if path == "/api/v1/health" and not query:
            return (
                json_bytes(
                    {
                        "status": "ready",
                        "api_version": API_VERSION,
                        "mode": "read-only",
                        "classification": "SYNTHETIC",
                        "datasets": sorted(self.datasets),
                    }
                ),
                "application/json",
                None,
            )
        if path == "/api/v1/datasets" and not query:
            return (
                json_bytes(
                    {
                        "api_version": API_VERSION,
                        "datasets": [self.datasets[k].metadata() for k in sorted(self.datasets)],
                    }
                ),
                "application/json",
                None,
            )
        if len(parts) == 5 and parts[:4] == ["", "api", "v1", "provenance"] and not query:
            d = self.datasets[parts[4]]
            return json_bytes({**d.metadata(), "manifest": d.manifest}), "application/json", None
        if len(parts) == 5 and parts[:4] == ["", "api", "v1", "evidence"] and not query:
            d = self.datasets[parts[4]]
            return (
                json_bytes(
                    {
                        "dataset": d.family,
                        "packets": [
                            {"name": name, "sha256": d.artifacts[name]["sha256"], "packet": value}
                            for name, value in sorted(d.json_files.items())
                            if name.startswith("evidence")
                        ],
                    }
                ),
                "application/json",
                None,
            )
        if len(parts) == 6 and parts[:4] == ["", "api", "v1", "artifact"] and not query:
            d = self.datasets[parts[4]]
            name = parts[5]
            # JSONL is only served through bounded table routes.
            if (name == "manifest.json" and d.manifest is not None) or (
                name in d.artifacts and name.startswith("evidence")
            ):
                return d.root / name, "application/json", name
            raise KeyError(name)
        if len(parts) == 5 and parts[:3] == ["", "api", "v1"] and parts[3] in {"table", "export"}:
            name = parts[4]
            if parts[3] == "table":
                return json_bytes(self.envelope(name, query)), "application/json", None
            filters = dict(query)
            metric = filters.pop("view_metric", None)
            session = filters.pop("view_session", None)
            require(
                metric is None
                or metric in {"recall", "revisions", "coverage", "consensus", "tail"},
                "Invalid view metric",
            )
            require(
                session is None or re.fullmatch(r"[a-zA-Z0-9_-]{1,96}", session),
                "Invalid view session",
            )
            result = self.envelope(name, filters)
            if metric is not None or session is not None:
                result["view"] = {
                    "version": "p3-display-v1",
                    "metric": metric,
                    "session_id": session,
                }
            return json_bytes(result), "application/json", f"{name}-filtered.json"
        if len(parts) == 6 and parts[:4] == ["", "api", "v1", "row"]:
            return json_bytes(self.envelope(parts[4], query, parts[5])), "application/json", None
        if (
            self.web is not None
            and not query
            and (path == "/" or ASSETS.fullmatch(path.removeprefix("/")))
        ):
            file = self.web / ("index.html" if path == "/" else path[1:])
            if file.is_file() and file.resolve() == file:
                mime = {
                    ".html": "text/html; charset=utf-8",
                    ".css": "text/css",
                    ".js": "text/javascript",
                }
                return file, mime.get(file.suffix, "application/octet-stream"), None
        raise KeyError(path)


def handler(app: Observatory):
    class LocalHandler(BaseHTTPRequestHandler):
        def respond(self, status, value, content_type="application/json", download=None):
            length = value.stat().st_size if isinstance(value, Path) else len(value)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                "connect-src 'self'; font-src 'self'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'none'",
            )
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self.end_headers()
            if self.command != "HEAD":
                if isinstance(value, Path):
                    with value.open("rb") as file:
                        while block := file.read(256 * 1024):
                            self.wfile.write(block)
                else:
                    self.wfile.write(value)

        def do_GET(self):  # noqa: N802
            port = self.server.server_port
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            host = self.headers.get_all("Host", [])
            origin = self.headers.get("Origin")
            if (
                len(host) != 1
                or host[0] not in hosts
                or origin is not None
                and origin != f"http://{host[0]}"
                or self.headers.get("Sec-Fetch-Site") == "cross-site"
            ):
                self.respond(403, json_bytes({"error": "Loopback same-origin required"}))
                return
            try:
                require(len(self.path) <= 2048, "Request too long")
                url = urlsplit(self.path)
                require(not url.netloc and not url.scheme and "%" not in url.path, "Invalid path")
                result = app.dispatch(url.path, request_query(url.query))
            except KeyError:
                self.respond(404, json_bytes({"error": "Unknown resource"}))
            except ValueError as exc:
                self.respond(400, json_bytes({"error": str(exc)}))
            else:
                self.respond(200, *result)

        do_HEAD = do_GET

        def do_POST(self):  # noqa: N802
            self.respond(405, json_bytes({"error": "Read-only endpoint"}))

        do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_POST

        def log_message(self, *_args):
            pass

    return LocalHandler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for family in ("p1", "p2", "p21"):
        parser.add_argument(f"--{family}", type=Path, required=True)
        parser.add_argument(
            f"--{family}-sha256", help="Trusted manifest digest (P1 evidence digest)"
        )
    parser.add_argument("--web", type=Path, default=Path("web/dist"))
    parser.add_argument("--host", choices=("127.0.0.1",), default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--shutdown-on-stdin", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    try:
        with TemporaryDirectory(prefix="xauusd-observatory-") as cache:
            datasets = {
                family: load_dataset(
                    family,
                    getattr(args, family),
                    Path(cache) / family,
                    getattr(args, f"{family}_sha256"),
                )
                for family in ("p1", "p2", "p21")
            }
            web = args.web.resolve(strict=True)
            require((web / "index.html").is_file(), "Build the frontend first")
            app = Observatory(datasets, web)
            with ThreadingHTTPServer((args.host, args.port), handler(app)) as server:
                if args.shutdown_on_stdin:

                    def wait_for_parent():
                        sys.stdin.readline()
                        server.shutdown()

                    Thread(target=wait_for_parent, daemon=True).start()
                print(
                    f"Synthetic Research Observatory http://127.0.0.1:{server.server_port}",
                    flush=True,
                )
                server.serve_forever()
    except KeyboardInterrupt:
        return
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Observatory startup: {exc}") from None


if __name__ == "__main__":
    main()
