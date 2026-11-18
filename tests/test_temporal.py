from dataclasses import replace
from decimal import Decimal

from xauusd_quote_lab.comparison import compare_brokers
from xauusd_quote_lab.contracts import Flag
from xauusd_quote_lab.dynamics import WideningEvent, measure_dynamics
from xauusd_quote_lab.replay import CLOCK


def compare(stream, *times):
    return compare_brokers((stream,), times, receive_clock_domain=CLOCK, max_age_ns=50).points


def test_receive_t_plus_one_never_visible(one_row):
    stream = one_row((100, 101))
    baseline = replace(stream, observations=stream.observations[:1])
    assert compare(stream, 99, 100) == compare(baseline, 99, 100)
    assert compare(stream, 99)[0].matches[0].exclusions == {Flag.NO_OBSERVATION}
    assert compare(stream, 101)[0].matches[0].poll_sequence == 1


def test_processing_pending_blocks_old_observation_and_hides_quality(one_row):
    stream = one_row((100, 110))
    later = replace(stream.observations[1], processing_wall_ns=130, ask_text=None)
    stream = replace(stream, observations=(stream.observations[0], later))
    before, pending, processed = compare(stream, 109, 110, 130)
    assert before.matches[0].prices is not None
    assert pending.matches[0].exclusions == {Flag.PROCESSING_PENDING}
    assert processed.matches[0].exclusions == {Flag.MISSING_ASK}


def test_reversed_wall_quarantines_stream_and_breaks_widening(one_row):
    stream = one_row((100, 120, 110, 115), ask_text="2000.70")
    point = compare(stream, 125)[0]
    assert point.matches[0].poll_sequence == 3
    assert point.matches[0].exclusions == {Flag.WALL_CLOCK_REVERSAL}
    result = measure_dynamics(
        stream, start_ns=100, end_ns=125, max_age_ns=50, widening_threshold=Decimal("0.5")
    )
    assert result.widening == (WideningEvent(100, 120, 20, False, "wall_clock_reversal", True),)
    assert result.covered_ns == 20


def test_regressed_timestamp_cannot_bring_later_poll_into_the_past(one_row):
    stream = one_row((100, 120, 110, 115))
    assert compare(stream, 115)[0].matches[0].poll_sequence == 0
    assert compare(stream, 120)[0].matches[0].exclusions == {Flag.WALL_CLOCK_REVERSAL}


def test_source_clock_future_requires_explicit_comparability(one_row):
    stream = one_row((100,), source_time_ms_or_null=1)
    assert compare(stream, 100)[0].matches[0].prices is not None
    point = compare(replace(stream, source_clock_comparable=True), 100)[0]
    assert point.matches[0].exclusions == {Flag.FUTURE_TIMESTAMP}


def test_source_out_of_order_and_monotonic_not_wall(one_row):
    stream = one_row((100, 110))
    first = replace(stream.observations[0], source_time_ms_or_null=11, received_monotonic_ns=900)
    second = replace(stream.observations[1], source_time_ms_or_null=10, received_monotonic_ns=1)
    point = compare(replace(stream, observations=(first, second)), 110)[0]
    assert point.matches[0].exclusions == {Flag.SOURCE_OUT_OF_ORDER}


def test_equal_receive_timestamp_uses_last_poll_sequence(one_row):
    stream = one_row((100, 100))
    invalid = replace(stream.observations[1], ask_text=None)
    point = compare(replace(stream, observations=(stream.observations[0], invalid)), 100)[0]
    assert point.matches[0].poll_sequence == 1
    assert point.matches[0].prices is None


def test_malformed_wall_clock_cannot_hide_future_source_or_poison_watermark(one_row):
    stream = one_row((1_000_000, 2_000_000))
    first, next_row = stream.observations
    malformed = replace(first, processing_wall_ns=-1, source_time_ms_or_null=10)
    legitimate = replace(next_row, source_time_ms_or_null=2)
    points = compare(
        replace(stream, observations=(malformed, legitimate), source_clock_comparable=True),
        1_000_000,
        2_000_000,
    )
    assert points[0].matches[0].exclusions == {Flag.INVALID_TIMESTAMP, Flag.FUTURE_TIMESTAMP}
    assert points[1].matches[0].prices is not None
