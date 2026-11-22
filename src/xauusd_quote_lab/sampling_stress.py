"""Frozen P8 synthetic stress scenarios and point-in-time sampling results."""

from functools import lru_cache
from hashlib import sha256
from itertools import product

from .contracts import Flag
from .sampling import MS, PHASE_PERCENT, POLL_INTERVALS_MS, poll_stream, poll_times
from .sampling_experiments import json_bytes, wire
from .sampling_metrics import build_oracle, score_sample
from .sampling_truth import END_NS, State, history

VERSION = "p8-sampling-stress-v1"


def scenarios():
    opening = State(0, "2000.20")
    burst = (
        State(230, "2000.90"),
        State(265, "2000.20"),
        State(310, "2001.00"),
        State(365, "2000.20"),
        State(690, "2000.95"),
        State(880, "2000.20"),
    )
    gap = frozenset({Flag.SOURCE_DISCONNECT})
    return (
        history("burst", "alpha", opening, *burst),
        history(
            "jitter",
            "alpha",
            opening,
            State(230, "2000.90", 340, 365, 230),
            State(265, "2000.20", 350, 430, 265),
            State(310, "2001.00", 358, 440, 310),
            State(365, "2000.20", 380, 450, 365),
            State(690, "2000.95", 850, 890, 690),
            State(880, "2000.20", 900, 920, 880),
        ),
        history(
            "clustered-gap",
            "alpha",
            opening,
            *burst[:2],
            State(300, None, reason="disconnect", flags=gap),
            State(450, None, reason="disconnect", flags=gap),
            State(670, "2000.20"),
            *burst[-2:],
        ),
        history(
            "clock-regression",
            "alpha",
            opening,
            State(230, "2000.90", 370, 400, 230),
            State(265, "2000.20", 320, 390, 265),
            State(310, "2001.00", 410, 420, 470),
            State(365, "2000.20", 450, 475, 365),
            *burst[-2:],
        ),
    )


@lru_cache(maxsize=1)
def report_bytes() -> bytes:
    design = scenarios()
    rows = []
    for scenario in design:
        oracle = build_oracle(scenario)
        for interval, phase in product(POLL_INTERVALS_MS, PHASE_PERCENT):
            sample = poll_stream(scenario.arrivals(), poll_times(END_NS, interval, phase, 0))
            score = score_sample(sample, oracle, interval * MS)
            ages = score.pop("origin_age_ns")
            rows.append(
                {
                    "scenario": scenario.source.session_id.removesuffix("-alpha-session"),
                    "interval_ms": interval,
                    "phase_percent": phase,
                    "max_origin_age_ns": str(ages[-1]) if ages else None,
                    **score,
                }
            )
    inputs = wire(design)
    input_sha = sha256(json_bytes(wire(inputs))).hexdigest()
    encoded = json_bytes(wire(rows))
    return json_bytes(
        {
            "classification": "SYNTHETIC",
            "version": VERSION,
            "input_sha256": input_sha,
            "inputs": inputs,
            "rows_sha256": sha256(encoded).hexdigest(),
            "rows": wire(rows),
        }
    )
