"""Check the research runtime and repository layout."""

import sys
from pathlib import Path

if sys.version_info[:2] != (3, 12):
    raise SystemExit("Python 3.12 is required")
if not Path("pyproject.toml").is_file():
    raise SystemExit("Run preflight from the repository root")
print(f"Python {sys.version.split()[0]} | synthetic-only research")
