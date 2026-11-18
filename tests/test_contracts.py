from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext

import pytest

from xauusd_quote_lab.contracts import Flag, PriceUnit
from xauusd_quote_lab.quality import inspect_quote


def test_exact_decimal_and_immutable_raw_observation(streams):
    stream = streams[0]
    row = stream.observations[0]
    with localcontext() as context:
        context.prec = 3
        state, prices = inspect_quote(row, stream.specs[0])
        assert state.eligible
        assert prices.spread == Decimal("0.25")
        assert prices.mid == Decimal("2000.225")
    with pytest.raises(FrozenInstanceError):
        row.bid_text = "1"


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"bid_text": "2000.40", "ask_text": "2000.30"}, Flag.CROSSED),
        ({"ask_text": None}, Flag.MISSING_ASK),
        ({"bid_text": None}, Flag.MISSING_BID),
        ({"ask_text": "NaN"}, Flag.INVALID_ASK),
        ({"ask_text": "Infinity"}, Flag.INVALID_ASK),
        ({"bid_text": 2000.1}, Flag.INVALID_BID),
        ({"bid_text": "-5"}, Flag.INVALID_BID),
        ({"ask_text": "2e3"}, Flag.INVALID_ASK),
        ({"instrument_spec_version": "absent"}, Flag.UNKNOWN_SPEC),
        ({"quality_flags": {Flag.SOURCE_DISCONNECT}}, Flag.SOURCE_DISCONNECT),
    ],
)
def test_invalid_quote_has_no_price(streams, changes, expected):
    stream = streams[0]
    quality, prices = inspect_quote(replace(stream.observations[0], **changes), stream.specs[0])
    assert prices is None
    assert expected in quality.exclusions


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"price_unit": PriceUnit.UNKNOWN}, Flag.UNKNOWN_UNIT),
        ({"quote_currency": "EUR"}, Flag.UNKNOWN_UNIT),
        ({"canonical_symbol": "XAGUSD"}, Flag.UNSUPPORTED_INSTRUMENT),
    ],
)
def test_instrument_eligibility(streams, changes, expected):
    stream = streams[0]
    quality, prices = inspect_quote(stream.observations[0], replace(stream.specs[0], **changes))
    assert prices is None
    assert expected in quality.exclusions


def test_session_provenance_and_spec_identity(streams):
    stream = streams[0]
    with pytest.raises(ValueError, match="session"):
        replace(stream, source=replace(stream.source, session_id="other"))
    with pytest.raises(ValueError, match="synthetic"):
        replace(stream, source=replace(stream.source, provenance_class="LIVE"))
    with pytest.raises(ValueError, match="one definition"):
        replace(stream, specs=(stream.specs[0], replace(stream.specs[0], digits=3)))
    with pytest.raises(ValueError, match="Poll sequences"):
        replace(stream, observations=(stream.observations[0], stream.observations[0]))
