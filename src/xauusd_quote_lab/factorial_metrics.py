"""Score factorial replications with P2 matching and P2.1 tail estimands."""

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, localcontext

from .comparison import compare_brokers
from .contracts import QuoteStream
from .factorial_truth import ONSET_MS, Cohort, Schedule
from .quality import PRICE_CONTEXT
from .sampling import MS, PHASE_PERCENT, PollSample, poll_stream, poll_times
from .sampling_experiments import EVALUATION_STEP_NS
from .sampling_metrics import Oracle, build_oracle, score_sample, share, weighted_quantile
from .sampling_truth import CLOCK, END_NS, THRESHOLD, State, history
from .tail_decomposition import decompose_tail


@dataclass(frozen=True, slots=True)
class ArrivalCohort:
    start_ns: int
    end_ns: int
    streams: tuple[QuoteStream, ...]


@dataclass(frozen=True, slots=True)
class CohortPolls:
    start_ns: int
    end_ns: int
    samples: tuple[PollSample, ...]


def project_arrivals(cohorts: tuple[Cohort, ...]) -> tuple[ArrivalCohort, ...]:
    return tuple(
        ArrivalCohort(c.start_ns, c.end_ns, tuple(h.arrivals() for h in c.histories))
        for c in cohorts
    )


def poll_cohorts(cohorts: tuple[ArrivalCohort, ...], schedule: Schedule) -> tuple[CohortPolls, ...]:
    return tuple(
        CohortPolls(
            cohort.start_ns,
            cohort.end_ns,
            tuple(
                poll_stream(
                    stream,
                    tuple(
                        t
                        for t in poll_times(
                            cohort.end_ns, schedule.interval_ms, schedule.phase_percent, index
                        )
                        if t >= cohort.start_ns
                    ),
                )
                for index, stream in enumerate(cohort.streams)
            ),
        )
        for cohort in cohorts
    )


def score_stream(sample: PollSample, oracle: Oracle, interval_ns: int) -> dict:
    score = score_sample(sample, oracle, interval_ns)
    sample_values = score["spread"]["sampled"]["values"]
    oracle_values = score["spread"]["oracle"]["values"]
    tails = {
        f"p{q}": decompose_tail(
            oracle_values[f"duration_p{q}"],
            sample_values[f"duration_p{q}"],
            sample_values[f"snapshot_p{q}"],
        )
        for q in (95, 99)
    }
    revisions = score["revisions"]
    revisions["recall"] = share(revisions["matched"], revisions["true"])
    revisions["recall_unavailable"] = None if revisions["true"] else "no_truth_revisions"
    with localcontext(PRICE_CONTEXT):
        eligible_wide_polls = sum(
            Decimal(row.ask_text) - Decimal(row.bid_text) >= THRESHOLD
            for row, origin in zip(sample.stream.observations, sample.origins, strict=True)
            if origin is not None
        )
    return {
        "source_id": score["source_id"],
        "session_id": score["session_id"],
        "events": score["events"],
        "oracle_episodes": tuple(ep.window for ep in oracle.episodes),
        "tails": tails,
        "observed_episodes": score["events"]["detected"] + score["events"]["false_detections"],
        "revisions": revisions,
        "eligible_wide_polls": eligible_wide_polls,
        "total_polls": score["total_polls"],
        "eligible_polls": score["available_polls"],
        "coverage": score["coverage"],
        "covered_ns": score["covered_ns"],
        "missing_ns": score["missing_ns"],
        "oracle_covered_ns": score["oracle_covered_ns"],
        "sampled_exclusions": score["sampled_exclusion_counts"],
        "oracle_exclusions": score["oracle_exclusion_counts"],
    }


def broker_coverage(polls: tuple[CohortPolls, ...], tolerance_ms: int) -> dict:
    decisions = consensus = slots = missing = pairwise = max_eligible = 0
    exclusions: Counter[str] = Counter()
    for item in polls:
        streams = tuple(sample.stream for sample in item.samples)
        grid = tuple(
            t for t in range(0, END_NS, EVALUATION_STEP_NS) if item.start_ns <= t < item.end_ns
        )
        result = compare_brokers(
            streams, grid, receive_clock_domain=CLOCK, max_age_ns=tolerance_ms * MS
        )
        decisions += len(result.points)
        consensus += sum(point.mode == "consensus" for point in result.points)
        pairwise += sum(point.mode == "pairwise" for point in result.points)
        max_eligible = max(
            max_eligible, max((point.eligible_broker_count for point in result.points), default=0)
        )
        slots += len(result.points) * len(streams)
        missing += result.unmatched_count
        exclusions.update(dict(result.exclusion_counts))
    return {
        "tolerance_ms": tolerance_ms,
        "decisions": decisions,
        "source_slots": slots,
        "matched_slots": slots - missing,
        "unmatched_slots": missing,
        "consensus_points": consensus,
        "pairwise_points": pairwise,
        "max_eligible_brokers": max_eligible,
        "coverage": share(slots - missing, slots),
        "consensus_coverage": share(consensus, decisions),
        "exclusions": dict(exclusions),
    }


