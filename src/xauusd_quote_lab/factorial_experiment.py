"""Run the bounded P2.1 factorial study from a verified committed checkout."""

import argparse
import platform
import subprocess
from collections import Counter, defaultdict
from collections.abc import Iterable
from decimal import Decimal, localcontext
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

from .comparison import BrokerComparison
from .dynamics import QuoteDynamics
from .evidence import Claim, EpistemicStatus, InputProvenance, ResearchEvidencePacket
from .factorial_metrics import (
    broker_coverage,
    counterexamples,
    ideal_row,
    poll_cohorts,
    project_arrivals,
    score_stream,
    summarize_ideal,
)
from .factorial_truth import (
    DURATIONS_MS,
    FIXED_TOLERANCE_MS,
    PROCESSING_MS,
    SCENARIOS,
    TRANSPORT_MS,
    TRUTH_VERSION,
    generate,
    inputs,
    schedules,
)
from .quality import PRICE_CONTEXT
from .replay import verified_checkout_revision
from .sampling import ASOF_TOLERANCES_MS, MS, PHASE_PERCENT, POLL_INTERVALS_MS, POLL_VERSION
from .sampling_experiments import EVALUATION_STEP_NS, json_bytes
from .sampling_metrics import METRIC_VERSION, build_oracle, share
from .sampling_truth import CLOCK, END_NS, SPECS, THRESHOLD
from .tail_decomposition import TAIL_VERSION

EXPERIMENT_ID = "p21-factorial-identifiability-v1"
BASELINE = "ee3853ab2089e90dbf514fb0ccde20499b789e9d"
BASELINE_RESULTS_SHA = "bdc5083df7a118fce5d48c68def2d30317e7bec17910801a9a0f4e6cd90327d1"
CORE_COUNT = 1152
OUTPUT_LIMIT = 96 * 1024 * 1024
ASOF_WIDTHS_MS = (25, 250, 1000)
ASOF_TRANSPORT_MS = 100
ASOF_PROCESSING_MS = 25
COMPONENTS = ("duration_to_duration", "snapshot_vs_duration_weighting", "original_cross_estimand")
VERSIONS = (
    QuoteDynamics.VERSION,
    BrokerComparison.VERSION,
    POLL_VERSION,
    METRIC_VERSION,
    TAIL_VERSION,
    "p21-ideal-intersection-v1",
)
CLOCKS = (
    CLOCK,
    "Source-event clock defines oracle episodes; receive and processing gate polls.",
    "Broker comparison uses a fixed synthetic wall grid and measures snapshot age.",
)
LIMITS = (
    "Sensitivity ranges describe enumerated synthetic scenarios and have no confidence level.",
    "Duration-to-duration differences include availability, missingness and support effects.",
    "Real tick completeness, synchronization, broker independence and real liquidity remain unknown.",
    "Quoted measurements cannot identify actors, executable arbitrage or realized costs.",
)


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def primary_rows():
    """Yield unique histories and their full schedule replications in frozen order."""
    for name in SCENARIOS:
        for factors in inputs():
            cohorts = generate(name, factors)
            arrivals = project_arrivals(cohorts)
            truth = {
                "scenario": name,
                "factors": factors,
                "cohorts": cohorts,
                "version": TRUTH_VERSION,
                "provenance": "SYNTHETIC",
                "specs": SPECS,
            }
            fingerprint = digest(json_bytes(truth))
            truth_record = {"input_sha256": fingerprint, "input": truth}
            oracles = tuple(
                tuple(build_oracle(history) for history in cohort.histories) for cohort in cohorts
            )
            for schedule in schedules():
                polls = poll_cohorts(arrivals, schedule)
                stream_scores = [
                    score_stream(sample, oracle, schedule.interval_ms * MS)
                    for group, labels in zip(polls, oracles, strict=True)
                    for sample, oracle in zip(group.samples, labels, strict=True)
                ]
                row = {
                    "scenario": name,
                    "input_sha256": fingerprint,
                    "duration_ms": factors.duration_ms,
                    "interval_ms": schedule.interval_ms,
                    "transport_ms": factors.transport_ms,
                    "processing_ms": factors.processing_ms,
                    "phase_percent": schedule.phase_percent,
                    "streams": stream_scores,
                    "broker": broker_coverage(polls, FIXED_TOLERANCE_MS),
                }
                asof = []
                if (
                    name == "asynchronous"
                    and factors.duration_ms in ASOF_WIDTHS_MS
                    and factors.transport_ms == ASOF_TRANSPORT_MS
                    and factors.processing_ms == ASOF_PROCESSING_MS
                ):
                    keys = {
                        key: value for key, value in row.items() if key not in {"streams", "broker"}
                    }
                    asof = [
                        {**keys, "broker": broker_coverage(polls, tolerance)}
                        for tolerance in ASOF_TOLERANCES_MS
                    ]
                ideal = (
                    ideal_row(factors.duration_ms, schedule, stream_scores[0])
                    if name == "isolated" and factors.transport_ms == factors.processing_ms == 0
                    else None
                )
                yield truth_record, row, asof, ideal


