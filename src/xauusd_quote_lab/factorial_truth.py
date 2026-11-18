"""Predeclared immutable synthetic scenarios for the P2.1 factorial design."""

from dataclasses import dataclass
from itertools import product

from .contracts import Flag
from .sampling import MS, PHASE_PERCENT, POLL_INTERVALS_MS
from .sampling_truth import END_NS, EventHistory, State, history

DURATIONS_MS = (25, 50, 100, 250, 500, 1000)
TRANSPORT_MS = (0, 25, 100, 250)
PROCESSING_MS = (0, 25, 100)
SCENARIOS = ("isolated", "clustered", "asynchronous", "gaps", "session-spec", "clocks")
FIXED_TOLERANCE_MS = 250
ONSET_MS = 125
TRUTH_VERSION = "p21-factorial-truth-v1"


@dataclass(frozen=True, slots=True)
class InputFactors:
    duration_ms: int
    transport_ms: int
    processing_ms: int


@dataclass(frozen=True, slots=True)
class Schedule:
    interval_ms: int
    phase_percent: int


@dataclass(frozen=True, slots=True)
class Cohort:
    start_ns: int
    end_ns: int
    histories: tuple[EventHistory, ...]


def inputs() -> tuple[InputFactors, ...]:
    return tuple(
        InputFactors(*factors) for factors in product(DURATIONS_MS, TRANSPORT_MS, PROCESSING_MS)
    )


def schedules() -> tuple[Schedule, ...]:
    return tuple(Schedule(*factors) for factors in product(POLL_INTERVALS_MS, PHASE_PERCENT))


def generate(name: str, factors: InputFactors) -> tuple[Cohort, ...]:
    d, transport, processing = factors.duration_ms, factors.transport_ms, factors.processing_ms

    def state(
        time: int, ask: str | None, *, spec="v1", reason=None, stagger=0, flags=frozenset()
    ) -> State:
        # Seed at the common origin represents an already available opening quote.
        receive = time + transport + stagger if time else 0
        processed = receive + processing if time else 0
        return State(time, ask, receive, processed, time, spec, reason, flags)

    end = ONSET_MS + d
    opening = state(0, "2000.20")
    isolated = (opening, state(ONSET_MS, "2000.90"), state(end, "2000.20"))

    if name == "isolated":
        series = (history(name, "alpha", *isolated),)
    elif name == "clustered":
        series = (
            history(
                name, "alpha", *isolated, state(end + 50, "2001.10"), state(end + 50 + d, "2000.20")
            ),
        )
    elif name == "asynchronous":
        series = tuple(
            history(
                name,
                alias,
                state(0, narrow),
                state(ONSET_MS + lag, wide, stagger=stagger),
                state(end + lag, narrow, stagger=stagger),
            )
            for alias, lag, stagger, narrow, wide in (
                ("alpha", 0, 0, "2000.20", "2000.90"),
                ("beta", 95, 15, "2000.25", "2000.85"),
                ("gamma", 205, 40, "2000.30", "2001.10"),
                ("delta", 305, 55, "2000.35", "2000.80"),
            )
        )
    elif name == "gaps":
        gap = ONSET_MS + d // 2
        series = (
            history(
                name,
                "alpha",
                *isolated[:2],
                state(gap, None, reason="disconnected", flags=frozenset({Flag.SOURCE_DISCONNECT})),
                state(end + 10, "1999.90", reason="crossed"),
                state(end + 50, "2000.20"),
            ),
        )
    elif name == "session-spec":
        boundary = 800
        old = [opening, state(200, "2000.90")]
        if 200 + d < boundary:
            old.append(state(200 + d, "2000.20"))
        old.append(
            State(
                boundary,
                None,
                source_ms=boundary,
                reason="session_closed",
                flags=frozenset({Flag.SOURCE_DISCONNECT}),
            )
        )
        second_end = 1000 + d
        new = [state(850, "2000.24"), state(1000, "2000.90")]
        if second_end < 1040:
            new.append(state(second_end, "2000.24"))
        new.append(state(1040, "2000.90" if second_end > 1040 else "2000.24", spec="v2"))
        if second_end > 1040:
            new.append(state(second_end, "2000.24", spec="v2"))
        return (
            Cohort(0, boundary * MS, (history("session-old", "alpha", *old),)),
            Cohort(boundary * MS, END_NS, (history("session-new", "alpha", *new),)),
        )
    elif name == "clocks":
        a, b, c = end + 40, end + 50, end + 300
        series = (
            history(
                name,
                "alpha",
                *isolated,
                State(a, "2000.25", a + transport + 80, a + transport + processing + 180, a),
                State(
                    b,
                    "2000.90",
                    b + transport,
                    b + transport + processing + 110,
                    b,
                    reason="receive_and_processing_reversed",
                ),
                State(
                    c,
                    "2000.80",
                    c + transport,
                    c + transport + processing,
                    c + transport + 75,
                    reason="future_source_time",
                ),
                state(end + 450, "2000.22", spec="v2"),
            ),
        )
    else:
        raise ValueError(f"Unknown factorial scenario {name!r}")
    return (Cohort(0, END_NS, series),)
