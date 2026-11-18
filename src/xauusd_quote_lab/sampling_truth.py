"""Frozen, deterministic fixtures with separate arrival and oracle projections."""

from dataclasses import dataclass
from decimal import Decimal

from .contracts import (
    BrokerSource,
    Environment,
    Flag,
    InstrumentSpec,
    PriceUnit,
    QuoteObservation,
    QuoteStream,
)
from .sampling import MS

CLOCK = "p2-v1/shared-synthetic-wall"
END_NS = 2200 * MS
THRESHOLD = Decimal("0.50")
TRUTH_VERSION = "p2-synthetic-history-v1"

SPECS = (
    InstrumentSpec(
        "XAUUSD",
        "v1",
        "synthetic declaration",
        price_unit=PriceUnit.USD_PER_TROY_OUNCE,
        quote_currency="USD",
        user_unit_asserted=True,
    ),
    InstrumentSpec(
        "XAUUSD",
        "v2",
        "synthetic metadata transition",
        price_unit=PriceUnit.USD_PER_TROY_OUNCE,
        quote_currency="USD",
        tick_size=Decimal("0.01"),
        user_unit_asserted=True,
    ),
    InstrumentSpec("XAUUSD", "units-unknown", "synthetic unknown units"),
)


@dataclass(frozen=True, slots=True)
class TruthEvent:
    event_ns: int
    arrival: QuoteObservation
    truth_exclusion: str | None = None


@dataclass(frozen=True, slots=True)
class EventHistory:
    source: BrokerSource
    events: tuple[TruthEvent, ...]

    def arrivals(self) -> QuoteStream:
        return QuoteStream(
            self.source, SPECS, tuple(event.arrival for event in self.events), CLOCK, True
        )


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    histories: tuple[EventHistory, ...]


@dataclass(frozen=True, slots=True)
class State:
    ms: int
    ask: str | None
    receive_ms: int | None = None
    process_ms: int | None = None
    source_ms: int | None = None
    spec: str = "v1"
    reason: str | None = None
    flags: frozenset[Flag] = frozenset()


def history(name: str, alias: str, *states: State) -> EventHistory:
    source = BrokerSource(
        alias,
        alias,
        "synthetic",
        Environment.MOCK,
        None,
        "SYNTHETIC",
        "SYNTHETIC",
        "fixture-declared",
        f"{name}-{alias}-session",
    )
    events = []
    last_event_ms = -1
    for seq, state in enumerate(states):
        receive = state.receive_ms if state.receive_ms is not None else state.ms
        process = state.process_ms if state.process_ms is not None else receive
        if not last_event_ms < state.ms < END_NS // MS or not 0 <= state.ms <= min(
            receive, process
        ):
            raise ValueError("Synthetic event times must increase and precede local clocks")
        last_event_ms = state.ms
        events.append(
            TruthEvent(
                state.ms * MS,
                QuoteObservation(
                    "2000.00",
                    state.ask,
                    state.source_ms,
                    receive * MS,
                    process * MS,
                    seq,
                    source.source_id,
                    source.session_id,
                    state.spec,
                    quality_flags=state.flags,
                ),
                state.reason,
            )
        )
    return EventHistory(source, tuple(events))


def scenarios() -> tuple[Scenario, ...]:
    return (
        Scenario("stable", (history("stable", "alpha", State(0, "2000.20")),)),
        Scenario(
            "short-spike",
            (
                history(
                    "short-spike",
                    "alpha",
                    State(0, "2000.20"),
                    State(120, "2000.90"),
                    State(180, "2000.20"),
                ),
            ),
        ),
        Scenario(
            "persistent",
            (
                history(
                    "persistent",
                    "alpha",
                    State(0, "2000.20"),
                    State(350, "2000.55"),
                    State(610, "2001.05"),
                    State(1300, "2000.22"),
                    State(2000, "2000.75"),
                ),
            ),
        ),
        Scenario(
            "gaps",
            (
                history(
                    "gaps",
                    "alpha",
                    State(0, "2000.80"),
                    State(300, "2000.20"),
                    State(510, "2000.95"),
                    State(
                        700, None, reason="disconnected", flags=frozenset({Flag.SOURCE_DISCONNECT})
                    ),
                    State(1050, None, reason="missing_ask"),
                    State(1280, "1999.90", reason="crossed"),
                    State(1600, "2000.25"),
                    State(1780, "2000.65"),
                    State(2050, "2000.30"),
                ),
            ),
        ),
        Scenario(
            "asynchronous",
            (
                history(
                    "async",
                    "alpha",
                    State(0, "2000.20"),
                    State(240, "2000.85", 270, 282),
                    State(320, "2000.20", 345, 355),
                    State(800, "2000.62"),
                    State(1210, "2000.33"),
                ),
                history(
                    "async",
                    "beta",
                    State(15, "2000.32"),
                    State(500, "2000.72", 525, 555),
                    State(775, "2000.25"),
                    State(1170, None, reason="missing_ask"),
                    State(1610, "2000.27"),
                ),
                history(
                    "async",
                    "gamma",
                    State(65, "2000.22"),
                    State(300, "2000.60", 307, 322),
                    State(580, "2000.18"),
                    State(950, "2000.80"),
                    State(1250, "2000.30"),
                ),
                history(
                    "async",
                    "delta",
                    State(100, "2000.40"),
                    State(605, "2000.83"),
                    State(710, "2000.20"),
                    State(1530, "2000.95"),
                    State(2010, "2000.20"),
                ),
            ),
        ),
        Scenario(
            "clocks-metadata",
            (
                history(
                    "clocks",
                    "alpha",
                    State(0, "2000.22", source_ms=0),
                    State(200, "2000.70", 450, 475, 200),
                    State(410, "2000.75", 420, 490, 410, reason="wall_clock_reversal"),
                    State(550, "2000.55", spec="units-unknown", reason="unknown_unit"),
                    State(700, "2000.35", source_ms=850, reason="future_source_time"),
                    State(780, "2000.80", spec="v2", source_ms=780),
                    State(960, "2000.85", spec="v2", source_ms=960),
                    State(1100, "2000.20", spec="v2", source_ms=1100),
                ),
            ),
        ),
    )