def distribution(values: list[Decimal]) -> dict:
    if not values:
        return {
            "defined_count": 0,
            "sum": None,
            "mean": None,
            "min": None,
            "max": None,
            "unavailable": "no_supported_pairs",
        }
    with localcontext(PRICE_CONTEXT):
        total = sum(values, Decimal(0))
        return {
            "defined_count": len(values),
            "sum": total,
            "mean": total / len(values),
            "min": min(values),
            "max": max(values),
            "unavailable": None,
        }


def compact(row: dict) -> dict:
    streams = row["streams"]
    values = {
        key: row[key]
        for key in (
            "scenario",
            "duration_ms",
            "interval_ms",
            "transport_ms",
            "processing_ms",
            "phase_percent",
        )
    }
    values.update(
        {
            "episodes": sum(s["events"]["eligible_truth"] for s in streams),
            "detected": sum(s["events"]["detected"] for s in streams),
            "false_detections": sum(s["events"]["false_detections"] for s in streams),
            "true_revisions": sum(s["revisions"]["true"] for s in streams),
            "matched_revisions": sum(s["revisions"]["matched"] for s in streams),
            "sample_right_censored": sum(s["events"]["sample_right_censored"] for s in streams),
            "supported_tail_rows": tuple(stream["tails"] for stream in streams),
            "broker": row["broker"],
        }
    )
    return values


def grouped(rows: list[dict], axes: tuple[str, ...]) -> dict[tuple, list[dict]]:
    blocks = defaultdict(list)
    for row in rows:
        blocks[tuple(row[axis] for axis in axes)].append(row)
    return dict(sorted(blocks.items()))


def totals(block: list[dict]) -> dict:
    true = sum(row["episodes"] for row in block)
    detected = sum(row["detected"] for row in block)
    revisions = sum(row["true_revisions"] for row in block)
    matched = sum(row["matched_revisions"] for row in block)
    return {
        "cells": len(block),
        "truth_episodes": true,
        "detected": detected,
        "missed": true - detected,
        "recall": share(detected, true),
        "false_detections": sum(row["false_detections"] for row in block),
        "true_revisions": revisions,
        "matched_revisions": matched,
        "revision_recall": share(matched, revisions),
        "sample_right_censored": sum(row["sample_right_censored"] for row in block),
        "broker_coverage": share(
            sum(row["broker"]["matched_slots"] for row in block),
            sum(row["broker"]["source_slots"] for row in block),
        ),
        "consensus_coverage": share(
            sum(row["broker"]["consensus_points"] for row in block),
            sum(row["broker"]["decisions"] for row in block),
        ),
    }


