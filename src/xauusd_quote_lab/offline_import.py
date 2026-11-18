"""Strict offline synthetic validation with receipts isolated from research inputs."""

import argparse
import hashlib
import os
import re
import stat
from collections import Counter
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path

from .observatory_schema import InvalidArtifact, decode
from .quality import parse_price

SCHEMA = "offline-quote-jsonl-v1"
REPORT = "offline-dataset-validation-report-v1"
ENVIRONMENTS = {"MOCK", "REAL", "DEMO", "UNKNOWN"}
MAX_BYTES = 8 * 1024 * 1024
MAX_MANIFEST = 32 * 1024
MAX_ROW = 4096
MAX_ROWS = 50_000
HASH = re.compile(r"[0-9a-f]{64}")
CLOCK_TICK = re.compile(r"(?:0|[1-9][0-9]{0,18})")
DECIMAL = re.compile(r"-?[0-9]{1,32}(?:\.[0-9]{1,32})?")
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,95}")
ROW_FIELDS = {
    "sequence",
    "bid",
    "ask",
    "source_time_ms",
    "received_wall_ns",
    "processing_wall_ns",
    "received_monotonic_ns",
}
MANIFEST_FIELDS = {
    "schema_version",
    "source",
    "environment",
    "provenance_class",
    "authorization",
    "instrument",
    "clocks",
    "session_id",
    "data_file",
    "source_sha256",
    "processing",
}
META = {
    "source": {"identity", "acquisition_method"},
    "authorization": {"decision", "license_or_permission"},
    "instrument": {"symbol", "price_unit", "quote_currency", "spec_version"},
    "clocks": {
        "source_domain",
        "receive_domain",
        "processing_domain",
        "monotonic_domain",
        "source_comparable_to_receive",
    },
    "processing": {"producer", "policy_version", "transformations"},
}


@dataclass(frozen=True, slots=True)
class OfflineDatasetValidationReport:
    version: str
    manifest_sha256: str | None
    source_sha256: str | None
    environment: str
    total_rows: int
    parsed_rows: int
    accepted_rows: int
    rejected_rows: int
    scan_complete: bool
    quality_flags: dict[str, int]
    missing_provenance: tuple[str, ...]
    timestamp_diagnostics: dict
    unit_compatibility: str
    issues: tuple[str, ...]
    admissibility: str


def read_local(root: Path, name: str, limit: int) -> bytes:
    path = root / name
    if not path.is_file() or path.is_symlink() or path.resolve() != path:
        raise InvalidArtifact("missing_or_unsafe_file")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(os.open(path, flags), "rb") as file:
        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
            raise InvalidArtifact("missing_or_unsafe_file")
        data = file.read(limit + 1)
    if len(data) > limit:
        raise InvalidArtifact("file_oversized")
    return data


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def label(value: object) -> bool:
    return isinstance(value, str) and LABEL.fullmatch(value) is not None


def manifest_fields(manifest: dict) -> tuple[list[str], bool]:
    missing = sorted(MANIFEST_FIELDS - manifest.keys())
    unknown = not manifest.keys() <= MANIFEST_FIELDS
    for root, fields in META.items():
        section = manifest.get(root)
        if root not in manifest:
            continue
        if not isinstance(section, dict):
            missing.append(root)
            continue
        missing.extend(f"{root}.{field}" for field in sorted(fields - section.keys()))
        unknown |= not section.keys() <= fields
    return sorted(missing), unknown


def valid_metadata(m: dict) -> bool:
    s, license_, spec, clocks, p = (
        m[k] for k in ("source", "authorization", "instrument", "clocks", "processing")
    )
    return (
        all(
            label(value)
            for value in (
                s["identity"],
                license_["license_or_permission"],
                spec["symbol"],
                spec["spec_version"],
                clocks["receive_domain"],
                clocks["processing_domain"],
                p["producer"],
                m["session_id"],
            )
        )
        and s["acquisition_method"] in ("SYNTHETIC_GENERATOR", "OFFLINE_EXPORT", "UNKNOWN")
        and license_["decision"] in ("AUTHORIZED", "UNDECLARED")
        and m["environment"] in ("MOCK", "REAL", "DEMO", "UNKNOWN")
        and m["provenance_class"] in ("SYNTHETIC", "EXTERNAL", "UNKNOWN")
        and spec["price_unit"] in ("USD_PER_TROY_OUNCE", "UNKNOWN")
        and spec["quote_currency"] in ("USD", None)
        and all(
            value is None or label(value)
            for value in (clocks["source_domain"], clocks["monotonic_domain"])
        )
        and type(clocks["source_comparable_to_receive"]) is bool
        and (not clocks["source_comparable_to_receive"] or clocks["source_domain"] is not None)
        and p["policy_version"] == "raw-v1"
        and p["transformations"] == []
        and isinstance(m["source_sha256"], str)
        and HASH.fullmatch(m["source_sha256"]) is not None
    )


