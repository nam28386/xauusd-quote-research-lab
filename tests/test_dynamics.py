from dataclasses import replace
from decimal import Decimal, localcontext

from xauusd_quote_lab.contracts import Flag
from xauusd_quote_lab.dynamics import WideningEvent, measure_dynamics
from xauusd_quote_lab.quality import PRICE_CONTEXT


def measure(stream, **options):
    return measure_dynamics(
        stream,
        **(
            {
                "start_ns": 100,
                "end_ns": 150,
                "max_age_ns": 20,
                "widening_threshold": Decimal("0.50"),
            }
            | options
        ),
    )


def test_hand_audited_golden_dynamics(streams):
    result = measure(streams[0])
    assert result.valid_snapshots == 4
    assert result.revision_count == 1
    assert result.snapshot_weighted_spread == Decimal("0.325")
    assert result.covered_ns == 30
    assert result.coverage == Decimal("0.6")
    with localcontext(PRICE_CONTEXT):
        assert result.duration_weighted_spread == Decimal(11) / 30
        assert result.revisions_per_covered_second == Decimal(1_000_000_000) / 30
    assert len(result.changes) == 2
    assert result.changes[0].delta_spread == 0
    change = result.changes[1]
    assert (change.delta_bid, change.delta_ask, change.delta_mid, change.delta_spread) == (
        Decimal(0),
        Decimal("0.35"),
        Decimal("0.175"),
        Decimal("0.35"),
    )
    assert result.widening == (WideningEvent(120, 130, 10, False, "missing_ask", False),)
    assert dict(result.exclusions) == {Flag.DUPLICATE_SNAPSHOT: 1, Flag.MISSING_ASK: 1}


def test_recovery_observed_and_threshold_inclusive(streams):
    stream = streams[0]
    rows = (stream.observations[0], stream.observations[2], stream.observations[4])
    result = measure(replace(stream, observations=rows), widening_threshold=Decimal("0.60"))
    assert result.widening == (WideningEvent(120, 140, 20, True, None, False),)


def test_outage_breaks_continuity_and_caps_coverage(streams):
    stream = streams[0]
    rows = (stream.observations[2], stream.observations[4])
    result = measure(replace(stream, observations=rows), max_age_ns=5)
    assert result.widening == (WideningEvent(120, 125, 5, False, "stale", True),)
    assert result.covered_ns == 5
    assert result.changes == ()
    assert result.revision_count == 0


def test_right_edge_and_window_without_observations(streams):
    active = measure(streams[0], end_ns=122)
    assert active.widening == (WideningEvent(120, 120, 0, False, "window_end", False),)
    empty = measure(streams[0], start_ns=141)
    assert empty.coverage == 0
    assert empty.duration_weighted_spread is None
    assert empty.snapshot_weighted_spread is None
    assert empty.revisions_per_covered_second is None


def test_metadata_version_breaks_deltas_and_censors_widening(streams):
    stream = streams[0]
    v2 = replace(stream.specs[0], spec_version="v2", tick_size=Decimal("0.001"))
    rows = (stream.observations[2], replace(stream.observations[4], instrument_spec_version="v2"))
    result = measure(replace(stream, specs=stream.specs + (v2,), observations=rows))
    assert result.valid_snapshots == 2
    assert result.changes == ()
    assert result.widening == (WideningEvent(120, 140, 20, False, "instrument_spec_changed", True),)


def test_regression_below_window_start_censors_instead_of_recovering(streams):
    stream = streams[0]
    wide = stream.observations[2]
    reversed_poll = replace(wide, poll_sequence=3, received_wall_ns=90, processing_wall_ns=125)
    narrow = stream.observations[4]
    result = measure(replace(stream, observations=(wide, reversed_poll, narrow)))
    assert result.widening == (WideningEvent(120, 120, 0, False, "wall_clock_reversal", True),)
    assert result.covered_ns == 0
    assert result.revision_count == 0
    assert dict(result.exclusions) == {Flag.WALL_CLOCK_REVERSAL: 1}
