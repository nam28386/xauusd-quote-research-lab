from dataclasses import replace
from decimal import Decimal, localcontext
from itertools import product

import pytest

from xauusd_quote_lab import factorial_experiment
from xauusd_quote_lab.contracts import Flag
from xauusd_quote_lab.factorial_experiment import Artifacts
from xauusd_quote_lab.factorial_metrics import (
    broker_coverage,
    counterexamples,
    ideal_row,
    poll_cohorts,
    project_arrivals,
    score_stream,
    summarize_ideal,
)
from xauusd_quote_lab.factorial_truth import (
    FIXED_TOLERANCE_MS,
    SCENARIOS,
    InputFactors,
    Schedule,
    generate,
    inputs,
    schedules,
)
from xauusd_quote_lab.sampling import MS, PHASE_PERCENT, poll_stream
from xauusd_quote_lab.sampling_metrics import build_oracle
from xauusd_quote_lab.tail_decomposition import decompose_tail


def test_factorial_design_balanced_and_deterministic():
    configs = set(product(inputs(), schedules()))
    assert len(inputs()) == 72
    assert len(schedules()) == 16
    assert len(configs) == 1152
    assert len(SCENARIOS) == 6
    for name, factor in product(SCENARIOS, inputs()):
        assert generate(name, factor) == generate(name, factor)


@pytest.mark.parametrize(
    "oracle,duration,snapshot",
    [
        ("0.20", "0.90", "0.25"),
        ("0.95", "0.65", "1.20"),
        ("9999999999999999.90", "9999999999999999.99", "9999999999999999.97"),
    ],
)
def test_tail_decomposition_is_exact_despite_ambient_precision(oracle, duration, snapshot):
    o, d, s = map(Decimal, (oracle, duration, snapshot))
    expected = (d - o, s - d, s - o)
    with localcontext() as context:
        context.prec = 2
        actual = decompose_tail(o, d, s)
    assert tuple(actual[k] for k in factorial_experiment.COMPONENTS) == expected
    assert (
        actual["original_cross_estimand"]
        == actual["duration_to_duration"] + actual["snapshot_vs_duration_weighting"]
    )


def test_tail_missing_duration_still_preserves_original_cross_estimand():
    tail = decompose_tail(Decimal("0.20"), None, Decimal("0.90"))
    assert tail["original_cross_estimand"] == Decimal("0.70")
    assert tail["duration_to_duration"] is None
    assert tail["snapshot_vs_duration_weighting"] is None
    assert tail["duration_unavailable"] == "missing_duration_support"
    assert tail["weighting_unavailable"] == "missing_sampled_support"


def test_ideal_finite_phase_intersection_differs_from_continuous_probability():
    cohorts = generate("isolated", InputFactors(25, 0, 0))
    oracle = build_oracle(cohorts[0].histories[0])
    predictions = []
    for phase in PHASE_PERCENT:
        schedule = Schedule(250, phase)
        sample = poll_cohorts(project_arrivals(cohorts), schedule)[0].samples[0]
        score = score_stream(sample, oracle, 250 * MS)
        predictions.append(ideal_row(25, schedule, score))
    summary = summarize_ideal(predictions)[0]
    assert [r["theoretical_intersection"] for r in predictions] == [False, False, True, False]
    assert [r["matched_events"] for r in predictions] == [0, 0, 1, 0]
    assert summary["finite_grid_probability"] == Decimal("0.25")
    assert summary["continuous_uniform_probability"] == Decimal("0.1")


def test_source_intersection_does_not_imply_availability():
    cohorts = generate("isolated", InputFactors(25, 25, 100))
    raw = cohorts[0].histories[0].arrivals()
    sample = poll_stream(raw, tuple(t * MS for t in (125, 149, 150, 175, 250, 275)))
    assert [row.ask_text for row in sample.stream.observations] == [
        "2000.20",
        "2000.20",
        None,
        None,
        None,
        "2000.20",
    ]
    assert Flag.PROCESSING_PENDING in sample.stream.observations[4].quality_flags
    assert sample.origins[0].sequence == 0
    assert sample.origins[2:5] == (None, None, None)
    assert sample.origins[5].sequence == 2


