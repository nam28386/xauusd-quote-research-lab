# XAUUSD Quote Research Lab

This private research repository uses Python 3.12 to measure synthetic XAUUSD bid and ask observations. Cloud inputs, fixtures and examples are synthetic.

Run from the repository root with Python 3.12 and uv.

```sh
python scripts/preflight.py
uv sync --frozen --extra dev
uv run --frozen --extra dev ruff check .
uv run --frozen --extra dev ruff format --check .
uv run --frozen --extra dev pytest -q
uv build
uv run --frozen --extra dev python -m xauusd_quote_lab.synthetic
uv run --frozen --extra dev python -m xauusd_quote_lab.replay
uv run --frozen --extra dev python scripts/audit_public_files.py
```

The evidence replay requires a checkout with committed source and fixture bytes.
It prints deterministic JSON with the fixture SHA-256 and current Git commit.
The fixture-only smoke command works during edits.

Read [project rules](AGENTS.md), the [canonical specification](docs/CODEX_NEW_CHAT_MASTER.md), and the [versioned measurement rules](docs/RESEARCH_METHODS.md).

The [P2 sampling experiment](docs/P2_SAMPLING.md) defines the synthetic
truth oracle, frozen schedule grid, metric conventions, and reproduction commands.

The [P2.1 factorial study](docs/P21_FACTORIAL.md) adds matched-weight tail
estimands, finite-phase checks and constructive identifiability examples.

The [P3 read-only observatory](docs/P3_OBSERVATORY.md) provides six local
research views. The guide covers startup, runner artifacts, API filters,
integrity checks and filtered exports.