def clock(value, *, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not CLOCK_TICK.fullmatch(value) or int(value) > 2**63 - 1:
        raise InvalidArtifact("invalid_timestamp_encoding")
    return int(value)


def row_shape(row):
    if not isinstance(row, dict) or row.keys() != ROW_FIELDS:
        raise InvalidArtifact("row_schema_mismatch")
    if type(row["sequence"]) is not int or not 0 <= row["sequence"] <= 2**53 - 1:
        raise InvalidArtifact("invalid_sequence_encoding")
    for side in ("bid", "ask"):
        value = row[side]
        if value is not None and (not isinstance(value, str) or not DECIMAL.fullmatch(value)):
            raise InvalidArtifact("invalid_decimal_encoding")
    return (
        clock(row["source_time_ms"], nullable=True),
        clock(row["received_wall_ns"]),
        clock(row["processing_wall_ns"]),
        clock(row["received_monotonic_ns"], nullable=True),
    )


def check_rows(data: bytes, clocks: dict) -> tuple[int, int, int, bool, Counter, Counter]:
    source = BytesIO(data)
    counts: Counter[str] = Counter()
    timing: Counter[str] = Counter()
    total = parsed = accepted = 0
    seq_high = receive_high = process_high = source_high = mono_high = -1
    previous = None
    complete = True
    while line := source.readline(MAX_ROW + 1):
        if total == MAX_ROWS:
            counts["row_limit_exceeded"] += 1
            complete = False
            break
        total += 1
        if len(line) > MAX_ROW:
            counts["row_oversized"] += 1
            complete = False
            break
        try:
            row = decode(line)
            source_ms, receive, process, mono = row_shape(row)
        except InvalidArtifact as error:
            name = str(error)
            counts[
                name
                if name
                in {
                    "row_schema_mismatch",
                    "invalid_timestamp_encoding",
                    "invalid_sequence_encoding",
                    "invalid_decimal_encoding",
                }
                else "invalid_json"
            ] += 1
            previous = None
            continue

        parsed += 1
        flags = set()
        row_time = set()
        bid, ask = parse_price(row["bid"]), parse_price(row["ask"])
        for side, price in (("bid", bid), ("ask", ask)):
            if price is None:
                flags.add(f"missing_{side}" if row[side] is None else f"invalid_{side}")
        if bid is not None and ask is not None and bid > ask:
            flags.add("crossed")
        if row["sequence"] <= seq_high:
            row_time.add("sequence_not_increasing")
        if receive < receive_high:
            row_time.add("receive_clock_reversal")
        if process < process_high:
            row_time.add("processing_clock_reversal")
        if clocks["receive_domain"] == clocks["processing_domain"] and process < receive:
            row_time.add("processing_before_receive")
        if source_ms is None:
            timing["source_missing"] += 1
        else:
            if clocks["source_domain"] is None:
                row_time.add("undeclared_source_clock")
            if source_ms < source_high:
                row_time.add("source_clock_reversal")
            if clocks["source_comparable_to_receive"] and source_ms * 1_000_000 > receive:
                row_time.add("future_source_timestamp")
            if "future_source_timestamp" not in row_time:
                source_high = max(source_high, source_ms)
        if mono is not None:
            if clocks["monotonic_domain"] is None:
                row_time.add("undeclared_monotonic_clock")
            if mono < mono_high:
                row_time.add("monotonic_clock_reversal")
            mono_high = max(mono_high, mono)
        flags.update(row_time)
        timing.update(row_time)
        seq_high = max(seq_high, row["sequence"])
        receive_high = max(receive_high, receive)
        process_high = max(process_high, process)
        if not flags:
            accepted += 1
            prices = (bid, ask)
            if previous == prices:
                flags.add("duplicate_snapshot")
            previous = prices
        else:
            previous = None
        counts.update(flags)
    return total, parsed, accepted, complete, counts, timing


def validate(directory: Path) -> OfflineDatasetValidationReport:
    manifest_sha = source_sha = None
    environment, unit = "UNKNOWN", "UNKNOWN"
    missing: list[str] = []
    issues: list[str] = []
    totals = (0, 0, 0, False, Counter(), Counter())
    clocks = {}
    try:
        root = directory.resolve(strict=True)
        content = read_local(root, "manifest.json", MAX_MANIFEST)
        manifest_sha = digest(content)
        m = decode(content)
        if not isinstance(m, dict):
            raise InvalidArtifact("manifest_schema_mismatch")
        candidate = m.get("environment")
        environment = (
            candidate if isinstance(candidate, str) and candidate in ENVIRONMENTS else "UNKNOWN"
        )
        missing, extra = manifest_fields(m)
        if missing:
            issues.append("missing_provenance")
        if extra:
            issues.append("undeclared_manifest_fields")
        if m.get("schema_version") != SCHEMA:
            issues.append("unsupported_schema")
        if m.get("data_file") != "observations.jsonl":
            issues.append("unsafe_data_reference")
        if not issues and not valid_metadata(m):
            issues.append("invalid_metadata")
        if not issues:
            spec = m["instrument"]
            if spec["price_unit"] == "UNKNOWN":
                issues.append("unknown_unit")
            elif (spec["symbol"], spec["quote_currency"]) != ("XAUUSD", "USD"):
                unit = "INCOMPATIBLE"
                issues.append("incompatible_instrument_or_unit")
            else:
                unit = "USD_PER_TROY_OUNCE"
            if m["authorization"]["decision"] != "AUTHORIZED":
                issues.append("authorization_not_declared")
            safe_synthetic = (
                environment == "MOCK"
                and m["provenance_class"] == "SYNTHETIC"
                and m["source"]["acquisition_method"] == "SYNTHETIC_GENERATOR"
            )
            if not safe_synthetic:
                issues.append("external_environment_quarantined")
            # Hash non-synthetic files locally for identification without parsing observations.
            data = read_local(root, m["data_file"], MAX_BYTES)
            source_sha = digest(data)
            if source_sha != m["source_sha256"]:
                issues.append("source_digest_mismatch")
            elif safe_synthetic and m["authorization"]["decision"] == "AUTHORIZED":
                clocks = m["clocks"]
                totals = check_rows(data, clocks)
                if not totals[3]:
                    issues.append("incomplete_scan")
                if totals[0] == 0 or totals[0] != totals[2]:
                    issues.append("invalid_or_empty_rows")
    except InvalidArtifact as error:
        name = str(error)
        issues.append(
            name
            if name
            in (
                "file_oversized",
                "missing_or_unsafe_file",
                "manifest_schema_mismatch",
            )
            else "invalid_manifest_json"
        )
    except (OSError, RuntimeError):
        issues.append("unreadable_dataset")
    total, parsed, accepted, complete, flags, timing = totals
    return OfflineDatasetValidationReport(
        REPORT,
        manifest_sha,
        source_sha,
        environment,
        total,
        parsed,
        accepted,
        total - accepted,
        complete,
        dict(sorted(flags.items())),
        tuple(missing),
        {
            "source_vs_receive_assessed": bool(clocks.get("source_comparable_to_receive")),
            "processing_vs_receive_assessed": bool(clocks)
            and clocks["processing_domain"] == clocks["receive_domain"],
            "counts": dict(sorted(timing.items())),
        },
        unit,
        tuple(issues),
        "QUARANTINED" if issues else "SYNTHETIC_VALIDATED_NO_PROMOTION",
    )


def save_receipt(report: OfflineDatasetValidationReport, directory: Path) -> Path:
    from .observatory import json_bytes

    root = directory.resolve()
    bucket = root / ("quarantine" if report.admissibility == "QUARANTINED" else "validated")
    if bucket.is_symlink():
        raise InvalidArtifact("unsafe_receipt_directory")
    bucket.mkdir(parents=True, exist_ok=True)
    data = json_bytes(asdict(report))
    path = bucket / f"{digest(data)}.json"
    try:
        with path.open("xb") as file:
            file.write(data)
    except FileExistsError:
        if path.is_symlink() or read_local(bucket, path.name, 64 * 1024) != data:
            raise InvalidArtifact("existing_receipt_mismatch") from None
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--reports", type=Path, required=True)
    args = parser.parse_args(argv)
    report = validate(args.dataset)
    try:
        save_receipt(report, args.reports)
    except (OSError, InvalidArtifact):
        raise SystemExit("Offline validation receipt could not be written") from None
    from .observatory import json_bytes

    print(json_bytes(asdict(report)).decode("ascii"), end="")
    if report.admissibility == "QUARANTINED":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
