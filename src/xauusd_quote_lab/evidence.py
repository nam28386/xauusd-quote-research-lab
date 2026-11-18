"""Deterministic versioned evidence packets for synthetic research."""

import json
import re
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar

SHA256 = re.compile(r"[0-9a-f]{64}")
GIT_SHA = re.compile(r"[0-9a-f]{40}")


class EpistemicStatus(StrEnum):
    FACT = "FACT"
    MEASUREMENT = "MEASUREMENT"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class InputProvenance:
    fixture_id: str
    sha256: str
    session_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    provenance_class: str = "SYNTHETIC"

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_ids", tuple(self.session_ids))
        object.__setattr__(self, "source_ids", tuple(self.source_ids))
        if (
            self.provenance_class != "SYNTHETIC"
            or not SHA256.fullmatch(self.sha256)
            or not self.fixture_id
            or not self.session_ids
            or not self.source_ids
        ):
            raise ValueError(
                "Evidence requires synthetic fixture identity, hash, sessions and sources"
            )


@dataclass(frozen=True, slots=True)
class Claim:
    status: EpistemicStatus
    statement: str
    value: Decimal | int | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", EpistemicStatus(self.status))
        if self.value is not None and not (
            type(self.value) is int or isinstance(self.value, Decimal) and self.value.is_finite()
        ):
            raise ValueError("Quantitative claims require a finite Decimal or an integer")
        if self.value is not None and self.status in {
            EpistemicStatus.UNKNOWN,
            EpistemicStatus.REJECTED,
        }:
            raise ValueError("Unknown or rejected claims cannot assert a quantitative value")


@dataclass(frozen=True, slots=True)
class ResearchEvidencePacket:
    VERSION: ClassVar[str] = "research-evidence-packet-v1"
    research_id: str
    hypothesis_id: str | None
    created_wall_ns: int
    inputs: tuple[InputProvenance, ...]
    code_sha: str
    schema_versions: tuple[str, ...]
    metric_versions: tuple[str, ...]
    question: str
    clock_assumptions: tuple[str, ...]
    parameters: tuple[tuple[str, str], ...]
    eligible_source_count: int
    exclusion_counts: tuple[tuple[str, int], ...]
    findings: tuple[Claim, ...]
    candidate_explanations: tuple[Claim, ...]
    falsifiers: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "inputs",
            "schema_versions",
            "metric_versions",
            "clock_assumptions",
            "findings",
            "candidate_explanations",
            "falsifiers",
            "limitations",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        for name in ("parameters", "exclusion_counts"):
            items = tuple(sorted((key, value) for key, value in getattr(self, name)))
            if len({key for key, _ in items}) != len(items):
                raise ValueError(f"Duplicate keys in {name}")
            object.__setattr__(self, name, items)
        if (
            type(self.created_wall_ns) is not int
            or self.created_wall_ns < 0
            or not GIT_SHA.fullmatch(self.code_sha)
            or not self.inputs
            or not self.schema_versions
            or not self.metric_versions
            or not self.clock_assumptions
            or type(self.eligible_source_count) is not int
            or not 0 <= self.eligible_source_count <= 4
            or any(type(count) is not int or count < 0 for _, count in self.exclusion_counts)
            or not self.research_id
            or not self.question
            or not self.limitations
        ):
            raise ValueError("Incomplete or invalid evidence provenance")
        if any(not isinstance(value, str) for _, value in self.parameters):
            raise ValueError("Parameter values must be explicit strings")

    def to_json(self) -> str:
        payload = _json_value(self)
        return json.dumps(
            payload, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")
        )


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if type(value) is int:
        # Preserve large integers (including nanosecond values carried as claim values).
        return str(value) if abs(value) > 2**53 - 1 else value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if is_dataclass(value):
        result = {
            field.name: str(getattr(value, field.name))
            if field.name.endswith("_ns")
            else _json_value(getattr(value, field.name))
            for field in fields(value)
        }
        if hasattr(value, "VERSION"):
            result["version"] = value.VERSION
        return result
    return value
