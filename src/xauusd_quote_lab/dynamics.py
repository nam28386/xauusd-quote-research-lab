"""Versioned descriptive dynamics on bounded receive-time intervals."""

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, localcontext
from itertools import dropwhile
from typing import ClassVar

from .contracts import Flag, QuoteStream
from .quality import PRICE_CONTEXT, QuotedPrices, evaluate_stream


@dataclass(frozen=True, slots=True)
class QuoteChange:
    poll_sequence: int
    delta_bid: Decimal
    delta_ask: Decimal
    delta_mid: Decimal
    delta_spread: Decimal


@dataclass(frozen=True, slots=True)
class WideningEvent:
    observed_start_ns: int
    observed_end_ns: int
    duration_ns: int
    recovered: bool
    censor_reason: str | None
    left_censored: bool


@dataclass(frozen=True, slots=True)
class QuoteDynamics:
    VERSION: ClassVar[str] = "quote-dynamics-v1.1"
    source_id: str
    session_id: str
    start_ns: int
    end_ns: int
    max_age_ns: int
    widening_threshold: Decimal
    valid_snapshots: int
    revision_count: int
    revisions_per_covered_second: Decimal | None
    snapshot_weighted_spread: Decimal | None
    duration_weighted_spread: Decimal | None
    covered_ns: int
    coverage: Decimal
    changes: tuple[QuoteChange, ...]
    widening: tuple[WideningEvent, ...]
    exclusions: tuple[tuple[Flag, int], ...]


def measure_dynamics(
    stream: QuoteStream,
    *,
    start_ns: int,
    end_ns: int,
    max_age_ns: int,
    widening_threshold: Decimal,
) -> QuoteDynamics:
    if any(type(value) is not int for value in (start_ns, end_ns, max_age_ns)) or (
        not 0 <= start_ns < end_ns or max_age_ns <= 0
    ):
        raise ValueError("Expected a nonempty nanosecond window and positive max age")
    if (
        not isinstance(widening_threshold, Decimal)
        or not widening_threshold.is_finite()
        or widening_threshold <= 0
    ):
        raise ValueError("Expected a finite positive Decimal widening threshold")

    # Drop the leading pre-window prefix only. A later regressed poll still breaks continuity.
    rows = tuple(
        dropwhile(
            lambda item: item[0].received_wall_ns < start_ns,
            evaluate_stream(stream, end_ns),
        )
    )
    changes = []
    events = []
    exclusions: Counter[Flag] = Counter()
    snapshots = revisions = covered = 0
    spread_sum = weighted_sum = Decimal(0)
    previous: QuotedPrices | None = None
    open_start: int | None = None
    left_censored = False

    with localcontext(PRICE_CONTEXT):
        for index, (row, quality, prices) in enumerate(rows):
            exclusions.update(quality.exclusions | (quality.flags & {Flag.PARTIAL_COVERAGE}))
            if prices is None:
                previous = None
                continue

            if previous is not None:
                delta = QuoteChange(
                    row.poll_sequence,
                    prices.bid - previous.bid,
                    prices.ask - previous.ask,
                    prices.mid - previous.mid,
                    prices.spread - previous.spread,
                )
                changes.append(delta)
                if prices == previous or Flag.DUPLICATE_SNAPSHOT in quality.flags:
                    exclusions[Flag.DUPLICATE_SNAPSHOT] += 1
                else:
                    revisions += 1
            elif Flag.DUPLICATE_SNAPSHOT in quality.flags:
                exclusions[Flag.DUPLICATE_SNAPSHOT] += 1

            received = row.received_wall_ns
            snapshots += 1
            spread_sum += prices.spread
            if prices.spread >= widening_threshold and open_start is None:
                open_start = received
                left_censored = previous is None

            boundary = received
            censor_reason = "window_end"
            next_prices = None
            if index + 1 < len(rows):
                next_row, next_quality, next_prices = rows[index + 1]
                if (
                    next_row.received_wall_ns < received
                    or Flag.WALL_CLOCK_REVERSAL in next_quality.flags
                ):
                    censor_reason = Flag.WALL_CLOCK_REVERSAL.value
                else:
                    boundary = min(next_row.received_wall_ns, received + max_age_ns)
                    if next_row.received_wall_ns > received + max_age_ns:
                        censor_reason = Flag.STALE.value
                        exclusions[Flag.STALE] += 1
                    elif next_prices is None:
                        censor_reason = ",".join(sorted(next_quality.exclusions))
                    elif next_row.instrument_spec_version != row.instrument_spec_version:
                        censor_reason = "instrument_spec_changed"
                    else:
                        censor_reason = None
            duration = boundary - received
            covered += duration
            weighted_sum += prices.spread * duration
            recovered = (
                censor_reason is None
                and next_prices is not None
                and next_prices.spread < widening_threshold
            )
            if open_start is not None and (censor_reason is not None or recovered):
                events.append(
                    WideningEvent(
                        open_start,
                        boundary,
                        boundary - open_start,
                        recovered,
                        censor_reason,
                        left_censored,
                    )
                )
                open_start = None
            previous = prices if censor_reason is None else None

        return QuoteDynamics(
            stream.source.source_id,
            stream.source.session_id,
            start_ns,
            end_ns,
            max_age_ns,
            widening_threshold,
            snapshots,
            revisions,
            Decimal(revisions) * 1_000_000_000 / covered if covered else None,
            spread_sum / snapshots if snapshots else None,
            weighted_sum / covered if covered else None,
            covered,
            Decimal(covered) / (end_ns - start_ns),
            tuple(changes),
            tuple(events),
            tuple(sorted(exclusions.items())),
        )
