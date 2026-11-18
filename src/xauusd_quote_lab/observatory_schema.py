"""Read-only P3 wire schemas for the published synthetic runner formats."""

import json
import re
from decimal import Decimal
from typing import NotRequired, TypedDict

from .contracts import Flag

SHA = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
DECIMAL = re.compile(r"-?[0-9]{1,130}(?:\.[0-9]{1,160})?(?:[Ee][+-]?[0-9]{1,3})?")
INTEGER_TEXT = re.compile(r"-?(?:0|[1-9][0-9]{0,29})")
P1 = {"quote-dynamics-v1.1", "broker-comparison-v1.1"}
P2 = P1 | {"p2-poll-v1", "p2-sampling-metrics-v1"}
P21 = P2 | {"p21-tail-decomposition-v1", "p21-ideal-intersection-v1"}
BASE_SCHEMA = {"broker-source-v1", "instrument-spec-v1", "quote-observation-v1", "quality-state-v1"}
P2_NAMES = ("asynchronous", "clocks-metadata", "gaps", "persistent", "short-spike", "stable")
P21_NAMES = ("isolated", "clustered", "asynchronous", "gaps", "session-spec", "clocks")
FACTORS = {
    "interval_ms": {100, 250, 500, 1000},
    "tolerance_ms": {100, 250, 500, 1000},
    "phase_percent": {0, 25, 50, 75},
    "duration_ms": {25, 50, 100, 250, 500, 1000},
    "transport_ms": {0, 25, 100, 250},
    "processing_ms": {0, 25, 100},
}
STATUSES = {"FACT", "MEASUREMENT", "INFERENCE", "HYPOTHESIS", "UNKNOWN", "REJECTED"}
REASONS = {flag.value for flag in Flag} | {
    "fewer_than_three_eligible_brokers",
    "instrument_spec_changed",
    "window_end",
    "disconnected",
    "future_source_time",
    "receive_and_processing_reversed",
    "session_closed",
    "no_truth_episodes",
    "no_truth_revisions",
    "missing_duration_support",
    "left_censored",
    "right_censored",
    "censored_edge",
    "no_eligible_snapshots",
    "no_covered_duration",
    "missing_sampled_support",
    "missing_snapshot_or_oracle_support",
    "no_supported_pairs",
    "missing_sample_or_oracle_support",
}
RATIOS = {
    "recall",
    "coverage",
    "revision_recall",
    "event_recall",
    "valid_coverage",
    "duration_coverage",
    "consensus_coverage",
    "broker_coverage",
    "asynchronous_broker_coverage",
    "asynchronous_consensus_coverage",
    "finite_grid_probability",
    "continuous_uniform_probability",
}
TAIL_KEYS = {
    "oracle_duration",
    "sampled_duration",
    "sampled_snapshot",
    "duration_to_duration",
    "snapshot_vs_duration_weighting",
    "original_cross_estimand",
}


class InvalidArtifact(ValueError):
    pass


class ArtifactMeta(TypedDict):
    sha256: str
    bytes: int
    classification: NotRequired[str]


class Row(TypedDict):
    ordinal: int
    data: dict


def require(condition: object, message: str) -> None:
    if not condition:
        raise InvalidArtifact(message)


def object_keys(value: object, keys: set[str]) -> dict:
    require(isinstance(value, dict) and keys <= value.keys(), "Missing or invalid object fields")
    return value


def objects(value: object, *, max_items: int = 20_000) -> list[dict]:
    require(
        isinstance(value, list)
        and len(value) <= max_items
        and all(isinstance(item, dict) for item in value),
        "Invalid object array",
    )
    return value


def matches(pattern: re.Pattern, value: object) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def is_count(value: object) -> bool:
    return type(value) is int and 0 <= value <= 2**53 - 1


def decode(data: bytes):
    def unique(pairs):
        result = dict(pairs)
        require(len(result) == len(pairs), "Duplicate JSON field")
        return result

    def reject(_: str):
        raise InvalidArtifact("Numeric research values must use exact JSON strings")

    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=unique,
            parse_float=reject,
            parse_constant=reject,
        )
    except (UnicodeError, ValueError, RecursionError) as error:
        raise InvalidArtifact(f"Invalid JSON: {error}") from None