def summary(rows: list[dict], axes: tuple[str, ...]) -> list[dict]:
    return [
        {**dict(zip(axes, key, strict=True)), **totals(block)}
        for key, block in grouped(rows, axes).items()
    ]


def tails_summary(rows: list[dict]) -> list[dict]:
    result = []
    axes = ("scenario", "interval_ms")
    for key, block in grouped(rows, axes).items():
        for tail in ("p95", "p99"):
            origins = [stream[tail] for row in block for stream in row["supported_tail_rows"]]
            # Use the same support for aggregate components so denominators agree.
            complete = [
                entry for entry in origins if all(entry[name] is not None for name in COMPONENTS)
            ]
            summary_row = {
                **dict(zip(axes, key, strict=True)),
                "tail": tail,
                "available": len(complete),
                "missing_component": len(origins) - len(complete),
                **{name: distribution([entry[name] for entry in complete]) for name in COMPONENTS},
            }
            result.append(summary_row)
    return result


def summarize_asof(rows: list[dict]) -> list[dict]:
    normalized = [{**row, "tolerance_ms": row["broker"]["tolerance_ms"]} for row in rows]
    result = []
    axes = ("interval_ms", "tolerance_ms")
    for key, block in grouped(normalized, axes).items():
        broker = [row["broker"] for row in block]
        result.append(
            {
                **dict(zip(axes, key, strict=True)),
                "cells": len(block),
                "coverage": share(
                    sum(x["matched_slots"] for x in broker), sum(x["source_slots"] for x in broker)
                ),
                "consensus_coverage": share(
                    sum(x["consensus_points"] for x in broker), sum(x["decisions"] for x in broker)
                ),
                "pairwise_points": sum(x["pairwise_points"] for x in broker),
            }
        )
    return result


def evidence(
    code_sha: str,
    artifacts: dict,
    totals_all: dict,
    counterexamples_count: int,
    provenance: InputProvenance,
    max_eligible: int,
    exclusions: Counter[str],
):
    return ResearchEvidencePacket(
        research_id=EXPERIMENT_ID,
        hypothesis_id="p21-factor-interaction-v1",
        created_wall_ns=END_NS,
        inputs=(provenance,),
        code_sha=code_sha,
        schema_versions=(TRUTH_VERSION, "p21-results-v1"),
        metric_versions=VERSIONS,
        question="How do declared synthetic timing, sampling and weighting affect measurement and identification?",
        clock_assumptions=CLOCKS,
        parameters=tuple((name, entry["sha256"]) for name, entry in sorted(artifacts.items()))
        + (
            ("asof_primary_ms", str(FIXED_TOLERANCE_MS)),
            ("created_wall_ns_origin", "end of synthetic research window"),
            (
                "eligible_source_count_statistic",
                "maximum observed eligible broker count over primary broker decisions",
            ),
        ),
        eligible_source_count=max_eligible,
        exclusion_counts=tuple(exclusions.items()),
        findings=(
            Claim(
                EpistemicStatus.FACT,
                "The balanced grid and truth histories are synthetic and hashed.",
            ),
            Claim(
                EpistemicStatus.MEASUREMENT,
                "Primary factorial rows examined.",
                totals_all["cells"],
                "rows",
            ),
            Claim(
                EpistemicStatus.MEASUREMENT,
                "Matched widening episodes in the frozen design.",
                totals_all["detected"],
                "episodes",
            ),
            Claim(
                EpistemicStatus.MEASUREMENT,
                "Observationally equal fixture pairs with different truth.",
                counterexamples_count,
                "pairs",
            ),
            Claim(
                EpistemicStatus.INFERENCE,
                "The observed poll record does not identify hidden episodes without assumptions.",
            ),
            Claim(
                EpistemicStatus.REJECTED,
                "The cross-estimand tail contrast is a pure duration-to-duration difference.",
            ),
            Claim(
                EpistemicStatus.UNKNOWN,
                "Real-market tick loss, execution costs and economic broker independence.",
            ),
        ),
        candidate_explanations=(
            Claim(
                EpistemicStatus.HYPOTHESIS,
                "A poll can intersect a source event and still miss it if processing is pending.",
            ),
        ),
        falsifiers=(
            "The fixed ideal schedule must agree with exact discrete intersection.",
            "Changing hidden truth labels alone must leave the arrival projection unchanged.",
            "Every fully supported tail decomposition must close without rounding error.",
        ),
        limitations=LIMITS,
    )


