"""Run the bounded P2 synthetic robustness grid from a verified checkout."""

import argparse
import hashlib
import json
import platform
import subprocess
from collections import Counter
from collections.abc import Iterable
from dataclasses import fields, is_dataclass
from decimal import Decimal, localcontext
from importlib.metadata import version
from itertools import product
from pathlib import Path

from .comparison import BrokerComparison, compare_brokers
from .contracts import BrokerSource, InstrumentSpec, QuoteObservation
from .dynamics import QuoteDynamics
from .evidence import Claim, EpistemicStatus, InputProvenance, ResearchEvidencePacket
from .quality import PRICE_CONTEXT, QualityState
from .replay import verified_checkout_revision
from .sampling import (
    ASOF_TOLERANCES_MS,
    MS,
    PHASE_PERCENT,
    POLL_INTERVALS_MS,
    POLL_VERSION,
    poll_stream,
    poll_times,
)
from .sampling_metrics import METRIC_VERSION, build_oracle, score_sample, share
from .sampling_truth import CLOCK, END_NS, SPECS, THRESHOLD, TRUTH_VERSION, Scenario, scenarios

EXPERIMENT_ID = "p2-synthetic-robustness-v1"
EVALUATION_STEP_NS = 50 * MS
LIMITATIONS = (
    "Fixture design and transport delays are synthetic declarations.",
    "Observed quote age is elapsed time since the poll and does not measure network latency.",
    "Real missed ticks, broker synchronization and broker independence remain unknown.",
    "Quoted spreads do not establish actor identity, real liquidity, executable costs or arbitrage.",
)
CLOCK_ASSUMPTIONS = (
    CLOCK,
    "Decision points use a common synthetic wall epoch. Source timestamp is compared only where declared.",
    "Polling observes latest eligible arrivals and remains blind to oracle event time and validity labels.",
)


def scenario_payload(scenario: Scenario) -> dict:
    return {
        "version": TRUTH_VERSION,
        "clock": CLOCK,
        "window_end_ns": END_NS,
        "provenance": "SYNTHETIC",
        "specs": SPECS,
        "scenario": scenario,
    }


def configuration_grid() -> tuple[tuple[int, int, int], ...]:
    return tuple(product(POLL_INTERVALS_MS, ASOF_TOLERANCES_MS, PHASE_PERCENT))


def run_grid() -> list[dict]:
    results = []
    for scenario in scenarios():
        arrivals = tuple(history.arrivals() for history in scenario.histories)
        # Only the offline scorer consumes oracle objects.
        oracles = tuple(build_oracle(history) for history in scenario.histories)
        for interval, phase in product(POLL_INTERVALS_MS, PHASE_PERCENT):
            samples = tuple(
                poll_stream(stream, poll_times(END_NS, interval, phase, index))
                for index, stream in enumerate(arrivals)
            )
            scores = [
                score_sample(sample, oracle, interval * MS)
                for sample, oracle in zip(samples, oracles, strict=True)
            ]
            for tolerance in ASOF_TOLERANCES_MS:
                comparison = compare_brokers(
                    tuple(sample.stream for sample in samples),
                    range(0, END_NS, EVALUATION_STEP_NS),
                    receive_clock_domain=CLOCK,
                    max_age_ns=tolerance * MS,
                )
                points = comparison.points
                results.append(
                    {
                        "scenario": scenario.name,
                        "interval_ms": interval,
                        "tolerance_ms": tolerance,
                        "phase_percent": phase,
                        "streams": scores,
                        "broker": {
                            "coverage": comparison.valid_coverage,
                            "consensus_coverage": comparison.consensus_coverage,
                            "unmatched": comparison.unmatched_count,
                            "matched_age_ns": comparison.matched_age_ns,
                            "exclusions": dict(comparison.exclusion_counts),
                            "pairwise_points": sum(point.mode == "pairwise" for point in points),
                            "consensus_points": sum(point.mode == "consensus" for point in points),
                            "points": [
                                {
                                    "decision_wall_ns": point.decision_wall_ns,
                                    "eligible": point.eligible_broker_count,
                                    "mode": point.mode,
                                    "reasons": point.unavailable_reasons,
                                    "median_spread": point.median_spread,
                                    "median_mid": point.median_mid,
                                    "pairwise": point.pairwise,
                                }
                                for point in points
                            ],
                        },
                    }
                )
    return results


def mean_defined(values: Iterable[Decimal | None]) -> Decimal | None:
    defined = [value for value in values if value is not None]
    with localcontext(PRICE_CONTEXT):
        return sum(defined, Decimal(0)) / len(defined) if defined else None


