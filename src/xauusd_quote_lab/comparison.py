"""Backward-as-of comparisons on explicitly compatible receive clocks."""

from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal, localcontext
from statistics import median
from typing import ClassVar

from .contracts import Environment, Flag, QuoteObservation, QuoteStream
from .quality import PRICE_CONTEXT, QualityState, QuotedPrices, evaluate_stream


@dataclass(frozen=True, slots=True)
class BrokerMatch:
    source_id: str
    session_id: str
    broker_alias: str
    environment: Environment
    poll_sequence: int | None = None
    spec_version: str | None = None
    age_ns: int | None = None
    prices: QuotedPrices | None = None
    exclusions: frozenset[Flag] = frozenset()


@dataclass(frozen=True, slots=True)
class Pairwise:
    aliases: tuple[str, str]
    mid_difference: Decimal
    spread_difference: Decimal


@dataclass(frozen=True, slots=True)
class ComparisonPoint:
    decision_wall_ns: int
    matches: tuple[BrokerMatch, ...]
    eligible_broker_count: int
    mode: str
    unavailable_reasons: tuple[str, ...]
    pairwise: Pairwise | None
    median_spread: Decimal | None
    median_mid: Decimal | None


@dataclass(frozen=True, slots=True)
class BrokerComparison:
    VERSION: ClassVar[str] = "broker-comparison-v1.1"
    receive_clock_domain: str
    max_age_ns: int
    representatives: tuple[tuple[str, str], ...]
    points: tuple[ComparisonPoint, ...]
    unmatched_count: int
    exclusion_counts: tuple[tuple[Flag, int], ...]
    matched_age_ns: tuple[int, ...]
    valid_coverage: Decimal | None
    consensus_coverage: Decimal | None
    limitations: tuple[str, ...]


def match_stream(
    stream: QuoteStream, decision: int, clock_domain: str, max_age: int
) -> BrokerMatch:
    source = stream.source
    base = BrokerMatch(source.source_id, source.session_id, source.broker_alias, source.environment)
    if stream.receive_clock_domain != clock_domain:
        return replace(base, exclusions=frozenset({Flag.CLOCK_INCOMPATIBLE}))
    visible = evaluate_stream(stream, decision)
    if not visible:
        return replace(base, exclusions=frozenset({Flag.NO_OBSERVATION}))
    row, state, prices = visible[-1]
    return match_observation(base, row, state, prices, decision, max_age)


def match_observation(
    base: BrokerMatch,
    row: QuoteObservation,
    state: QualityState,
    prices: QuotedPrices | None,
    decision: int,
    max_age: int,
) -> BrokerMatch:
    age = decision - row.received_wall_ns
    exclusions = state.exclusions | ({Flag.STALE} if age > max_age else set())
    return replace(
        base,
        poll_sequence=row.poll_sequence,
        spec_version=row.instrument_spec_version,
        age_ns=age,
        prices=None if exclusions else prices,
        exclusions=exclusions,
    )


def match_decisions(
    stream: QuoteStream, decisions: Sequence[int], clock_domain: str, max_age: int
) -> Iterator[BrokerMatch]:
    if not decisions:
        return
    source = stream.source
    base = BrokerMatch(source.source_id, source.session_id, source.broker_alias, source.environment)
    if stream.receive_clock_domain != clock_domain:
        for _ in decisions:
            yield replace(base, exclusions=frozenset({Flag.CLOCK_INCOMPATIBLE}))
        return

    # Process each row that can arrive by the last decision once. Quality state
    # is exposed only after the entire visible prefix passes its processing watermark.
    checked = evaluate_stream(stream, decisions[-1])
    index = 0
    processing_high = -1
    pending = QualityState(frozenset({Flag.PROCESSING_PENDING}))
    for decision in decisions:
        while index < len(checked) and checked[index][0].received_wall_ns <= decision:
            processing_ns = checked[index][0].processing_wall_ns
            if type(processing_ns) is int:
                processing_high = max(processing_high, processing_ns)
            index += 1
        if index == 0:
            yield replace(base, exclusions=frozenset({Flag.NO_OBSERVATION}))
            continue
        row, state, prices = checked[index - 1]
        if processing_high > decision:
            state, prices = pending, None
        yield match_observation(base, row, state, prices, decision, max_age)