def check_decimal(value, *, ratio=False):
    if value is None:
        return
    require(matches(DECIMAL, value), "Invalid decimal wire value")
    if ratio:
        require(0 <= Decimal(value) <= 1, "Ratio outside 0..1")


def reason(value):
    require(
        isinstance(value, str) and all(part in REASONS for part in value.split(",")),
        "Unknown reason code",
    )


def validate_fields(value, *, key="", depth=0):
    """Validate common wire units recursively before table-specific validation."""
    require(depth < 40, "Excessive JSON depth")
    if isinstance(value, list):
        require(len(value) <= 20_000, "Excessive collection length")
        for item in value:
            validate_fields(item, key=key, depth=depth + 1)
    elif isinstance(value, dict):
        if key == "unavailable":
            for label in value.values():
                reason(label)
            return
        if key in {
            "exclusions",
            "sampled_exclusions",
            "oracle_exclusions",
            "sampled_exclusion_counts",
            "oracle_exclusion_counts",
        }:
            for label, total in value.items():
                reason(label)
                require(is_count(total), "Invalid exclusion count")
        for name, item in value.items():
            validate_fields(item, key=name, depth=depth + 1)
    elif value is not None:
        if key.endswith("_ns"):
            require(matches(INTEGER_TEXT, value), "Expected exact nanosecond string")
            require("error" in key or not value.startswith("-"), "Negative absolute timestamp")
        elif key in RATIOS:
            check_decimal(value, ratio=True)
        elif (
            key in TAIL_KEYS
            or key
            in {
                "median_mid",
                "median_spread",
                "mid_difference",
                "spread_difference",
                "bid_text",
                "ask_text",
                "oracle_tail",
                "snapshot_mean",
                "duration_mean",
                "snapshot_p95",
                "snapshot_p99",
                "duration_p95",
                "duration_p99",
                "observed_per_covered_second",
                "point_size",
                "tick_size",
                "contract_size",
                "widening_threshold",
                "threshold_usd_per_troy_ounce",
                "signed",
                "absolute",
            }
            or key.endswith(("_p95_error", "_p99_error"))
        ):
            check_decimal(value)
        elif key in (
            "censor_reason",
            "truth_exclusion",
            "reasons",
            "quality_flags",
            "unavailable",
        ) or key.endswith("_unavailable"):
            reason(value)
        elif key.endswith("sha256"):
            require(matches(SHA, value), "Invalid SHA-256")
        elif type(value) is int:
            require(abs(value) <= 2**53 - 1, "Unsafe integer; use string wire format")
        elif not isinstance(value, (str, bool)):
            raise InvalidArtifact("Unsupported JSON value")


def check_versions(values, expected: set[str]):
    require(
        isinstance(values, list)
        and all(isinstance(v, str) for v in values)
        and set(values) == expected
        and len(values) == len(expected),
        "Unsupported versions",
    )


def evidence(packet, family: str, code_sha: str | None = None):
    p = object_keys(
        packet,
        {
            "version",
            "code_sha",
            "schema_versions",
            "metric_versions",
            "inputs",
            "findings",
            "candidate_explanations",
            "created_wall_ns",
            "parameters",
            "exclusion_counts",
            "eligible_source_count",
            "clock_assumptions",
            "limitations",
            "falsifiers",
            "research_id",
            "question",
        },
    )
    require(
        p["version"] == "research-evidence-packet-v1" and matches(COMMIT, p["code_sha"]),
        "Unsupported packet schema or invalid commit",
    )
    require(code_sha is None or p["code_sha"] == code_sha, "Evidence code reference mismatch")
    schemas = {
        "p1": BASE_SCHEMA,
        "p2": BASE_SCHEMA | {"p2-synthetic-history-v1"},
        "p21": {"p21-factorial-truth-v1", "p21-results-v1"},
    }
    check_versions(p["schema_versions"], schemas[family])
    check_versions(p["metric_versions"], {"p1": P1, "p2": P2, "p21": P21}[family])
    require(
        matches(INTEGER_TEXT, p["created_wall_ns"])
        and is_count(p["eligible_source_count"])
        and p["eligible_source_count"] <= 4,
        "Invalid packet time or source count",
    )
    validate_fields(p)
    for item in objects(p["inputs"], max_items=32):
        item = object_keys(
            item, {"fixture_id", "sha256", "provenance_class", "source_ids", "session_ids"}
        )
        require(
            item["provenance_class"] == "SYNTHETIC" and matches(SHA, item["sha256"]),
            "Invalid synthetic input provenance",
        )
        for field in ("source_ids", "session_ids"):
            require(
                isinstance(item[field], list)
                and bool(item[field])
                and all(isinstance(x, str) and x for x in item[field]),
                "Invalid identity list",
            )
    require(bool(p["inputs"]), "Missing evidence inputs")
    for field in ("findings", "candidate_explanations"):
        for claim in objects(p[field], max_items=256):
            object_keys(claim, {"status", "statement", "value", "unit"})
            require(
                isinstance(claim["status"], str)
                and claim["status"] in STATUSES
                and isinstance(claim["statement"], str),
                "Invalid claim",
            )
            if claim["value"] is not None and type(claim["value"]) is not int:
                check_decimal(claim["value"])
    for field in ("parameters", "exclusion_counts"):
        pairs = p[field]
        require(
            isinstance(pairs, list)
            and all(
                isinstance(pair, list)
                and len(pair) == 2
                and isinstance(pair[0], str)
                and (isinstance(pair[1], str) if field == "parameters" else is_count(pair[1]))
                for pair in pairs
            ),
            "Invalid packet entries",
        )
        require(len({key for key, _ in pairs}) == len(pairs), "Duplicate packet entry")


