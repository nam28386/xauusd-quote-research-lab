"""Prepare fresh synthetic artifacts or launch the local read-only P3 observatory."""

import argparse
import subprocess
import sys
from pathlib import Path

from xauusd_quote_lab.observatory import main as serve


def prepare(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    p1 = root / "p1"
    p1.mkdir()
    with (p1 / "evidence.json").open("xb") as evidence:
        subprocess.run(
            [sys.executable, "-m", "xauusd_quote_lab.replay"], stdout=evidence, check=True
        )
    for family, module in (("p2", "sampling_experiments"), ("p21", "factorial_experiment")):
        subprocess.run(
            [sys.executable, "-m", f"xauusd_quote_lab.{module}", "--output", str(root / family)],
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument(
        "--prepare-only", action="store_true", help="Generate all three fresh datasets"
    )
    parser.add_argument("--port", type=int, default=8765)
    for family in ("p1", "p2", "p21"):
        parser.add_argument(f"--{family}-sha256")
    args = parser.parse_args()
    if args.prepare_only:
        prepare(args.artifacts)
        return
    options = ["--port", str(args.port)]
    for family in ("p1", "p2", "p21"):
        options.extend((f"--{family}", str(args.artifacts / family)))
        if pin := getattr(args, f"{family}_sha256"):
            options.extend((f"--{family}-sha256", pin))
    serve(options)


if __name__ == "__main__":
    main()
