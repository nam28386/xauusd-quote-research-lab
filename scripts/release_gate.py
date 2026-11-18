"""Verify the exact source, frozen research and canonical distribution for RC3."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
P1_GOLDEN = "408bfc439bbe9811b623245b44255a9458526b32ac0322f968f876e8c6dd2411"
GOLDENS = {
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
    "p21/heatmap.json": "57663acd302e37b89e423a3d0a93c405d6462900ddfd7445b042596c7cf97fbe",
    "p21/ideal-intersection.json": "7b017a2f42774b5bd9598df80e3703a58a55a26f0268922e6728eb17c0e49298",
    "p21/identifiability.json": "3fcf7b40d6290e60785aa8d880788b759a9d382e74f33941c2992d2901767f84",
    "p21/results.jsonl": "16626a948ce64fc59c42644a38fef0fd4f55463ff088c1b81676fe8f496acd92",
    "p21/sensitivity.json": "e731b3b4f2b8db23614a75d9869462676f15178adccfa2a1d9f6391f0d352332",
    "p21/tail-decomposition.json": "281e572c605d2d22534012eb010b4a487604d1688d0b0bf0ed4e7b2e28829016",
    "p21/truth-inputs.jsonl": "547811e56ed4920e66963675ef3679c1311fdeac5d88709f6af69a21a8f0d924",
}


def gate(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def verify_source(sha: str) -> None:
    gate(git("rev-parse", "HEAD") == sha, "Release checkout does not match the expected SHA")
    gate(not git("status", "--porcelain", "--untracked-files=all"), "Release checkout is dirty")
    print(f"Verified clean source {sha}")


def verify_goldens(root: Path, sha: str) -> None:
    def decode(name: str):
        return json.loads((root / name).read_bytes())

    p1 = decode("p1/evidence.json")
    gate(p1.pop("code_sha", None) == sha, "P1 evidence has the wrong commit")
    wire = json.dumps(p1, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    gate(
        hashlib.sha256((wire + "\n").encode("ascii")).hexdigest() == P1_GOLDEN, "P1 golden changed"
    )
    for family in ("p2", "p21"):
        gate(
            decode(f"{family}/manifest.json").get("code_sha") == sha,
            f"{family} manifest has the wrong commit",
        )
    for name, expected in GOLDENS.items():
        with (root / name).open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        gate(actual == expected, f"Frozen research output changed: {name}")
    print(f"Verified P1 evidence and {len(GOLDENS)} frozen P2/P2.1 files")


def verify_bundle(root: Path, sha: str) -> None:
    from xauusd_quote_lab.workstation_release import MANIFEST_NAME, VERSION, verify_archive

    archive = f"xauusd-quote-lab-{VERSION}.zip"
    files = {archive, MANIFEST_NAME, "SHA256SUMS"}
    gate({p.name for p in root.iterdir()} == files, "Unexpected distribution asset inventory")
    for name in files:
        item = root / name
        gate(item.is_file() and not item.is_symlink(), f"Unsafe distribution asset: {name}")
    sums = root / "SHA256SUMS"
    sidecar = root / MANIFEST_NAME
    gate(sums.stat().st_size <= 512 and sidecar.stat().st_size <= 512 * 1024, "Oversized sidecar")
    records = sums.read_bytes().decode("ascii").splitlines()
    expected = {line.split("  ", 1)[1]: line.split("  ", 1)[0] for line in records if "  " in line}
    gate(
        len(records) == 2 and expected.keys() == {archive, MANIFEST_NAME},
        "Invalid checksum inventory",
    )
    manifest = verify_archive(root / archive, expected[archive])
    gate(manifest["code_sha"] == sha, "Distribution code SHA differs from verified checkout")
    gate(manifest["release_version"] == VERSION, "Unexpected candidate version")
    gate(set(manifest.get("datasets", {})) == {"p1", "p2", "p21"}, "Missing synthetic datasets")
    payload = sidecar.read_bytes()
    gate(
        hashlib.sha256(payload).hexdigest() == expected[MANIFEST_NAME], "Manifest checksum mismatch"
    )
    with ZipFile(root / archive) as bundle:
        gate(payload == bundle.read(MANIFEST_NAME), "External and embedded manifests differ")
    print(f"Verified {archive} SHA-256 {expected[archive]} | {len(manifest['files'])} members")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("source", "goldens", "bundle"))
    parser.add_argument("--sha", required=True)
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    sys.path.append(str(ROOT / "src"))
    try:
        if args.kind == "source":
            verify_source(args.sha)
        elif args.directory is None:
            parser.error("--directory is required for this gate")
        elif args.kind == "goldens":
            verify_goldens(args.directory, args.sha)
        else:
            verify_bundle(args.directory, args.sha)
    except (ValueError, OSError, BadZipFile, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Release gate: {exc}") from None


if __name__ == "__main__":
    main()