def row_config(row, family: str, *, asof=False):
    keys = {"scenario", "interval_ms", "phase_percent", "broker"}
    keys |= (
        {"tolerance_ms"}
        if family == "p2"
        else {
            "duration_ms",
            "transport_ms",
            "processing_ms",
            "input_sha256",
        }
    )
    if not asof:
        keys.add("streams")
    row = object_keys(row, keys)
    require(row["scenario"] in (P2_NAMES if family == "p2" else P21_NAMES), "Unsupported scenario")
    for factor in keys & FACTORS.keys():
        require(
            type(row[factor]) is int and row[factor] in FACTORS[factor], "Invalid design factor"
        )
    broker = object_keys(
        row["broker"],
        {"coverage", "consensus_coverage", "exclusions", "pairwise_points", "consensus_points"},
    )
    if family == "p21":
        object_keys(
            broker,
            {"tolerance_ms", "decisions", "source_slots", "matched_slots", "unmatched_slots"},
        )
        require(
            is_count(broker["tolerance_ms"]) and broker["tolerance_ms"] in FACTORS["tolerance_ms"],
            "Invalid as-of tolerance",
        )
    if not asof:
        for stream in objects(row["streams"], max_items=4):
            object_keys(
                stream,
                {
                    "events",
                    "revisions",
                    "session_id",
                    "coverage",
                    "missing_ns",
                    "source_id",
                    "tails" if family == "p21" else "spread",
                },
            )
            require(matches(INTEGER_TEXT, stream["missing_ns"]), "Missing timestamp")
            event = object_keys(
                stream["events"],
                {
                    "eligible_truth",
                    "detected",
                    "missed",
                    "matches",
                    "recall",
                    "recall_unavailable",
                    "sample_right_censored",
                },
            )
            require(
                all(
                    is_count(event[k])
                    for k in ("eligible_truth", "detected", "missed", "sample_right_censored")
                )
                and event["detected"] + event["missed"] == event["eligible_truth"],
                "Invalid event accounting",
            )
            if family == "p21":
                for tail in ("p95", "p99"):
                    values = object_keys(
                        object_keys(stream["tails"], {"p95", "p99"})[tail], TAIL_KEYS
                    )
                    for name in TAIL_KEYS:
                        check_decimal(values[name])
    validate_fields(row)


def quote(value):
    row = object_keys(
        value,
        {
            "source_id",
            "session_id",
            "instrument_spec_version",
            "bid_text",
            "ask_text",
            "source_time_ms_or_null",
            "received_wall_ns",
            "processing_wall_ns",
            "poll_sequence",
            "ingestion_mode",
            "quality_flags",
        },
    )
    require(
        row["ingestion_mode"] == "SYNTHETIC" and is_count(row["poll_sequence"]),
        "Expected a synthetic quote observation",
    )
    require(
        all(
            isinstance(row[key], str) and bool(row[key])
            for key in ("source_id", "session_id", "instrument_spec_version")
        ),
        "Invalid quote identity",
    )
    require(
        all(matches(INTEGER_TEXT, row[k]) for k in ("received_wall_ns", "processing_wall_ns")),
        "Invalid quote timestamp",
    )
    require(
        row["source_time_ms_or_null"] is None or is_count(row["source_time_ms_or_null"]),
        "Invalid source milliseconds",
    )
    require(isinstance(row["quality_flags"], list), "Invalid quote flags")
    check_decimal(row["bid_text"])
    check_decimal(row["ask_text"])


