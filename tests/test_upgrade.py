import json
from dataclasses import replace
from hashlib import sha256
from random import Random

from xauusd_quote_lab.comparison import match_decisions, match_stream
from xauusd_quote_lab.sampling_experiments import json_bytes
from xauusd_quote_lab.sampling_stress import report_bytes


def test_incremental_matching_matches_reference_and_respects_visible_prefix(streams):
    random = Random(403)
    base = streams[0]
    first = base.observations[0]
    decisions = range(0, 400, 3)
    for _ in range(20):
        rows = tuple(
            replace(
                first,
                poll_sequence=i,
                received_wall_ns=(receive := i * 10 + random.randrange(-10, 10)),
                processing_wall_ns=receive + random.choice([-1, 0, 20, 100]),
                source_time_ms_or_null=random.randrange(3),
                ask_text=random.choice([None, "2000.25", "1999.00"]),
            )
            for i in range(30)
        )
        stream = replace(base, observations=rows)
        clock = stream.receive_clock_domain
        result = list(match_decisions(stream, decisions, clock, 50))
        assert result == [match_stream(stream, t, clock, 50) for t in decisions]
        assert result[:30] == list(match_decisions(stream, decisions[:30], clock, 50))


def test_stress_report_binds_inputs_and_results():
    report = json.loads(report_bytes())
    assert report["classification"] == "SYNTHETIC"
    assert len(report["rows"]) == 64
    for name in ("inputs", "rows"):
        digest_key = "input_sha256" if name == "inputs" else "rows_sha256"
        assert sha256(json_bytes(report[name])).hexdigest() == report[digest_key]
    rows = report["rows"]
    assert {row["scenario"] for row in rows} == {
        "burst",
        "jitter",
        "clustered-gap",
        "clock-regression",
    }
    assert any(row["sampled_exclusion_counts"].get("source_disconnect") for row in rows)
    assert all(row["available_polls"] <= row["total_polls"] for row in rows)
