"""P2.1 additive tail estimands under the frozen P2 quantile convention."""

from decimal import Decimal, localcontext

from .quality import PRICE_CONTEXT

TAIL_VERSION = "p21-tail-decomposition-v1"


def decompose_tail(
    oracle_duration: Decimal | None,
    sampled_duration: Decimal | None,
    sampled_snapshot: Decimal | None,
) -> dict[str, Decimal | str | None]:
    with localcontext(PRICE_CONTEXT):
        duration = (
            sampled_duration - oracle_duration
            if sampled_duration is not None and oracle_duration is not None
            else None
        )
        weighting = (
            sampled_snapshot - sampled_duration
            if sampled_snapshot is not None and sampled_duration is not None
            else None
        )
        cross = (
            sampled_snapshot - oracle_duration
            if sampled_snapshot is not None and oracle_duration is not None
            else None
        )
        if duration is not None and weighting is not None and cross != duration + weighting:
            raise ArithmeticError("The tail decomposition must close exactly")
    return {
        "oracle_duration": oracle_duration,
        "sampled_duration": sampled_duration,
        "sampled_snapshot": sampled_snapshot,
        "duration_to_duration": duration,
        "snapshot_vs_duration_weighting": weighting,
        "original_cross_estimand": cross,
        "duration_unavailable": "missing_duration_support" if duration is None else None,
        "weighting_unavailable": "missing_sampled_support" if weighting is None else None,
        "cross_unavailable": "missing_snapshot_or_oracle_support" if cross is None else None,
    }
