"""Offline replay of the reviewed synthetic fixture with code provenance."""

import argparse
import re
import subprocess
from decimal import Decimal
from pathlib import Path

from .comparison import BrokerComparison, compare_brokers
from .contracts import (
    BrokerSource,
    Environment,
    InstrumentSpec,
    PriceUnit,
    QuoteObservation,
    QuoteStream,
)
from .dynamics import QuoteDynamics, measure_dynamics
from .evidence import Claim, EpistemicStatus, InputProvenance, ResearchEvidencePacket
from .quality import QualityState
from .synthetic import FIXTURE_PATH, load_fixture

CLOCK = "golden-v1/shared-synthetic-wall"


def golden_streams(root: Path = Path(".")) -> tuple[str, str, tuple[QuoteStream, ...]]:
    data, digest = load_fixture(root)
    spec = InstrumentSpec(
        "XAUUSD",
        "fixture-spec-v1",
        "synthetic fixture",
        price_unit=PriceUnit.USD_PER_TROY_OUNCE,
        quote_currency="USD",
        user_unit_asserted=True,
    )
    streams = []
    for item in data["streams"]:
        alias = item["alias"]
        source = BrokerSource(
            source_id=alias,
            broker_alias=alias,
            server_alias=f"synthetic-{alias}",
            environment=Environment(item["environment"]),
            account_type_user_label=None,
            ingestion_mode="SYNTHETIC",
            provenance_class="SYNTHETIC",
            source_identity_verification_state="synthetic declaration",
            session_id="golden-session-v1",
        )
        observations = tuple(
            QuoteObservation(
                bid, ask, None, int(ns), int(ns), index, alias, source.session_id, spec.spec_version
            )
            for index, (ns, bid, ask) in enumerate(item["rows"])
        )
        streams.append(QuoteStream(source, (spec,), observations, CLOCK))
    return data["fixture_id"], digest, tuple(streams)


def replay(code_sha: str) -> ResearchEvidencePacket:
    fixture_id, digest, streams = golden_streams()
    dynamics = measure_dynamics(
        streams[0],
        start_ns=100,
        end_ns=150,
        max_age_ns=20,
        widening_threshold=Decimal("0.50"),
    )
    comparison = compare_brokers(
        streams, (124, 125, 130), receive_clock_domain=CLOCK, max_age_ns=20
    )
    point = comparison.points[1]
    exclusions = tuple(
        (f"{metric}.{flag.value}", count)
        for metric, counts in (
            ("comparison", comparison.exclusion_counts),
            ("dynamics", dynamics.exclusions),
        )
        for flag, count in counts
    )
    return ResearchEvidencePacket(
        research_id="golden-replay-v1",
        hypothesis_id=None,
        created_wall_ns=150,
        inputs=(
            InputProvenance(
                fixture_id,
                digest,
                ("golden-session-v1",),
                tuple(stream.source.source_id for stream in streams),
            ),
        ),
        code_sha=code_sha,
        schema_versions=(
            BrokerSource.VERSION,
            InstrumentSpec.VERSION,
            QuoteObservation.VERSION,
            QualityState.VERSION,
        ),
        metric_versions=(QuoteDynamics.VERSION, BrokerComparison.VERSION),
        question="What quoted spread and mid measurements are observable in the golden replay?",
        clock_assumptions=(CLOCK, "Synthetic shared wall clock; processing equals receive."),
        parameters=(
            ("max_age_ns", "20"),
            ("window_ns", "100..150"),
            ("decision_wall_ns", "124,125,130"),
            ("widening_threshold", "0.50"),
        ),
        eligible_source_count=point.eligible_broker_count,
        exclusion_counts=exclusions,
        findings=(
            Claim(EpistemicStatus.FACT, "The fixture is synthetic and hash pinned."),
            Claim(
                EpistemicStatus.MEASUREMENT,
                "Consensus spread at synthetic decision 125 ns.",
                point.median_spread,
                "USD/troy oz",
            ),
            Claim(
                EpistemicStatus.MEASUREMENT,
                "Alpha duration-weighted spread.",
                dynamics.duration_weighted_spread,
                "USD/troy oz",
            ),
            Claim(EpistemicStatus.UNKNOWN, "Real-world missed quote revisions."),
        ),
        candidate_explanations=(),
        falsifiers=("Recompute the Decimal measurements from the pinned rows and decision times.",),
        limitations=comparison.limitations
        + ("Fixture times are synthetic; created time is simulated.",),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    root = Path.cwd()
    revision = subprocess.check_output(["git", "rev-parse", "--verify", "HEAD"], text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise SystemExit("A full Git commit SHA is required")
    # Prevent a clean commit SHA from being attributed to modified implementation or inputs.
    paths = ["src", "pyproject.toml", "uv.lock", str(FIXTURE_PATH)]
    diff = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *paths], cwd=root)
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "--", *paths], cwd=root
    )
    if diff.returncode or untracked:
        raise SystemExit("Commit replay code and inputs before producing evidence")
    print(replay(revision).to_json())


if __name__ == "__main__":
    main()
