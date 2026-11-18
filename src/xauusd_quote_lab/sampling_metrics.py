"""Offline P2 scoring against independently declared synthetic truth states."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, localcontext

from .contracts import Flag
from .dynamics import WideningEvent, measure_dynamics
from .quality import PRICE_CONTEXT
from .sampling import PollSample
from .sampling_truth import END_NS, THRESHOLD, EventHistory

METRIC_VERSION = "p2-sampling-metrics-v1"


@dataclass(frozen=True, slots=True)
class TruthEpisode:
    window: WideningEvent
    sequences: frozenset[int]


@dataclass(frozen=True, slots=True)
class Oracle:
    episodes: tuple[TruthEpisode, ...]
    revisions: frozenset[int]
    states: tuple[tuple[Decimal, int], ...]
    exposures: tuple[tuple[Decimal, int], ...]
    exclusions: tuple[tuple[str, int], ...]


def build_oracle(history: EventHistory) -> Oracle:
    """Derive state-time labels directly, independent of arrival clocks and polling."""
    episodes = []
    revisions = set()
    states = []
    exposures = []
    excluded: Counter[str] = Counter()
    active = []
    left_censored = False
    previous = None
    previous_spec = None

    for index, event in enumerate(history.events):
        row = event.arrival
        spec = row.instrument_spec_version
        spread = None
        if event.truth_exclusion is None:
            with localcontext(PRICE_CONTEXT):
                prices = Decimal(row.bid_text), Decimal(row.ask_text)
                spread = prices[1] - prices[0]
            right = (
                history.events[index + 1].event_ns if index + 1 < len(history.events) else END_NS
            )
            states.append((spread, 1))
            exposures.append((spread, right - event.event_ns))
            if previous is not None and previous_spec == spec and prices != previous:
                revisions.add(row.poll_sequence)
        else:
            prices = None
            excluded[event.truth_exclusion] += 1

        if active and (spread is None or spec != previous_spec or spread < THRESHOLD):
            recovered = spread is not None and spec == previous_spec
            reason = None if recovered else event.truth_exclusion or "instrument_spec_changed"
            episodes.append(close_episode(active, event.event_ns, recovered, reason, left_censored))
            active = []
        if spread is not None and spread >= THRESHOLD:
            if not active:
                left_censored = previous is None or previous_spec != spec
            active.append((event.event_ns, row.poll_sequence))
        previous, previous_spec = prices, spec

    if active:
        episodes.append(close_episode(active, END_NS, False, "window_end", left_censored))
    return Oracle(
        tuple(episodes),
        frozenset(revisions),
        tuple(states),
        tuple(exposures),
        tuple(sorted(excluded.items())),
    )


def close_episode(active, end_ns, recovered, reason, left_censored) -> TruthEpisode:
    start_ns = active[0][0]
    return TruthEpisode(
        WideningEvent(start_ns, end_ns, end_ns - start_ns, recovered, reason, left_censored),
        frozenset(sequence for _, sequence in active),
    )


def share(numerator: int, denominator: int) -> Decimal | None:
    with localcontext(PRICE_CONTEXT):
        return Decimal(numerator) / denominator if denominator else None


def weighted_quantile(weighted: Iterable[tuple[Decimal, int]], percentile: int) -> Decimal | None:
    if not 1 <= percentile <= 100:
        raise ValueError("Percentile must be in 1..100")
    items = sorted(weighted)
    if any(weight < 0 for _, weight in items):
        raise ValueError("Quantile weights must be nonnegative")
    total = sum(weight for _, weight in items)
    rank = (percentile * total + 99) // 100
    cumulative = 0
    if rank:
        for value, weight in items:
            cumulative += weight
            if cumulative >= rank:
                return value
    return None


def distribution(snapshots, durations) -> dict:
    def mean(items):
        count = sum(weight for _, weight in items)
        with localcontext(PRICE_CONTEXT):
            return sum(value * weight for value, weight in items) / count if count else None

    result = {
        "snapshot_mean": mean(snapshots),
        "duration_mean": mean(durations),
        "snapshot_p95": weighted_quantile(snapshots, 95),
        "snapshot_p99": weighted_quantile(snapshots, 99),
        "duration_p95": weighted_quantile(durations, 95),
        "duration_p99": weighted_quantile(durations, 99),
    }
    return {
        "values": result,
        "unavailable": {
            metric: (
                "no_eligible_snapshots" if metric.startswith("snapshot") else "no_covered_duration"
            )
            for metric, value in result.items()
            if value is None
        },
    }


def differences(sampled: dict, oracle: dict) -> dict:
    results = {}
    for metric, actual in sampled["values"].items():
        # Snapshot tails are compared with full event-time occupancy tails.
        reference_key = metric.replace("snapshot_p", "duration_p")
        expected = oracle["values"][reference_key]
        with localcontext(PRICE_CONTEXT):
            signed = actual - expected if actual is not None and expected is not None else None
        results[metric] = {
            "reference": reference_key,
            "signed": signed,
            "absolute": signed.copy_abs() if signed is not None else None,
            "unavailable": "missing_sample_or_oracle_support" if signed is None else None,
        }
    return results


def match_episodes(sampled, truth, witnesses) -> dict:
    used = set()
    matches = []
    false_episodes = []
    for event in sampled:
        start_spec = next(
            spec for decision, _, spec in witnesses if decision == event.observed_start_ns
        )
        sequences = {
            sequence
            for decision, sequence, spec in witnesses
            if event.observed_start_ns <= decision <= event.observed_end_ns and spec == start_spec
        }
        match = next(
            (
                i
                for i, candidate in enumerate(truth)
                if i not in used and sequences & candidate.sequences
            ),
            None,
        )
        if match is None:
            false_episodes.append(event)
            continue
        used.add(match)
        reference = truth[match].window
        know_onset = not (reference.left_censored or event.left_censored)
        know_recovery = reference.recovered and event.recovered
        matches.append(
            {
                "truth_index": match,
                "sample": event,
                "oracle": reference,
                "onset_error_ns": event.observed_start_ns - reference.observed_start_ns
                if know_onset
                else None,
                "recovery_error_ns": event.observed_end_ns - reference.observed_end_ns
                if know_recovery
                else None,
                "duration_error_ns": event.duration_ns - reference.duration_ns
                if know_onset and know_recovery
                else None,
                "onset_unavailable": None if know_onset else "left_censored",
                "recovery_unavailable": None if know_recovery else "right_censored",
                "duration_unavailable": None if know_onset and know_recovery else "censored_edge",
            }
        )
    return {
        "eligible_truth": len(truth),
        "detected": len(matches),
        "missed": len(truth) - len(matches),
        "recall": share(len(matches), len(truth)),
        "recall_unavailable": None if truth else "no_truth_episodes",
        "false_detections": len(false_episodes),
        "false_episodes": false_episodes,
        "truth_left_censored": sum(e.window.left_censored for e in truth),
        "truth_right_censored": sum(not e.window.recovered for e in truth),
        "sample_left_censored": sum(e.left_censored for e in sampled),
        "sample_right_censored": sum(not e.recovered for e in sampled),
        "missed_episodes": [e.window for i, e in enumerate(truth) if i not in used],
        "matches": matches,
    }


def score_sample(sample: PollSample, oracle: Oracle, interval_ns: int) -> dict:
    dynamics = measure_dynamics(
        sample.stream,
        start_ns=0,
        end_ns=END_NS,
        max_age_ns=interval_ns,
        widening_threshold=THRESHOLD,
    )
    rows = sample.stream.observations
    snapshots = []
    exposures = []
    witnesses = []
    origin_ages = []
    for i, (row, origin) in enumerate(zip(rows, sample.origins, strict=True)):
        if origin is None:
            continue
        with localcontext(PRICE_CONTEXT):
            spread = Decimal(row.ask_text) - Decimal(row.bid_text)
        snapshots.append((spread, 1))
        if i + 1 < len(rows):
            weight = min(interval_ns, rows[i + 1].received_wall_ns - row.received_wall_ns)
            exposures.append((spread, weight))
        if spread >= THRESHOLD:
            witnesses.append((row.received_wall_ns, origin.sequence, row.instrument_spec_version))
        origin_ages.append(row.received_wall_ns - origin.received_wall_ns)
    reported = distribution(snapshots, exposures)
    reference = distribution(oracle.states, oracle.exposures)
    # Keep means on the canonical P1 implementation.
    reported["values"]["snapshot_mean"] = dynamics.snapshot_weighted_spread
    reported["values"]["duration_mean"] = dynamics.duration_weighted_spread

    changed = [
        sample.origins[change.poll_sequence].sequence
        for change in dynamics.changes
        if (change.delta_bid or change.delta_ask)
        and Flag.DUPLICATE_SNAPSHOT not in rows[change.poll_sequence].quality_flags
    ]
    credited = set(changed) & oracle.revisions
    return {
        "source_id": sample.stream.source.source_id,
        "session_id": sample.stream.source.session_id,
        "events": match_episodes(dynamics.widening, oracle.episodes, witnesses),
        "spread": {
            "sampled": reported,
            "oracle": reference,
            "errors": differences(reported, reference),
        },
        "revisions": {
            "true": len(oracle.revisions),
            "observed": dynamics.revision_count,
            "duplicates": dict(dynamics.exclusions).get(Flag.DUPLICATE_SNAPSHOT, 0),
            "matched": len(credited),
            "missed": len(oracle.revisions - credited),
            "unlinked_observed": len(changed) - len(credited),
            "observed_per_covered_second": dynamics.revisions_per_covered_second,
            "intensity_unavailable": None if dynamics.covered_ns else "no_covered_duration",
        },
        "coverage": dynamics.coverage,
        "covered_ns": dynamics.covered_ns,
        "missing_ns": END_NS - dynamics.covered_ns,
        "oracle_covered_ns": sum(weight for _, weight in oracle.exposures),
        "available_polls": len(snapshots),
        "total_polls": len(rows),
        "origin_age_ns": sorted(origin_ages),
        "sampled_exclusion_counts": dict(dynamics.exclusions),
        "oracle_exclusion_counts": dict(oracle.exclusions),
    }
