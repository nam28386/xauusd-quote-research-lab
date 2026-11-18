# P2.1 factorial measurement and identifiability

## Frozen design

The verified parent is `ee3853ab2089e90dbf514fb0ccde20499b789e9d`. Its 384-row
result SHA-256 is `bdc5083df7a118fce5d48c68def2d30317e7bec17910801a9a0f4e6cd90327d1`.
P1 and P2 modules, fixtures, and metric versions remain usable as published.

The primary design crosses width 25/50/100/250/500/1000 ms, poll interval
100/250/500/1000 ms, transport 0/25/100/250 ms, processing 0/25/100 ms and phase
0/25/50/75%. Each of six scenario replications uses all 1,152 cells. Broker
comparisons evaluate every 50 ms at a fixed 250 ms age tolerance. Separate
as-of sensitivity uses the asynchronous scenario, widths 25/250/1000 ms,
transport 100 ms and processing 25 ms with all intervals, phases, and
100/250/500/1000 ms tolerances. This adds 192 comparison rows.

All scenarios share the half-open 0–2,200 ms evaluation window, 0.50 USD/troy
oz widening threshold, P2 fixed broker phase stagger and P1 clocks. The initial
quote at t=0 is already available. Noninitial revisions acquire the predeclared
transport and processing delay. Some asynchronous sources have additional
fixed transport skew. Synthetic clock anomalies and session closure have
explicit clock definitions. Poll projection sees only raw arrivals. The
offline oracle sees immutable event histories and independent validity labels.
There is no random seed, tuning split, favorable offset selection, live feed,
or execution model.

- Isolated starts at 125 ms. It provides the ideal zero-delay and zero-jitter subset.
- Clustered adds a second equal-width episode after a 50 ms quiet interval.
- Asynchronous uses four brokers with staggered events, clocks and schedules.
- Gaps interrupts the nominal widening at half its width and inserts a crossed quote.
- Session/spec switches source session at 800 ms, with no carry-in to the new
  session, then changes instrument spec at 1,040 ms. Per-session source
  duration coverage keeps the P2 global-window denominator. Broker time uses
  disjoint session decision windows.
- Clocks injects receive and processing reversals, a future source timestamp,
  and subsequent recovery under a new spec.

## Estimands

For each of p95/p99, let O be the oracle duration tail, D the sampled duration
tail, and S the sampled snapshot tail. The new P2.1 family reports D−O
(duration-to-duration), S−D (weighting), and S−O (original cross-estimand),
with exact additive identity where supported. D−O controls the weighting
convention and still reflects availability, exclusions and coverage. S−O
combines both components. Nearest-rank and no-support conventions come
from P2. P2 event matching and eligible revision accounting remain in use.

The no-delay ideal subset uses the same four frozen phases. Half-open
intersection uses the exact count of phases with a poll in [onset, end).
A continuous-uniform phase has probability min(1,d/T), recorded separately.
The outputs distinguish intersection, eligible widened polls, observed
episodes, matched truth, and left/right censoring. Detection and error ranges
are conditional on the enumerated scenarios and have no confidence level.

Two pairs of histories follow identical recorded arrival clocks and sequences
but differ in unobserved widening between polls. Their full PollSample objects
are equal including recorded origin metadata. Oracle event counts and at least
one tail differ. Real-market missed ticks are unidentified from this example,
and synthetic results provide no evidence about dealer identity, broker
independence, executable arbitrage, realized costs or market liquidity.

## Reproduction

Run from the committed checkout after syncing the frozen environment.

```sh
uv sync --frozen --extra dev
uv run --frozen --extra dev python -m xauusd_quote_lab.factorial_experiment --output dist/p21-experiment
```

The new output directory holds the manifest, 6,912 primary rows, all unique
truth inputs, 192 as-of rows, ideal phase checks, heatmap data and scenario
summaries. The tail summary uses common support, reports exact component
sums and rounds means to 128 significant digits. The SHA-256 index binds
each artifact to the bounded evidence packet. The runner writes JSONL in
bounded chunks and enforces a 96 MiB total output limit. A failed run has
no manifest. The manifest records the Python runtime and dependency lock.
