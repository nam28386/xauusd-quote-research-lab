import json
from dataclasses import replace
from decimal import Decimal

import pytest

from xauusd_quote_lab.evidence import Claim, EpistemicStatus
from xauusd_quote_lab.replay import replay
from xauusd_quote_lab.synthetic import FIXTURE_SHA256

SHA = "a" * 40


def test_deterministic_evidence_golden_replay():
    packet = replay(SHA)
    assert replay(SHA).to_json() == packet.to_json()
    payload = json.loads(packet.to_json())
    assert payload["version"] == "research-evidence-packet-v1"
    assert payload["inputs"][0]["sha256"] == FIXTURE_SHA256
    assert payload["inputs"][0]["source_ids"] == ["alpha", "beta", "gamma", "delta"]
    assert payload["inputs"][0]["session_ids"] == ["golden-session-v1"]
    assert payload["code_sha"] == SHA
    assert payload["created_wall_ns"] == "150"
    assert payload["eligible_source_count"] == 4
    assert dict(payload["exclusion_counts"]) == {
        "comparison.missing_ask": 1,
        "comparison.no_observation": 1,
        "dynamics.duplicate_snapshot": 1,
        "dynamics.missing_ask": 1,
    }
    assert payload["findings"][1]["value"] == "0.45"
    assert payload["findings"][1]["status"] == "MEASUREMENT"
    assert payload["findings"][3]["status"] == "UNKNOWN"


def test_decimal_and_large_timestamp_strings():
    packet = replace(
        replay(SHA),
        created_wall_ns=1_700_000_000_000_000_001,
        findings=(Claim(EpistemicStatus.MEASUREMENT, "exact", Decimal("0.0100")),),
    )
    payload = json.loads(packet.to_json())
    assert payload["created_wall_ns"] == "1700000000000000001"
    assert payload["findings"][0]["value"] == "0.0100"


def test_evidence_rejects_invalid_provenance_and_epistemic_value():
    with pytest.raises(ValueError, match="provenance"):
        replay("unverified")
    with pytest.raises(ValueError, match="Unknown"):
        Claim(EpistemicStatus.UNKNOWN, "not observed", Decimal(0))
    with pytest.raises(ValueError, match="finite"):
        Claim(EpistemicStatus.MEASUREMENT, "undefined", Decimal("NaN"))