def compare_brokers(
    streams: Sequence[QuoteStream],
    decisions_wall_ns: Sequence[int],
    *,
    receive_clock_domain: str,
    max_age_ns: int,
    representatives: Mapping[str, str] | None = None,
) -> BrokerComparison:
    if not 1 <= len(streams) <= 4 or len({s.source.source_id for s in streams}) != len(streams):
        raise ValueError("Provide one to four distinct source IDs")
    if not receive_clock_domain.strip() or type(max_age_ns) is not int or max_age_ns <= 0:
        raise ValueError("Declare a receive clock domain and a positive age tolerance")
    if any(type(t) is not int or t < 0 for t in decisions_wall_ns) or any(
        a >= b for a, b in zip(decisions_wall_ns, decisions_wall_ns[1:])
    ):
        raise ValueError("Decisions must be strictly increasing nonnegative nanosecond timestamps")

    groups: dict[str, list[str]] = {}
    for stream in streams:
        groups.setdefault(stream.source.broker_alias, []).append(stream.source.source_id)
    chosen = dict(representatives or {})
    if any(source_id not in groups.get(alias, []) for alias, source_id in chosen.items()):
        raise ValueError("Representatives must belong to the declared broker and input streams")

    points = []
    ages = []
    exclusions: Counter[Flag] = Counter()
    unmatched = 0
    with localcontext(PRICE_CONTEXT):
        matches_by_stream = [
            match_decisions(stream, decisions_wall_ns, receive_clock_domain, max_age_ns)
            for stream in sorted(streams, key=lambda item: item.source.source_id)
        ]
        for decision, decision_matches in zip(
            decisions_wall_ns, zip(*matches_by_stream, strict=True), strict=True
        ):
            matches = []
            eligible: list[tuple[str, QuotedPrices]] = []
            for match in decision_matches:
                alias = match.broker_alias
                reason = None
                if len(groups[alias]) > 1:
                    if alias not in chosen:
                        reason = Flag.AMBIGUOUS_BROKER
                    elif chosen[alias] != match.source_id:
                        reason = Flag.NON_REPRESENTATIVE
                if reason is not None:
                    match = replace(match, prices=None, exclusions=match.exclusions | {reason})
                if match.prices is not None and match.age_ns is not None:
                    ages.append(match.age_ns)
                    eligible.append((alias, match.prices))
                else:
                    unmatched += 1
                    exclusions.update(match.exclusions)
                matches.append(match)

            count = len(eligible)
            pair = None
            median_spread = median_mid = None
            unavailable = []
            if count < len(groups):
                unavailable.append(Flag.PARTIAL_COVERAGE.value)
            if count < 3:
                unavailable.append("fewer_than_three_eligible_brokers")
            if count == 2:
                (alias_a, a), (alias_b, b) = sorted(eligible)
                pair = Pairwise((alias_a, alias_b), a.mid - b.mid, a.spread - b.spread)
            if count >= 3:
                median_spread = median([price.spread for _, price in eligible])
                median_mid = median([price.mid for _, price in eligible])
            points.append(
                ComparisonPoint(
                    decision,
                    tuple(matches),
                    count,
                    ("unavailable", "descriptive", "pairwise", "consensus")[min(count, 3)],
                    tuple(unavailable),
                    pair,
                    median_spread,
                    median_mid,
                )
            )

        total = len(points) * len(streams)
        return BrokerComparison(
            receive_clock_domain,
            max_age_ns,
            tuple(sorted(chosen.items())),
            tuple(points),
            unmatched,
            tuple(sorted(exclusions.items())),
            tuple(sorted(ages)),
            Decimal(len(ages)) / total if total else None,
            Decimal(sum(point.eligible_broker_count >= 3 for point in points)) / len(points)
            if points
            else None,
            (
                "Broker aliases do not establish economic independence.",
                "Matching age is not network latency.",
                "REAL and DEMO are labels with non-equivalent execution conditions.",
                "Quoted differences do not establish executable arbitrage or realized costs.",
            ),
        )