def ideal_row(duration_ms: int, schedule: Schedule, score: dict) -> dict:
    start = ONSET_MS * MS
    stop = (ONSET_MS + duration_ms) * MS
    step = schedule.interval_ms * MS
    offset = step * schedule.phase_percent // 100
    first = offset + max(0, (start - offset + step - 1) // step) * step
    intersection = first < min(stop, END_NS)
    return {
        "duration_ms": duration_ms,
        "interval_ms": schedule.interval_ms,
        "phase_percent": schedule.phase_percent,
        "theoretical_intersection": intersection,
        "eligible_wide_polls": score["eligible_wide_polls"],
        "observed_episodes": score["observed_episodes"],
        "matched_events": score["events"]["detected"],
        "sample_left_censored": score["events"]["sample_left_censored"],
        "sample_right_censored": score["events"]["sample_right_censored"],
        "truth_left_censored": score["events"]["truth_left_censored"],
        "truth_right_censored": score["events"]["truth_right_censored"],
    }


def summarize_ideal(rows: list[dict]) -> list[dict]:
    result = []
    for duration, interval in sorted({(r["duration_ms"], r["interval_ms"]) for r in rows}):
        cell = [r for r in rows if (r["duration_ms"], r["interval_ms"]) == (duration, interval)]
        if {r["phase_percent"] for r in cell} != set(PHASE_PERCENT) or len(cell) != len(
            PHASE_PERCENT
        ):
            raise ValueError("Ideal phase grid is incomplete or duplicated")
        intersections = sum(r["theoretical_intersection"] for r in cell)
        if any(
            r["theoretical_intersection"] != bool(r["eligible_wide_polls"])
            or bool(r["eligible_wide_polls"]) != bool(r["observed_episodes"])
            or bool(r["observed_episodes"]) != bool(r["matched_events"])
            for r in cell
        ):
            raise ValueError("Ideal phase, eligibility, detection or matching disagrees")
        result.append(
            {
                "duration_ms": duration,
                "interval_ms": interval,
                "phase_count": len(cell),
                "intersection_phases": intersections,
                "finite_grid_probability": share(intersections, len(cell)),
                "continuous_uniform_probability": share(min(duration, interval), interval),
                "matched_phases": sum(bool(r["matched_events"]) for r in cell),
                "phase_rows": cell,
            }
        )
    return result


def counterexamples() -> list[dict]:
    result = []
    polls = tuple(range(0, END_NS, 100 * MS))
    for count, percentile in ((1, 99), (2, 95)):
        quiet = [State(0, "2000.20")]
        hidden = quiet.copy()
        for start in (120, 320)[:count]:
            quiet.extend((State(start, "2000.20"), State(start + 60, "2000.20")))
            hidden.extend((State(start, "2000.90"), State(start + 60, "2000.20")))
        left = history(f"equivalence-{count}", "alpha", *quiet)
        right = history(f"equivalence-{count}", "alpha", *hidden)
        left_sample = poll_stream(left.arrivals(), polls)
        right_sample = poll_stream(right.arrivals(), polls)
        if left_sample != right_sample:
            raise ValueError("Equivalence fixture must have identical complete samples")
        left_truth, right_truth = build_oracle(left), build_oracle(right)
        result.append(
            {
                "id": f"hidden-{count}",
                "interval_ms": 100,
                "phase_percent": 0,
                "polls_ns": polls,
                "observationally_equal": True,
                "shared_sample": left_sample,
                "tail_percentile": percentile,
                "quiet": {
                    "truth": left,
                    "episodes": len(left_truth.episodes),
                    "oracle_tail": weighted_quantile(left_truth.exposures, percentile),
                },
                "hidden": {
                    "truth": right,
                    "episodes": len(right_truth.episodes),
                    "oracle_tail": weighted_quantile(right_truth.exposures, percentile),
                },
            }
        )
    return result