def instrument_versions(value) -> set[str]:
    result = set()
    for spec in objects(value, max_items=16):
        object_keys(spec, {"canonical_symbol", "price_unit", "quote_currency", "spec_version"})
        require(spec["canonical_symbol"] == "XAUUSD", "Unsupported instrument")
        require(
            (spec["price_unit"] == "USD_PER_TROY_OUNCE" and spec["quote_currency"] == "USD")
            or (spec["price_unit"] == "UNKNOWN" and spec["quote_currency"] in (None, "USD")),
            "Unsupported quote unit",
        )
        version = spec["spec_version"]
        require(
            isinstance(version, str) and version and version not in result, "Invalid spec version"
        )
        result.add(version)
    require(bool(result), "Missing instrument specs")
    return result


def history(value, spec_versions: set[str] | None = None):
    h = object_keys(value, {"source", "events"})
    source = object_keys(
        h["source"], {"source_id", "session_id", "provenance_class", "ingestion_mode"}
    )
    require(
        source["provenance_class"] == source["ingestion_mode"] == "SYNTHETIC",
        "Unsupported source provenance",
    )
    for event in objects(h["events"], max_items=1024):
        object_keys(event, {"event_ns", "arrival", "truth_exclusion"})
        require(matches(INTEGER_TEXT, event["event_ns"]), "Invalid source-event timestamp")
        quote(event["arrival"])
        require(
            spec_versions is None or event["arrival"]["instrument_spec_version"] in spec_versions,
            "Unknown observation spec",
        )
        require(
            all(event["arrival"][k] == source[k] for k in ("source_id", "session_id")),
            "Source/session does not match its quote",
        )


def published_row(name, value):
    keys = {
        "p2-sensitivity": {"interval_ms", "tolerance_ms", "event_recall", "truth_events"},
        "p2-phase": {"interval_ms", "phase_percent", "event_recall", "truth_events"},
        "asof-sensitivity": {
            "interval_ms",
            "tolerance_ms",
            "consensus_coverage",
            "coverage",
            "cells",
        },
        "heatmap": {
            "scenario",
            "duration_ms",
            "interval_ms",
            "phase_percent",
            "detected",
            "truth_episodes",
            "recall",
        },
        "ideal": {
            "duration_ms",
            "interval_ms",
            "phase_count",
            "phase_rows",
            "finite_grid_probability",
        },
        "tail": {
            "scenario",
            "interval_ms",
            "tail",
            "available",
            "missing_component",
            "duration_to_duration",
            "snapshot_vs_duration_weighting",
            "original_cross_estimand",
        },
        "p21-sensitivity": {"duration_ms", "interval_ms", "detected", "truth_episodes", "recall"},
        "transport-processing": {
            "transport_ms",
            "processing_ms",
            "detected",
            "truth_episodes",
            "recall",
        },
    }
    if name not in keys:
        return
    row = object_keys(value, keys[name])
    for factor in FACTORS.keys() & row.keys():
        require(
            is_count(row[factor]) and row[factor] in FACTORS[factor], "Invalid published factor"
        )
    for count in {
        "available",
        "missing_component",
        "cells",
        "truth_events",
        "phase_count",
        "detected",
        "truth_episodes",
    } & row.keys():
        require(is_count(row[count]), "Invalid summary support")
    if "scenario" in row:
        require(row["scenario"] in P21_NAMES, "Invalid summary scenario")
    if name == "tail":
        require(row["tail"] in ("p95", "p99"), "Invalid quantile")
        for key in (
            "duration_to_duration",
            "snapshot_vs_duration_weighting",
            "original_cross_estimand",
        ):
            component = object_keys(
                row[key], {"sum", "mean", "min", "max", "defined_count", "unavailable"}
            )
            require(
                is_count(component["defined_count"])
                and component["defined_count"] == row["available"],
                "Inconsistent tail support",
            )
            for metric in ("sum", "mean", "min", "max"):
                check_decimal(component[metric])
