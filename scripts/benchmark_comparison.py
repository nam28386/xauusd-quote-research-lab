"""Measure comparison scaling on one and four deterministic synthetic sources."""

import json
import tracemalloc
from dataclasses import replace
from statistics import median
from time import perf_counter

from xauusd_quote_lab.comparison import compare_brokers
from xauusd_quote_lab.replay import golden_streams


def benchmark():
    _, _, base = golden_streams()
    results = []
    for count in (512, 1024, 2048):
        decisions = range(100, 100 + 10 * count, 10)
        for sources in (1, 4):
            streams = tuple(
                replace(
                    stream,
                    observations=tuple(
                        replace(
                            stream.observations[0],
                            poll_sequence=sequence,
                            received_wall_ns=stamp,
                            processing_wall_ns=stamp,
                            source_time_ms_or_null=None,
                        )
                        for sequence, stamp in enumerate(decisions)
                    ),
                )
                for stream in base[:sources]
            )

            def run():
                return compare_brokers(
                    streams,
                    decisions,
                    receive_clock_domain=streams[0].receive_clock_domain,
                    max_age_ns=100,
                )

            timings = []
            for _ in range(3):
                start = perf_counter()
                report = run()
                timings.append(perf_counter() - start)
                assert len(report.points) == count and report.valid_coverage == 1
                del report
            tracemalloc.start()
            run()
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            results.append(
                {
                    "sources": sources,
                    "observations_per_source": count,
                    "decisions": count,
                    "median_seconds": median(timings),
                    "peak_comparison_bytes": peak,
                }
            )
    return results


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2))
