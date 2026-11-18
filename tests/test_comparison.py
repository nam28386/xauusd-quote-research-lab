from dataclasses import replace
from decimal import Decimal

import pytest

from xauusd_quote_lab.comparison import compare_brokers
from xauusd_quote_lab.contracts import Environment, Flag
from xauusd_quote_lab.replay import CLOCK


def compare(streams, decisions=(125,), **options):
    return compare_brokers(
        streams,
        decisions,
        **({"receive_clock_domain": CLOCK, "max_age_ns": 20} | options),
    )


@pytest.mark.parametrize(
    "n, mode, spread, mid",
    [
        (1, "descriptive", None, None),
        (2, "pairwise", None, None),
        (3, "consensus", "0.40", "2000.35"),
        (4, "consensus", "0.45", "2000.375"),
    ],
)
def test_distinct_broker_thresholds(streams, n, mode, spread, mid):
    result = compare(streams[:n], max_age_ns=30)
    point = result.points[0]
    assert point.eligible_broker_count == n
    assert point.mode == mode
    assert point.median_spread == (Decimal(spread) if spread else None)
    assert point.median_mid == (Decimal(mid) if mid else None)
    assert result.valid_coverage == 1
    if n == 2:
        assert point.pairwise.aliases == ("alpha", "beta")
        assert point.pairwise.mid_difference == Decimal("0.20")
        assert point.pairwise.spread_difference == Decimal("0.20")
    else:
        assert point.pairwise is None


def test_latest_invalid_never_falls_back(streams):
    result = compare(streams, (125, 130))
    latest = result.points[1]
    alpha = latest.matches[0]
    assert alpha.poll_sequence == 3
    assert alpha.age_ns == 0
    assert alpha.prices is None
    assert alpha.exclusions == {Flag.MISSING_ASK}
    assert result.valid_coverage == Decimal("0.875")
    assert result.unmatched_count == 1
    assert result.matched_age_ns == tuple(sorted((5, 10, 7, 0, 15, 12, 5)))


def test_duplicate_accounts_require_predeclared_representative(streams):
    alpha = streams[0]
    other = replace(
        alpha,
        source=replace(alpha.source, source_id="alpha-other"),
        observations=tuple(replace(row, source_id="alpha-other") for row in alpha.observations),
    )
    inputs = (alpha, other, *streams[1:3])
    point = compare(inputs).points[0]
    assert point.eligible_broker_count == 2
    assert point.median_mid is None
    assert all(Flag.AMBIGUOUS_BROKER in item.exclusions for item in point.matches[:2])
    result = compare(inputs, (125, 130), representatives={"alpha": "alpha"})
    assert result.points[0].eligible_broker_count == 3
    assert result.points[1].eligible_broker_count == 2
    assert Flag.NON_REPRESENTATIVE in result.points[0].matches[1].exclusions


def test_real_demo_are_distinct_and_have_cost_limitation(streams):
    result = compare(streams[1:3])
    assert [item.environment for item in result.points[0].matches] == [
        Environment.REAL,
        Environment.DEMO,
    ]
    assert any("non-equivalent" in text for text in result.limitations)


def test_clock_compatibility_and_staleness(streams):
    result = compare(
        (replace(streams[0], receive_clock_domain="unrelated"), streams[1]),
        (125, 126),
        max_age_ns=10,
    )
    assert result.points[0].matches[0].exclusions == {Flag.CLOCK_INCOMPATIBLE}
    assert result.points[0].matches[1].prices is not None
    assert result.points[1].matches[1].exclusions == {Flag.STALE}
    assert result.consensus_coverage == 0


def test_metadata_mismatch_removes_consensus(streams):
    gamma = replace(streams[2], specs=(replace(streams[2].specs[0], quote_currency="VND"),))
    result = compare((*streams[:2], gamma))
    assert result.points[0].eligible_broker_count == 2
    assert result.points[0].median_mid is None
    assert result.points[0].matches[2].exclusions == {Flag.UNKNOWN_UNIT}
