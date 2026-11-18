import hashlib
import json
from dataclasses import replace
from decimal import Decimal, localcontext

import pytest

from xauusd_quote_lab.comparison import compare_brokers
from xauusd_quote_lab.contracts import Flag
from xauusd_quote_lab.dynamics import WideningEvent
from xauusd_quote_lab.quality import PRICE_CONTEXT
from xauusd_quote_lab.sampling import MS, poll_stream, poll_times
from xauusd_quote_lab.sampling_experiments import (
    configuration_grid,
    run_grid,
    summarize,
    write_experiment,
)
from xauusd_quote_lab.sampling_metrics import (
    TruthEpisode,
    build_oracle,
    match_episodes,
    score_sample,
    weighted_quantile,
)
from xauusd_quote_lab.sampling_truth import CLOCK, END_NS, State, history, scenarios


@pytest.fixture(scope="module")
def by_name():
    return {scenario.name: scenario for scenario in scenarios()}


@pytest.fixture(scope="module")
def grid():
    return run_grid()


def test_hand_calculated_short_spike_and_phase(by_name):
    stream = by_name["short-spike"].histories[0]
    oracle = build_oracle(stream)
    assert oracle.episodes[0].window == WideningEvent(
        120 * MS, 180 * MS, 60 * MS, True, None, False
    )
    misses = poll_stream(stream.arrivals(), (100 * MS, 200 * MS))
    assert [row.ask_text for row in misses.stream.observations] == ["2000.20", "2000.20"]
    detects = poll_stream(stream.arrivals(), (150 * MS,))
    assert detects.stream.observations[0].ask_text == "2000.90"
    edges = poll_stream(stream.arrivals(), (120 * MS - 1, 120 * MS, 180 * MS - 1, 180 * MS))
    assert [row.ask_text for row in edges.stream.observations] == [
        "2000.20",
        "2000.90",
        "2000.90",
        "2000.20",
    ]

    phase_0 = score_sample(
        poll_stream(stream.arrivals(), poll_times(END_NS, 100, 0, 0)), oracle, 100 * MS
    )
    phase_50 = score_sample(
        poll_stream(stream.arrivals(), poll_times(END_NS, 100, 50, 0)), oracle, 100 * MS
    )
    assert phase_0["events"]["missed"] == 1
    assert phase_0["spread"]["errors"]["snapshot_p99"]["signed"] == Decimal("-0.70")
    assert phase_50["events"]["recall"] == 1
    assert phase_50["revisions"]["matched"] == 2
    assert phase_50["revisions"]["missed"] == 0
    assert phase_50["revisions"]["duplicates"] == 19
    match = phase_50["events"]["matches"][0]
    assert (match["onset_error_ns"], match["recovery_error_ns"], match["duration_error_ns"]) == (
        30 * MS,
        70 * MS,
        40 * MS,
    )
    assert phase_50["spread"]["sampled"]["values"]["snapshot_p95"] == Decimal("0.20")
    assert phase_50["spread"]["sampled"]["values"]["snapshot_p99"] == Decimal("0.90")
    with localcontext(PRICE_CONTEXT):
        assert phase_50["spread"]["sampled"]["values"]["duration_mean"] == Decimal(7) / 30
        assert phase_50["spread"]["oracle"]["values"]["duration_mean"] == Decimal(241) / 1100


def test_receive_and_processing_boundaries_have_no_lookahead():
    base = history("cutoff", "alpha", State(0, "2000.20"), State(120, "2000.90", 130, 140))
    stream = base.arrivals()
    before = poll_stream(stream, (130 * MS - 1,))
    prefix = poll_stream(replace(stream, observations=stream.observations[:1]), (130 * MS - 1,))
    assert before == prefix
    sample = poll_stream(stream, (130 * MS, 140 * MS - 1, 140 * MS))
    assert [row.ask_text for row in sample.stream.observations] == [None, None, "2000.90"]
    assert sample.stream.observations[0].quality_flags == {Flag.PROCESSING_PENDING}
    assert sample.origins[:2] == (None, None)
    assert sample.origins[2].received_wall_ns == 130 * MS
    assert sample.origins[2].processing_wall_ns == 140 * MS
    assert sample.stream.observations[2].received_wall_ns == 140 * MS


def test_oracle_label_changes_cannot_modify_the_poll_projection(by_name):
    original = by_name["short-spike"].histories[0]
    relabeled = replace(
        original,
        events=(
            original.events[0],
            replace(original.events[1], event_ns=119 * MS, truth_exclusion="test_hidden_label"),
            original.events[2],
        ),
    )
    assert build_oracle(original) != build_oracle(relabeled)
    assert poll_stream(original.arrivals(), (100 * MS, 150 * MS)) == poll_stream(
        relabeled.arrivals(),
        (100 * MS, 150 * MS),
    )