def test_truth_relabeling_does_not_change_factorial_polling():
    original = generate("isolated", InputFactors(25, 0, 0))[0]
    source = original.histories[0]
    changed = replace(
        source,
        events=(
            source.events[0],
            replace(source.events[1], truth_exclusion="synthetic"),
            source.events[2],
        ),
    )
    assert build_oracle(changed) != build_oracle(source)
    a = project_arrivals((original,))
    b = project_arrivals((replace(original, histories=(changed,)),))
    assert a == b
    assert poll_cohorts(a, Schedule(250, 50)) == poll_cohorts(b, Schedule(250, 50))


def test_sessions_do_not_carry_forward_and_spec_boundaries_are_visible():
    cohorts = generate("session-spec", InputFactors(500, 0, 0))
    old, new = poll_cohorts(project_arrivals(cohorts), Schedule(100, 0))
    a, b = old.samples[0], new.samples[0]
    assert a.stream.source.session_id != b.stream.source.session_id
    assert a.stream.observations[-1].received_wall_ns == 700 * MS
    assert b.stream.observations[0].received_wall_ns == 800 * MS
    assert b.stream.observations[0].ask_text is None
    assert [b.stream.observations[i].instrument_spec_version for i in (2, 3)] == ["v1", "v2"]
    assert broker_coverage((old, new), FIXED_TOLERANCE_MS)["decisions"] == 44
    truth = build_oracle(cohorts[1].histories[0])
    assert truth.episodes[0].window.censor_reason == "instrument_spec_changed"
    assert truth.episodes[1].window.left_censored


def test_clock_anomalies_are_excluded_without_rewriting_source_clocks():
    cohort = generate("clocks", InputFactors(25, 0, 0))[0]
    sample = poll_stream(
        cohort.histories[0].arrivals(), tuple(t * MS for t in (269, 270, 369, 370, 450, 600))
    )
    rows = sample.stream.observations
    assert rows[0].ask_text == "2000.20"
    assert Flag.PROCESSING_PENDING in rows[1].quality_flags
    assert Flag.PROCESSING_PENDING in rows[2].quality_flags
    assert Flag.WALL_CLOCK_REVERSAL in rows[3].quality_flags
    assert Flag.FUTURE_TIMESTAMP in rows[4].quality_flags
    assert rows[5].instrument_spec_version == "v2"
    assert rows[5].ask_text == "2000.22"


def test_observational_equivalence_with_distinct_p95_and_p99_truth():
    cases = counterexamples()
    assert [case["tail_percentile"] for case in cases] == [99, 95]
    assert [case["quiet"]["episodes"] for case in cases] == [0, 0]
    assert [case["hidden"]["episodes"] for case in cases] == [1, 2]
    for case in cases:
        assert case["quiet"]["oracle_tail"] == Decimal("0.20")
        assert case["hidden"]["oracle_tail"] == Decimal("0.90")
        assert (
            poll_stream(case["quiet"]["truth"].arrivals(), case["polls_ns"])
            == case["shared_sample"]
        )
        assert (
            poll_stream(case["hidden"]["truth"].arrivals(), case["polls_ns"])
            == case["shared_sample"]
        )


def test_asof_tolerance_only_changes_comparison_support():
    cohorts = generate("asynchronous", InputFactors(250, 100, 25))
    polls = poll_cohorts(project_arrivals(cohorts), Schedule(500, 0))
    short = broker_coverage(polls, 100)
    long = broker_coverage(polls, 500)
    assert short["coverage"] < long["coverage"]
    assert short["consensus_points"] == 0
    assert long["consensus_points"] > 0


def test_artifact_budget_and_no_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(factorial_experiment, "OUTPUT_LIMIT", 5)
    writer = Artifacts(tmp_path / "result")
    writer.write("first", (b"abc",))
    with pytest.raises(ValueError, match="output budget"):
        writer.write("too-large", (b"def",))
    with pytest.raises(FileExistsError):
        Artifacts(tmp_path / "result")
    assert "too-large" not in writer.index