def summarize(rows: list[dict]) -> dict:
    def totals(block: list[dict]) -> dict:
        streams = [stream for row in block for stream in row["streams"]]
        truth = sum(stream["events"]["eligible_truth"] for stream in streams)
        found = sum(stream["events"]["detected"] for stream in streams)
        async_rows = [row["broker"] for row in block if row["scenario"] == "asynchronous"]
        return {
            "events_detected": found,
            "truth_events": truth,
            "event_recall": share(found, truth),
            "false_detections": sum(stream["events"]["false_detections"] for stream in streams),
            "signed_snapshot_p95_error": mean_defined(
                stream["spread"]["errors"]["snapshot_p95"]["signed"] for stream in streams
            ),
            "signed_snapshot_p99_error": mean_defined(
                stream["spread"]["errors"]["snapshot_p99"]["signed"] for stream in streams
            ),
            "absolute_snapshot_p95_error": mean_defined(
                stream["spread"]["errors"]["snapshot_p95"]["absolute"] for stream in streams
            ),
            "absolute_snapshot_p99_error": mean_defined(
                stream["spread"]["errors"]["snapshot_p99"]["absolute"] for stream in streams
            ),
            "duration_coverage": mean_defined(stream["coverage"] for stream in streams),
            "asynchronous_broker_coverage": mean_defined(row["coverage"] for row in async_rows),
            "asynchronous_consensus_coverage": mean_defined(
                row["consensus_coverage"] for row in async_rows
            ),
            "asynchronous_pairwise_points": sum(row["pairwise_points"] for row in async_rows),
        }

    return {
        "configurations": [
            {
                "interval_ms": interval,
                "tolerance_ms": tolerance,
                **totals(
                    [
                        row
                        for row in rows
                        if (row["interval_ms"], row["tolerance_ms"]) == (interval, tolerance)
                    ]
                ),
            }
            for interval, tolerance in product(POLL_INTERVALS_MS, ASOF_TOLERANCES_MS)
        ],
        "phase_sensitivity": [
            {
                "interval_ms": interval,
                "phase_percent": phase,
                **totals(
                    [
                        row
                        for row in rows
                        if row["interval_ms"] == interval
                        and row["phase_percent"] == phase
                        and row["tolerance_ms"] == ASOF_TOLERANCES_MS[0]
                    ]
                ),
            }
            for interval, phase in product(POLL_INTERVALS_MS, PHASE_PERCENT)
        ],
    }


