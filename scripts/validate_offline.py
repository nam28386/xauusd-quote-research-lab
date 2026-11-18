"""Invoke the offline validation boundary without installing the package."""

import sys
from pathlib import Path


def main() -> None:
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Python 3.12 is required")
    sys.dont_write_bytecode = True
    sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))
    from xauusd_quote_lab.offline_import import main as validate

    validate()


if __name__ == "__main__":
    main()
