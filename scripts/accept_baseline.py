"""Rebuild the P1/P2/P2.1 measurements and verify the frozen P4 reference."""

import argparse
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from start_observatory import prepare

from xauusd_quote_lab.observatory import load_dataset
from xauusd_quote_lab.replay import verified_checkout_revision

REFERENCE = {
    "code_sha": "c3879c4b627c19a8869a75d8aeeaeb7c153e0669",
    "files": {
        "p1/evidence.json": "0fd2f1f1a6e41171a4c811e6b37102feffcbcfede45010a4993290be25ae920c",
        "p2/evidence-asynchronous.json": "1c985f1017afdd1f809a5e997bb731e99f30a1d2a274dac7ed8121ad0a4c5139",
        "p2/evidence-clocks-metadata.json": "6d1f5f7a840378d53d70ac89269969bb51842795e182d0a247cde83c3e15eae8",
        "p2/evidence-gaps.json": "aad1db2827cb98ac82e3c23b2091eacd3e863383213773080b8d415c12e85e57",
        "p2/evidence-persistent.json": "874b02dc0c58b05c8e2f4d850c0b21d67144d29b9a94cf12682afb32ad307fdc",
        "p2/evidence-short-spike.json": "10e1c3c01241bc443faace608824da4f29238e166eeca6c8054683d2c0b36602",
        "p2/evidence-stable.json": "868de7d80816e2959f2d34d1d33dacc5a6329b041931fd0f71e1aeff2e462ad6",
        "p2/input-asynchronous.json": "d46d3cb5655e92ccabdc062860649217a9f2ed0ef8a918452214b1a2b610f6b4",
        "p2/input-clocks-metadata.json": "8f79a1540abfe58ac79b0b91f4f5e6755c5d2a2cb8266bf6d915374e408ab658",
        "p2/input-gaps.json": "6a3f8f9dba8be174981b5183ac9495398b927a16b952b59aac65401fe99678e8",
        "p2/input-persistent.json": "889cf41c90baff78f306a7630b34cdf5de1c34eccac3de74133a8d1441a37eed",
        "p2/input-short-spike.json": "cc43d04c2dc888fa885cfc4b8f625ef001636f95b9ec45d6f87fc6de3ff25d38",
        "p2/input-stable.json": "d4d4aa94f5c8c18338f7cf4ede9d1f3be96456e697dcbbaaee093179bd9189e5",
        "p2/results.json": "bdc5083df7a118fce5d48c68def2d30317e7bec17910801a9a0f4e6cd90327d1",
        "p2/sensitivity.json": "e48a6937ee688cdee4fbac2a767cd957d2625513d7f623fafe7a183e378e051a",
        "p21/asof-results.jsonl": "b4cf7e4a3c9b0618288b8279c1db7a91f26692f598a33598cefc67403aa9818e",
        "p21/asof-sensitivity.json": "05baa7cda0c80143a9493fb7bab4c60334bd05f8941e871eea9083a566babf5e",
        "p21/evidence.json": "2030abd7739f8ec02dade96d17c841df61f5b4f83f73ad293a9a40ab3002cca8",
        "p21/heatmap.json": "57663acd302e37b89e423a3d0a93c405d6462900ddfd7445b042596c7cf97fbe",
        "p21/ideal-intersection.json": "7b017a2f42774b5bd9598df80e3703a58a55a26f0268922e6728eb17c0e49298",
        "p21/identifiability.json": "3fcf7b40d6290e60785aa8d880788b759a9d382e74f33941c2992d2901767f84",
        "p21/results.jsonl": "16626a948ce64fc59c42644a38fef0fd4f55463ff088c1b81676fe8f496acd92",
        "p21/sensitivity.json": "e731b3b4f2b8db23614a75d9869462676f15178adccfa2a1d9f6391f0d352332",
        "p21/tail-decomposition.json": "281e572c605d2d22534012eb010b4a487604d1688d0b0bf0ed4e7b2e28829016",
        "p21/truth-inputs.jsonl": "547811e56ed4920e66963675ef3679c1311fdeac5d88709f6af69a21a8f0d924",
    },
}


def measurement_digest(path: Path) -> str:
    data = path.read_bytes()
    if path.name.startswith("evidence"):
        packet = json.loads(data)
        del packet["code_sha"]
        data = json.dumps(packet, sort_keys=True, separators=(",", ":")).encode("ascii")
    return sha256(data).hexdigest()


def verify(root: Path) -> dict:
    revision = verified_checkout_revision(Path.cwd())
    with TemporaryDirectory() as temporary:
        for family in ("p1", "p2", "p21"):
            dataset = load_dataset(family, root / family, Path(temporary) / family, None)
            if dataset.code_sha != revision:
                raise ValueError(f"{family} artifacts do not identify this commit")
    actual = {
        path.relative_to(root).as_posix(): measurement_digest(path)
        for family in ("p1", "p2", "p21")
        for path in (root / family).iterdir()
        if path.name != "manifest.json"
    }
    expected = REFERENCE["files"]
    changed = sorted(
        key for key in actual.keys() | expected.keys() if actual.get(key) != expected.get(key)
    )
    if changed:
        raise ValueError(f"Frozen measurements differ: {', '.join(changed)}")
    return {"baseline": REFERENCE["code_sha"], "candidate": revision, "verified": actual}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.verify_only:
        prepare(args.artifacts)
    print(json.dumps(verify(args.artifacts), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
