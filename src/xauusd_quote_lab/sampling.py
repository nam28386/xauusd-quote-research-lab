"""Point-in-time polling of recorded synthetic arrivals. No oracle inputs."""

from collections.abc import Sequence
from dataclasses import dataclass

from .contracts import Flag, QuoteObservation, QuoteStream
from .quality import evaluate_stream

MS = 1_000_000
POLL_INTERVALS_MS = (100, 250, 500, 1000)
ASOF_TOLERANCES_MS = (100, 250, 500, 1000)
PHASE_PERCENT = (0, 25, 50, 75)
POLL_VERSION = "p2-poll-v1"


@dataclass(frozen=True, slots=True)
class PollOrigin:
    sequence: int
    received_wall_ns: int
    processing_wall_ns: int


@dataclass(frozen=True, slots=True)
class PollSample:
    stream: QuoteStream
    origins: tuple[PollOrigin | None, ...]


def poll_times(end_ns: int, interval_ms: int, phase_percent: int, source_index: int) -> range:
    step = interval_ms * MS
    # Stagger all source schedules by a predeclared quarter period.
    offset = step * ((phase_percent + source_index * 25) % 100) // 100
    return range(offset, end_ns, step)


def poll_stream(stream: QuoteStream, decisions_ns: Sequence[int]) -> PollSample:
    if any(type(t) is not int or t < 0 for t in decisions_ns) or any(
        a >= b for a, b in zip(decisions_ns, decisions_ns[1:])
    ):
        raise ValueError("Poll decisions must be strictly increasing nonnegative nanoseconds")
    if not stream.specs:
        raise ValueError("Polling requires a declared initial instrument spec")

    rows = []
    origins = []
    for sequence, decision in enumerate(decisions_ns):
        visible = evaluate_stream(stream, decision)
        row, quality, prices = visible[-1] if visible else (None, None, None)
        flags = quality.flags if quality else frozenset({Flag.NO_OBSERVATION})
        ready = row is not None and Flag.PROCESSING_PENDING not in flags
        rows.append(
            QuoteObservation(
                row.bid_text if prices is not None else None,
                row.ask_text if prices is not None else None,
                row.source_time_ms_or_null if prices is not None else None,
                decision,
                decision,
                sequence,
                stream.source.source_id,
                stream.source.session_id,
                row.instrument_spec_version if ready else stream.specs[0].spec_version,
                quality_flags=flags,
            )
        )
        origins.append(
            PollOrigin(row.poll_sequence, row.received_wall_ns, row.processing_wall_ns)
            if prices is not None
            else None
        )
    return PollSample(
        QuoteStream(
            stream.source,
            stream.specs,
            tuple(rows),
            stream.receive_clock_domain,
            stream.source_clock_comparable,
        ),
        tuple(origins),
    )
