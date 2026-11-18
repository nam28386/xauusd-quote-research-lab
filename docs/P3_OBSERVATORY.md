# P3 synthetic research observatory

P3 inspects the frozen P1/P2/P2.1 outputs. React and TypeScript render locally
bundled Plotly charts. A standard-library Python service uses one IPv4 loopback
origin for the static build and the versioned read API. Dependencies are
locked with uv and npm. The server exposes no upload or write endpoints.

## Reproduce and launch

With Python 3.12, uv and Node 24, run from the clean committed checkout root.
The same commands work in Bash and PowerShell.

```sh
uv sync --frozen --extra dev
npm --prefix web ci
npm --prefix web run build
uv run --frozen --extra dev python scripts/start_observatory.py --artifacts dist/observatory-inputs --prepare-only
uv run --frozen --extra dev python scripts/start_observatory.py --artifacts dist/observatory-inputs
```

Open `http://127.0.0.1:8765/` locally. Generation requires a new destination.
For existing outputs put the P1 replay stdout in `p1/evidence.json`, the P2
output directory at `p2/`, and the P2.1 directory at `p21/` under the chosen
artifact root. The module CLI also accepts each directory individually.
Use `--p1-sha256`, `--p2-sha256`, and `--p21-sha256` with independently
obtained digests to pin the P1 packet or the P2/P2.1 manifests. Startup without
a pin checks manifest consistency. The declared code SHA is provenance
metadata. Trusted digest acquisition and signature verification are independent
of the application.

## API p3-read-v1

Routes return JSON. UTC-independent durations and wall timestamps use integer
nanosecond strings on the inherited wire. Decimal values use strings and
unavailable estimates use null with upstream reason codes where published.

| Method and path | Content |
|---|---|
| GET /api/v1/datasets | Source experiments, hashes, declared versions, verification level, and artifact classifications |
| GET /api/v1/provenance/{p1,p2,p21} | Dataset metadata and parsed manifest where upstream publishes one |
| GET /api/v1/evidence/{p1,p2,p21} | Original research evidence records with packet hashes |
| GET /api/v1/artifact/{family}/{name} | Exact approved manifest or evidence bytes as a download |
| GET /api/v1/table/{table} | Filtered, deterministic records in artifact order |
| GET /api/v1/row/{table}/{ordinal} | Exact zero-based row and source artifact hash |
| GET /api/v1/export/{table} | Deterministic JSON page including original filter values, hashes and optional presentation selection |

Tables are `p2`, `p2-sensitivity`, `p2-phase`, `p21`, `p21-asof`,
`asof-sensitivity`, `heatmap`, `ideal`, `tail`, `p21-sensitivity`,
`transport-processing`, `identifiability` and `truth`.
Use only supported keys for a table, such as `scenario`, `interval_ms`,
`phase_percent`, `duration_ms`, `transport_ms`, `processing_ms`,
`tolerance_ms`, `tail` or `input_sha256`. Pagination accepts a filtered
`offset` and a `limit` of 1–100 with default 24. A page export includes the
canonical filters and can record `view_metric` and `view_session` in the
`p3-display-v1` envelope. Plotly receives numeric coordinates for drawing.
Tabular values, tooltip text, and exports retain the exact upstream strings.

## Integrity and limits

Startup validates experiment and metric versions, scans JSONL rows and checks
cross-references from results to frozen truth and from evidence to artifacts.
The loader copies verified bytes into a private temporary snapshot, keeps
bounded byte offsets and filter keys for JSONL, and reads only requested rows
from that snapshot. P2 uses a bounded whole-file JSON decode. Original files
stay available at their original paths. Budgets are 96 MiB per dataset,
8 MiB for JSON, 256 KiB per JSONL row, 20,000 indexed rows and 64 KiB per
evidence packet.

The server binds to 127.0.0.1, rejects unexpected Host and Origin headers,
blocks cross-origin embedding, requires recognized routes and serves only
allowlisted static assets or artifact downloads. This is a local research
interface for trusted users on their own machine. The application does not
authenticate other software or accounts on that machine.

The factorial heatmap places one published row in each cell for a fixed
scenario, transport delay, processing delay, phase and source session. It
refuses overlapping cells. The tail explorer renders the three upstream
contrasts on their own support. The separate as-of curve uses the frozen
asynchronous sweep. A missing value is a gap on a plot and has an explicit
state in the table. The Atlas shows complete synthetic truth and sampled
quote tables, with hashes. A plot cannot establish real tick completeness,
economic broker independence, executable arbitrage, realized trading costs
or institutional actor identity. Deterministic configurations are not
independent observations of a market.

## QA

```sh
uv run --frozen --extra dev pytest -q
uv run --frozen --extra dev python scripts/audit_public_files.py
npm --prefix web test
npm --prefix web audit
npm --prefix web exec -- playwright install chromium
npm --prefix web run test:e2e
```

Playwright uses the generated `dist/observatory-inputs` by default. Set
`P3_ARTIFACT_ROOT` to test another existing verified artifact root and
`P3_CHROMIUM` to use an installed Chromium executable. The hosted matrix
builds and tests on Ubuntu and Windows. Local MT5 remains unverified.