def wire(value, *, ns=False):
    if is_dataclass(value):
        return {
            field.name: wire(getattr(value, field.name), ns=field.name.endswith("_ns"))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {key: wire(item, ns=key.endswith("_ns")) for key, item in value.items()}
    if isinstance(value, (tuple, list, frozenset)):
        items = sorted(value) if isinstance(value, frozenset) else value
        return [wire(item, ns=ns) for item in items]
    if isinstance(value, Decimal) or (type(value) is int and (ns or abs(value) > 2**53 - 1)):
        return str(value)
    return value


def json_bytes(value) -> bytes:
    return (
        json.dumps(wire(value), sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("ascii")


def packet(scenario: Scenario, input_sha: str, results_sha: str, code_sha: str, rows: list[dict]):
    # Predeclared audit slice for each compact packet. All configurations are in the hashed table.
    row = next(
        row
        for row in rows
        if row["scenario"] == scenario.name
        and (row["interval_ms"], row["tolerance_ms"], row["phase_percent"]) == (100, 100, 50)
    )
    streams = row["streams"]
    exclusions = Counter()
    for stream in streams:
        for label, field in (
            ("poll", "sampled_exclusion_counts"),
            ("oracle", "oracle_exclusion_counts"),
        ):
            exclusions.update({f"{label}.{key}": count for key, count in stream[field].items()})
    exclusions.update(
        {f"comparison.{key}": count for key, count in row["broker"]["exclusions"].items()}
    )
    found = sum(stream["events"]["detected"] for stream in streams)
    truth = sum(stream["events"]["eligible_truth"] for stream in streams)
    return ResearchEvidencePacket(
        research_id=f"{EXPERIMENT_ID}/{scenario.name}",
        hypothesis_id="p2-schedule-dependence-v1",
        created_wall_ns=END_NS,
        inputs=(
            InputProvenance(
                scenario.name,
                input_sha,
                tuple(h.source.session_id for h in scenario.histories),
                tuple(h.source.source_id for h in scenario.histories),
            ),
        ),
        code_sha=code_sha,
        schema_versions=(
            BrokerSource.VERSION,
            InstrumentSpec.VERSION,
            QuoteObservation.VERSION,
            QualityState.VERSION,
            TRUTH_VERSION,
        ),
        metric_versions=(
            QuoteDynamics.VERSION,
            BrokerComparison.VERSION,
            POLL_VERSION,
            METRIC_VERSION,
        ),
        question="How do synthetic sampling phase and as-of age tolerance affect measurement?",
        clock_assumptions=CLOCK_ASSUMPTIONS,
        parameters=(
            ("interval_ms", "100"),
            ("tolerance_ms", "100"),
            ("phase_percent", "50"),
            ("eligible_source_count_statistic", "maximum over comparison decisions"),
            ("results_sha256", results_sha),
            ("created_wall_ns_origin", "synthetic window end"),
        ),
        eligible_source_count=max(point["eligible"] for point in row["broker"]["points"]),
        exclusion_counts=tuple(exclusions.items()),
        findings=(
            Claim(EpistemicStatus.FACT, "Fixture clocks and episode boundaries are synthetic."),
            Claim(
                EpistemicStatus.MEASUREMENT,
                "Widening truth episodes detected in the audit slice.",
                found,
                "count",
            ),
            Claim(
                EpistemicStatus.MEASUREMENT,
                "Eligible synthetic truth episodes in the audit slice.",
                truth,
                "count",
            ),
            Claim(
                EpistemicStatus.INFERENCE,
                "The fixture measurements are conditional on poll timing and declared validity.",
            ),
            Claim(
                EpistemicStatus.UNKNOWN, "Real-market missed quote revisions and executable costs."
            ),
        ),
        candidate_explanations=(
            Claim(
                EpistemicStatus.HYPOTHESIS,
                "A widening between consecutive polling decisions can leave no eligible wide snapshot.",
            ),
            Claim(
                EpistemicStatus.HYPOTHESIS,
                "Larger as-of tolerance can increase comparisons when otherwise eligible poll snapshots age out.",
            ),
        ),
        falsifiers=(
            "Replay the predeclared phases and verify every detection has an eligible sampled origin in its matched truth episode.",
            "Hold the polls constant and verify as-of tolerance never changes the single-source episode table.",
        ),
        limitations=LIMITATIONS,
    )


def write_experiment(output: Path, code_sha: str, lock_sha: str) -> dict:
    rows = run_grid()
    grid = configuration_grid()
    fixture_set = scenarios()
    expected_keys = {(scenario.name, *config) for scenario in fixture_set for config in grid}
    actual_keys = {
        (row["scenario"], row["interval_ms"], row["tolerance_ms"], row["phase_percent"])
        for row in rows
    }
    if actual_keys != expected_keys or len(actual_keys) != len(rows):
        raise ValueError("Experiment grid is incomplete or duplicated")

    output.mkdir(parents=True, exist_ok=False)
    artifacts = {}

    def write(name: str, data: bytes) -> str:
        (output / name).write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        artifacts[name] = {"sha256": digest, "bytes": len(data)}
        return digest

    results_sha = write("results.json", json_bytes(rows))
    write("sensitivity.json", json_bytes(summarize(rows)))
    inputs = {}
    for scenario in fixture_set:
        name = f"input-{scenario.name}.json"
        digest = write(name, json_bytes(scenario_payload(scenario)))
        inputs[scenario.name] = {"artifact": name, "sha256": digest}
        evidence = packet(scenario, digest, results_sha, code_sha, rows)
        write(f"evidence-{scenario.name}.json", evidence.to_json().encode("ascii"))

    manifest = {
        "manifest_version": "p2-experiment-manifest-v1",
        "experiment_id": EXPERIMENT_ID,
        "purpose": "Exhaustive synthetic sampling and age-tolerance robustness research",
        "hypothesis_id": "p2-schedule-dependence-v1",
        "scientific_status": "SYNTHETIC_MEASUREMENT",
        "run_id": f"{EXPERIMENT_ID}/{code_sha}",
        "predeclared_grid": grid,
        "grid_fields": ("interval_ms", "tolerance_ms", "phase_percent"),
        "row_count": len(rows),
        "scenarios": [s.name for s in fixture_set],
        "clock_assumptions": CLOCK_ASSUMPTIONS,
        "window_start_ns": 0,
        "window_end_ns": END_NS,
        "broker_grid_step_ns": EVALUATION_STEP_NS,
        "threshold_usd_per_troy_ounce": THRESHOLD,
        "split": "Exhaustive fixed synthetic histories, no optimization or phase selection.",
        "random_seeds": [],
        "model": None,
        "cost_model": None,
        "versions": (
            TRUTH_VERSION,
            POLL_VERSION,
            METRIC_VERSION,
            QuoteDynamics.VERSION,
            BrokerComparison.VERSION,
        ),
        "code_sha": code_sha,
        "lock_sha256": lock_sha,
        "inputs": inputs,
        "artifacts": artifacts,
        "environment": {
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
            "package": version("xauusd-quote-lab"),
        },
        "reproduction": "uv run --frozen --extra dev python -m xauusd_quote_lab.sampling_experiments --output NEW_DIRECTORY",
        "limitations": LIMITATIONS,
    }
    (output / "manifest.json").write_bytes(json_bytes(manifest))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New directory for experiment artifacts"
    )
    args = parser.parse_args()
    root = Path.cwd()
    try:
        revision = verified_checkout_revision(root)
        lock_sha = hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest()
        manifest = write_experiment(args.output, revision, lock_sha)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"P2 experiment: {exc}") from None
    print(f"{manifest['experiment_id']} | {manifest['row_count']} rows | {revision}")


if __name__ == "__main__":
    main()
