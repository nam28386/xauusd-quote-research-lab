from dataclasses import replace

import pytest

from xauusd_quote_lab.replay import golden_streams


@pytest.fixture
def streams():
    return golden_streams()[2]


@pytest.fixture
def one_row(streams):
    def make(times, **overrides):
        stream = streams[0]
        seed = stream.observations[0]
        return replace(
            stream,
            observations=tuple(
                replace(
                    seed, poll_sequence=i, received_wall_ns=t, processing_wall_ns=t, **overrides
                )
                for i, t in enumerate(times)
            ),
        )

    return make