def test_invalid_latest_poll_blocks_earlier_valid_and_zero_support(by_name):
    gaps = by_name["gaps"].histories[0]
    sampled = poll_stream(gaps.arrivals(), (600 * MS, 700 * MS, 1500 * MS, 1600 * MS))
    assert [row.ask_text for row in sampled.stream.observations] == [
        "2000.95",
        None,
        None,
        "2000.25",
    ]
    assert Flag.SOURCE_DISCONNECT in sampled.stream.observations[1].quality_flags
    assert Flag.CROSSED in sampled.stream.observations[2].quality_flags
    comparison = compare_brokers(
        (sampled.stream,), (700 * MS,), receive_clock_domain=CLOCK, max_age_ns=2000 * MS
    )
    assert comparison.points[0].eligible_broker_count == 0
    isolated = score_sample(poll_stream(gaps.arrivals(), (800 * MS,)), build_oracle(gaps), 100 * MS)
    assert isolated["spread"]["sampled"]["unavailable"]["snapshot_p99"] == "no_eligible_snapshots"
    assert isolated["spread"]["sampled"]["unavailable"]["duration_p95"] == "no_covered_duration"


def test_metadata_and_session_boundaries_are_explicit(by_name):
    clocks = by_name["clocks-metadata"].histories[0]
    raw = clocks.arrivals()
    sampled = poll_stream(raw, (400 * MS, 490 * MS, 600 * MS, 725 * MS, 800 * MS))
    assert [row.ask_text for row in sampled.stream.observations] == [
        "2000.22",
        None,
        None,
        None,
        "2000.80",
    ]
    assert Flag.WALL_CLOCK_REVERSAL in sampled.stream.observations[1].quality_flags
    assert Flag.UNKNOWN_UNIT in sampled.stream.observations[2].quality_flags
    assert Flag.FUTURE_TIMESTAMP in sampled.stream.observations[3].quality_flags
    assert sampled.stream.observations[4].instrument_spec_version == "v2"
    assert all(row.session_id == raw.source.session_id for row in sampled.stream.observations)
    with pytest.raises(ValueError, match="source or session"):
        replace(raw, observations=(replace(raw.observations[0], session_id="other"),))


def test_match_cannot_borrow_next_spec_witness_at_boundary():
    old = WideningEvent(100, 200, 100, False, "instrument_spec_changed", True)
    new = WideningEvent(200, 200, 0, False, "window_end", True)
    truth = (TruthEpisode(WideningEvent(190, 300, 110, False, "window_end", True), frozenset({2})),)
    matched = match_episodes((old, new), truth, [(100, 1, "v1"), (200, 2, "v2")])
    assert matched["false_episodes"] == [old]
    assert matched["matches"][0]["sample"] == new
    assert matched["matches"][0]["recovery_unavailable"] == "right_censored"


def test_nearest_rank_does_not_interpolate():
    values = ((Decimal("0.20"), 95), (Decimal("0.90"), 5))
    assert weighted_quantile(values, 95) == Decimal("0.20")
    assert weighted_quantile(values, 99) == Decimal("0.90")
    assert weighted_quantile(((Decimal("0.90"), 0),), 99) is None


def test_predeclared_grid_and_broker_tolerance_separation(grid):
    assert len(configuration_grid()) == 64
    assert len(grid) == 384
    summary = summarize(grid)
    assert len(summary["configurations"]) == 16
    assert len(summary["phase_sensitivity"]) == 16
    async_rows = [
        row
        for row in grid
        if row["scenario"] == "asynchronous"
        and row["interval_ms"] == 250
        and row["phase_percent"] == 0
    ]
    assert [row["tolerance_ms"] for row in async_rows] == [100, 250, 500, 1000]
    assert all(row["streams"] == async_rows[0]["streams"] for row in async_rows)
    assert async_rows[0]["broker"]["consensus_points"] == 0
    assert async_rows[-1]["broker"]["consensus_points"] > 0
    assert async_rows[-1]["broker"]["coverage"] > async_rows[0]["broker"]["coverage"]
    assert all(len(row["broker"]["points"]) == 44 for row in grid)
    assert [item["events_detected"] for item in summary["configurations"][::4]] == [53, 47, 27, 14]


def test_artifacts_are_deterministic_and_linked(tmp_path):
    outputs = [tmp_path / name for name in ("first", "second")]
    sha = "b" * 40
    for output in outputs:
        write_experiment(output, sha, "a" * 64)
    first, second = outputs
    assert sorted(path.name for path in first.iterdir()) == sorted(
        path.name for path in second.iterdir()
    )
    for path in first.iterdir():
        assert path.read_bytes() == (second / path.name).read_bytes()
    manifest = json.loads((first / "manifest.json").read_bytes())
    assert manifest["code_sha"] == sha
    assert manifest["row_count"] == 384
    assert manifest["window_end_ns"] == "2200000000"
    for name, details in manifest["artifacts"].items():
        payload = (first / name).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == details["sha256"]
        if name.startswith("evidence-"):
            assert len(payload) <= 65_536
            packet = json.loads(payload)
            assert packet["code_sha"] == sha
            assert (
                packet["inputs"][0]["sha256"]
                == manifest["inputs"][packet["inputs"][0]["fixture_id"]]["sha256"]
            )
            assert (
                dict(packet["parameters"])["results_sha256"]
                == manifest["artifacts"]["results.json"]["sha256"]
            )
