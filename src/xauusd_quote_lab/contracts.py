"""Version-one immutable contracts for synthetic quote observations."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar


class Environment(StrEnum):
    MOCK = "MOCK"
    REAL = "REAL"
    DEMO = "DEMO"
    UNKNOWN = "UNKNOWN"


class PriceUnit(StrEnum):
    USD_PER_TROY_OUNCE = "USD_PER_TROY_OUNCE"
    UNKNOWN = "UNKNOWN"


class Flag(StrEnum):
    MISSING_BID = "missing_bid"
    MISSING_ASK = "missing_ask"
    INVALID_BID = "invalid_bid"
    INVALID_ASK = "invalid_ask"
    CROSSED = "crossed"
    DUPLICATE_SNAPSHOT = "duplicate_snapshot"
    STALE = "stale"
    FUTURE_TIMESTAMP = "future_timestamp"
    SOURCE_OUT_OF_ORDER = "source_out_of_order"
    WALL_CLOCK_REVERSAL = "wall_clock_reversal"
    INVALID_TIMESTAMP = "invalid_timestamp"
    UNSUPPORTED_INSTRUMENT = "unsupported_instrument"
    UNKNOWN_UNIT = "unknown_unit"
    SOURCE_DISCONNECT = "source_disconnect"
    PARTIAL_COVERAGE = "partial_source_coverage"
    UNKNOWN_SPEC = "unknown_spec_version"
    PROCESSING_PENDING = "processing_pending"
    NO_OBSERVATION = "no_observation"
    CLOCK_INCOMPATIBLE = "clock_incompatible"
    AMBIGUOUS_BROKER = "ambiguous_broker"
    NON_REPRESENTATIVE = "non_representative"


@dataclass(frozen=True, slots=True)
class BrokerSource:
    VERSION: ClassVar[str] = "broker-source-v1"
    source_id: str
    broker_alias: str
    server_alias: str
    environment: Environment
    account_type_user_label: str | None
    ingestion_mode: str
    provenance_class: str
    source_identity_verification_state: str
    session_id: str


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    VERSION: ClassVar[str] = "instrument-spec-v1"
    raw_symbol: str
    spec_version: str
    spec_source: str
    canonical_symbol: str = "XAUUSD"
    price_unit: PriceUnit = PriceUnit.UNKNOWN
    quote_currency: str | None = None
    point_size: Decimal | None = None
    tick_size: Decimal | None = None
    digits: int | None = None
    contract_size: Decimal | None = None
    user_unit_asserted: bool = False


@dataclass(frozen=True, slots=True)
class QuoteObservation:
    VERSION: ClassVar[str] = "quote-observation-v1"
    bid_text: str | None
    ask_text: str | None
    source_time_ms_or_null: int | None
    received_wall_ns: int
    processing_wall_ns: int
    poll_sequence: int
    source_id: str
    session_id: str
    instrument_spec_version: str
    received_monotonic_ns: int | None = None
    quality_flags: frozenset[Flag] = frozenset()
    ingestion_mode: str = "SYNTHETIC"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "quality_flags", frozenset(Flag(flag) for flag in self.quality_flags)
        )
        if type(self.received_wall_ns) is not int:
            raise ValueError("Receive time must be an integer nanosecond timestamp")


@dataclass(frozen=True, slots=True)
class QuoteStream:
    source: BrokerSource
    specs: tuple[InstrumentSpec, ...]
    observations: tuple[QuoteObservation, ...]
    receive_clock_domain: str | None = None
    source_clock_comparable: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "specs", tuple(self.specs))
        object.__setattr__(self, "observations", tuple(self.observations))
        if (self.source.ingestion_mode, self.source.provenance_class) != ("SYNTHETIC", "SYNTHETIC"):
            raise ValueError("Only synthetic streams are supported")
        if not all(
            text and text == text.strip()
            for text in (self.source.source_id, self.source.session_id, self.source.broker_alias)
        ):
            raise ValueError("Source, session and broker aliases must be nonempty and trimmed")
        if len({spec.spec_version for spec in self.specs}) != len(self.specs):
            raise ValueError("Each instrument spec version must have one definition")
        last_sequence = -1
        for row in self.observations:
            if (row.source_id, row.session_id) != (self.source.source_id, self.source.session_id):
                raise ValueError("Observation source or session mismatch")
            if row.ingestion_mode != self.source.ingestion_mode:
                raise ValueError("Observation ingestion mode mismatch")
            if type(row.poll_sequence) is not int or row.poll_sequence <= last_sequence:
                raise ValueError("Poll sequences must strictly increase within a stream")
            last_sequence = row.poll_sequence
