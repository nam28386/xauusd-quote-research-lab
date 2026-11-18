"""Eligibility checks and exact quoted-price arithmetic."""

import re
from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from typing import ClassVar

from .contracts import Flag, InstrumentSpec, PriceUnit, QuoteObservation, QuoteStream

PRICE_CONTEXT = Context(prec=128)
PRICE_TEXT = re.compile(r"[0-9]{1,32}(?:\.[0-9]{1,32})?")
NONBLOCKING = frozenset({Flag.DUPLICATE_SNAPSHOT, Flag.PARTIAL_COVERAGE})


@dataclass(frozen=True, slots=True)
class QualityState:
    VERSION: ClassVar[str] = "quality-state-v1"
    flags: frozenset[Flag]

    def __post_init__(self) -> None:
        object.__setattr__(self, "flags", frozenset(Flag(flag) for flag in self.flags))

    @property
    def exclusions(self) -> frozenset[Flag]:
        return self.flags - NONBLOCKING

    @property
    def eligible(self) -> bool:
        return not self.exclusions


@dataclass(frozen=True, slots=True)
class QuotedPrices:
    bid: Decimal
    ask: Decimal

    @property
    def spread(self) -> Decimal:
        with localcontext(PRICE_CONTEXT):
            return self.ask - self.bid

    @property
    def mid(self) -> Decimal:
        with localcontext(PRICE_CONTEXT):
            return (self.ask + self.bid) / 2


def parse_price(value: str | None) -> Decimal | None:
    if not isinstance(value, str) or not PRICE_TEXT.fullmatch(value):
        return None
    price = Decimal(value)
    return price if price > 0 else None


def inspect_quote(
    row: QuoteObservation,
    spec: InstrumentSpec | None,
    *,
    source_clock_comparable: bool = False,
) -> tuple[QualityState, QuotedPrices | None]:
    flags = set(row.quality_flags)
    source_ms = row.source_time_ms_or_null
    bid, ask = parse_price(row.bid_text), parse_price(row.ask_text)
    if bid is None:
        flags.add(Flag.MISSING_BID if row.bid_text is None else Flag.INVALID_BID)
    if ask is None:
        flags.add(Flag.MISSING_ASK if row.ask_text is None else Flag.INVALID_ASK)
    if bid is not None and ask is not None and bid > ask:
        flags.add(Flag.CROSSED)
    if spec is None or spec.spec_version != row.instrument_spec_version:
        flags.add(Flag.UNKNOWN_SPEC)
    else:
        if spec.canonical_symbol != "XAUUSD":
            flags.add(Flag.UNSUPPORTED_INSTRUMENT)
        if spec.price_unit != PriceUnit.USD_PER_TROY_OUNCE or spec.quote_currency != "USD":
            flags.add(Flag.UNKNOWN_UNIT)

    clocks = (row.received_wall_ns, row.processing_wall_ns, source_ms, row.received_monotonic_ns)
    if any(type(clock) is not int or clock < 0 for clock in clocks[:2]) or any(
        clock is not None and (type(clock) is not int or clock < 0) for clock in clocks[2:]
    ):
        flags.add(Flag.INVALID_TIMESTAMP)
    else:
        if row.processing_wall_ns < row.received_wall_ns:
            flags.add(Flag.WALL_CLOCK_REVERSAL)
        if source_clock_comparable and source_ms is not None:
            if source_ms * 1_000_000 > row.received_wall_ns:
                flags.add(Flag.FUTURE_TIMESTAMP)

    quality = QualityState(frozenset(flags))
    prices = (
        QuotedPrices(bid, ask) if quality.eligible and bid is not None and ask is not None else None
    )
    return quality, prices


def evaluate_stream(
    stream: QuoteStream, decision_wall_ns: int
) -> tuple[tuple[QuoteObservation, QualityState, QuotedPrices | None], ...]:
    """Evaluate the observable poll prefix without exposing future processing state."""
    specs = {spec.spec_version: spec for spec in stream.specs}
    checked = []
    receive_high = processing_high = source_high = -1
    processing_pending = False
    for row in stream.observations:
        if row.received_wall_ns > decision_wall_ns:
            # A later poll cannot precede an as-yet-unreceived earlier poll.
            break
        processing_pending = processing_pending or (
            type(row.processing_wall_ns) is int and row.processing_wall_ns > decision_wall_ns
        )
        if processing_pending:
            checked.append((row, QualityState(frozenset({Flag.PROCESSING_PENDING})), None))
            continue
        quality, prices = inspect_quote(
            row,
            specs.get(row.instrument_spec_version),
            source_clock_comparable=stream.source_clock_comparable,
        )
        flags = set(quality.flags)
        if row.received_wall_ns < receive_high:
            flags.add(Flag.WALL_CLOCK_REVERSAL)
        receive_high = max(receive_high, row.received_wall_ns)
        if type(row.processing_wall_ns) is int:
            if row.processing_wall_ns < processing_high:
                flags.add(Flag.WALL_CLOCK_REVERSAL)
            processing_high = max(processing_high, row.processing_wall_ns)
        source_ms = row.source_time_ms_or_null
        if type(source_ms) is int:
            if 0 <= source_ms < source_high:
                flags.add(Flag.SOURCE_OUT_OF_ORDER)
            if Flag.FUTURE_TIMESTAMP not in flags:
                source_high = max(source_high, source_ms)
        quality = QualityState(frozenset(flags))
        checked.append((row, quality, prices if quality.eligible else None))
    return tuple(checked)
