"""Read the allowlisted, hash-pinned synthetic golden fixture."""

import hashlib
import json
from pathlib import Path

FIXTURE_PATH = Path("fixtures/synthetic/golden-v1.json")
FIXTURE_SHA256 = "6a50516270328b855a3007b350001fc675bc7ce62ffef3f382dee5d7ad57fb9f"


def load_fixture(root: Path = Path(".")) -> tuple[dict, str]:
    payload = (root / FIXTURE_PATH).read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != FIXTURE_SHA256:
        raise ValueError("Synthetic fixture bytes do not match the reviewed fixture")
    data = json.loads(payload)
    if data["provenance"] != "SYNTHETIC":
        raise ValueError("Synthetic provenance is required")
    return data, digest


def main() -> None:
    fixture, digest = load_fixture()
    print(f"{fixture['fixture_id']} {digest} ({len(fixture['streams'])} synthetic streams)")


if __name__ == "__main__":
    main()