class Artifacts:
    def __init__(self, output: Path):
        output.mkdir(parents=True, exist_ok=False)
        self.output = output
        self.total = 0
        self.index = {}

    def write(self, name: str, chunks: Iterable[bytes]) -> None:
        state = sha256()
        size = 0
        with (self.output / name).open("xb") as file:
            for data in chunks:
                self.total += len(data)
                if self.total > OUTPUT_LIMIT:
                    raise ValueError("P2.1 run exceeds the 96 MiB output budget")
                size += len(data)
                state.update(data)
                file.write(data)
        self.index[name] = {"sha256": state.hexdigest(), "bytes": size}

    def json(self, name: str, value: object) -> None:
        self.write(name, (json_bytes(value),))


def run(output: Path, code_sha: str, lock_sha: str) -> dict:
    files = Artifacts(output)
    truth_catalog = {}
    aggregates = []
    separate_asof = []
    ideal = []
    seen = set()
    exclusions: Counter[str] = Counter()

    def rows():
        for truth, row, asof, theory in primary_rows():
            key = tuple(
                row[name]
                for name in (
                    "scenario",
                    "duration_ms",
                    "interval_ms",
                    "transport_ms",
                    "processing_ms",
                    "phase_percent",
                )
            )
            if key in seen:
                raise ValueError("Duplicate factorial cell")
            seen.add(key)
            truth_catalog.setdefault(row["input_sha256"], truth)
            aggregates.append(compact(row))
            for stream in row["streams"]:
                for field in ("sampled_exclusions", "oracle_exclusions"):
                    exclusions.update(
                        {f"{field}.{key}": count for key, count in stream[field].items()}
                    )
            exclusions.update(
                {
                    f"broker_exclusions.{key}": count
                    for key, count in row["broker"]["exclusions"].items()
                }
            )
            separate_asof.extend(asof)
            if theory is not None:
                ideal.append(theory)
            yield json_bytes(row)

    files.write("results.jsonl", rows())
    if (
        any(sum(key[0] == name for key in seen) != CORE_COUNT for name in SCENARIOS)
        or len(seen) != CORE_COUNT * len(SCENARIOS)
        or len(separate_asof) != 192
        or len(ideal) != 96
        or len(truth_catalog) != 432
    ):
        raise ValueError("The frozen factorial design is incomplete")
    files.write("truth-inputs.jsonl", (json_bytes(truth) for truth in truth_catalog.values()))
    theory = summarize_ideal(ideal)
    files.json("ideal-intersection.json", theory)
    files.json(
        "heatmap.json",
        summary(aggregates, ("scenario", "duration_ms", "interval_ms", "phase_percent")),
    )
    files.json(
        "sensitivity.json",
        {
            "overall": totals(aggregates),
            "by_scenario": summary(aggregates, ("scenario",)),
            "by_width_interval": summary(aggregates, ("duration_ms", "interval_ms")),
            "by_transport_processing": summary(aggregates, ("transport_ms", "processing_ms")),
            "by_interval_phase": summary(aggregates, ("interval_ms", "phase_percent")),
        },
    )
    files.json("tail-decomposition.json", tails_summary(aggregates))
    files.write("asof-results.jsonl", (json_bytes(row) for row in separate_asof))
    files.json("asof-sensitivity.json", summarize_asof(separate_asof))
    equivalence = counterexamples()
    for case in equivalence:
        case["sample_sha256"] = digest(json_bytes(case["shared_sample"]))
        for member in ("quiet", "hidden"):
            case[member]["truth_sha256"] = digest(json_bytes(case[member]["truth"]))
    files.json("identifiability.json", equivalence)
    sources = {
        (history.source.source_id, history.source.session_id)
        for truth in truth_catalog.values()
        for cohort in truth["input"]["cohorts"]
        for history in cohort.histories
    }
    provenance = InputProvenance(
        "p21-frozen-truth-catalog",
        files.index["truth-inputs.jsonl"]["sha256"],
        tuple(sorted({session for _, session in sources})),
        tuple(sorted({source for source, _ in sources})),
    )
    max_eligible = max(row["broker"]["max_eligible_brokers"] for row in aggregates)
    claim = evidence(
        code_sha,
        files.index,
        totals(aggregates),
        len(equivalence),
        provenance,
        max_eligible,
        exclusions,
    )
    files.write("evidence.json", (claim.to_json().encode("ascii"),))

    manifest = {
        "manifest_version": "p21-experiment-manifest-v1",
        "experiment_id": EXPERIMENT_ID,
        "code_sha": code_sha,
        "run_id": f"{EXPERIMENT_ID}/{code_sha}",
        "lock_sha256": lock_sha,
        "baseline_code_sha": BASELINE,
        "baseline_result_sha256": BASELINE_RESULTS_SHA,
        "versions": (TRUTH_VERSION, *VERSIONS),
        "factors": {
            "duration_ms": DURATIONS_MS,
            "interval_ms": POLL_INTERVALS_MS,
            "transport_ms": TRANSPORT_MS,
            "processing_ms": PROCESSING_MS,
            "phase_percent": PHASE_PERCENT,
        },
        "scenario_replications": SCENARIOS,
        "rows_per_scenario": CORE_COUNT,
        "primary_rows": len(seen),
        "primary_asof_ms": FIXED_TOLERANCE_MS,
        "unique_frozen_histories": len(truth_catalog),
        "asof_experiment": {
            "scenario": "asynchronous",
            "duration_ms": ASOF_WIDTHS_MS,
            "transport_ms": ASOF_TRANSPORT_MS,
            "processing_ms": ASOF_PROCESSING_MS,
            "tolerances_ms": ASOF_TOLERANCES_MS,
            "rows": len(separate_asof),
        },
        "ideal_cells": len(ideal),
        "window_ns": (0, END_NS),
        "broker_grid_step_ns": EVALUATION_STEP_NS,
        "widening_threshold": THRESHOLD,
        "clock_assumptions": CLOCKS,
        "limitations": LIMITS,
        "split": "Exhaustive fixed design with no tuning, no random seeds, and no execution model.",
        "environment": {
            "python": platform.python_version(),
            "os": platform.system(),
            "machine": platform.machine(),
            "package": version("xauusd-quote-lab"),
        },
        "max_output_bytes": OUTPUT_LIMIT,
        "artifacts": files.index,
        "reproduction": "uv run --frozen --extra dev python -m xauusd_quote_lab.factorial_experiment --output NEW_DIRECTORY",
    }
    payload = json_bytes(manifest)
    if files.total + len(payload) > OUTPUT_LIMIT:
        raise ValueError("P2.1 run exceeds the 96 MiB output budget")
    (output / "manifest.json").write_bytes(payload)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    args = parser.parse_args()
    root = Path.cwd()
    try:
        revision = verified_checkout_revision(root)
        report = run(args.output, revision, digest((root / "uv.lock").read_bytes()))
    except (OSError, ValueError, ArithmeticError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"P2.1 experiment: {exc}") from None
    print(f"{EXPERIMENT_ID} | {report['primary_rows']} factorial rows | {revision}")


if __name__ == "__main__":
    main()
