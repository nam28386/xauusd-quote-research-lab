# P2 synthetic sampling robustness v1

The experiment freezes six synthetic histories, a 2,200 ms half-open window,
a widening threshold of 0.50 USD/troy oz, four sampling intervals and four
P1 broker as-of tolerances (100, 250, 500, 1000 ms for each). Each pair runs
at 0, 25, 50 and 75 percent phase; broker schedules add a fixed stagger of
one quarter interval per source, modulo the interval. Broker evaluation
uses a separate fixed 50 ms clock. These are exhaustive fixture conditions
with no tuning split, random seed or phase selection.

The immutable generation layer has event, source, receive and processing
times. Only the arrival projection enters polling. A P1-visible processed
latest arrival supplies a quote or a blocking tombstone. Poll records use
poll time as synthetic local receipt/processing; where eligible, they
retain the separate origin receipt, processing and sequence. Comparison
age is elapsed time since the polling snapshot. Event age at polling is
reported separately. An explicit invalid or pending latest event blocks an
older valid arrival. Polling itself has no as-of tolerance parameter.

The offline oracle builds exact source-event-time states from the complete
history and the independently declared valid/invalid states. Its durations
end at the next source event or the experiment boundary. The latest poll
contributes zero tail duration under P1. Sampled event, revision and mean
statistics use the P1 dynamics window with the polling period as its
continuity cap. Comparison tolerance affects broker metrics only.

Nearest-rank quantiles use the smallest value whose cumulative mass reaches
the requested percentile. Sampled p95/p99 use unit weights for valid poll
snapshots and also report duration-weighted tails. The oracle reports
duration-weighted tails and separate event-state-weighted tails. Signed
errors are sampled minus oracle; absolute errors are reported separately.
Empty support is null with a reason. Duration coverage uses the full window
per source. Oracle and sampled weighting differences are part of the
comparison design.

Truth episodes are contiguous eligible widened spans within one spec.
Gaps, metadata boundaries and window end censor episodes; a widened first
span after a break is left-censored. A sampled episode matches the earliest
unused truth episode with a witnessed origin sequence from its valid wide
state, on the same source and spec. Each episode matches at most once.
An observed episode with no match is false under this definition. Delayed
detects are possible from causal arrival delays. Onset is scored only for
uncensored left edges, recovery only when both right edges recovered, and
duration error only when all relevant edges are uncensored. Errors are signed
sampled clock minus oracle clock. Event recall with no truth episodes is null.

True revisions count changes of valid prices between consecutive eligible
truth states on the same spec; initial and post-gap states initialize a
segment. Observed changes use P1 duplicate and continuity rules. Exact
origin identity credits a true revision once; missed revisions are truth
identities without credit, with unlinked observed changes recorded
separately. Contribution from duplicate poll snapshots is descriptive.

The synthetic histories cover stable spread, a 120–180 ms spike, persistent
widening and recovery, missing/crossed/disconnected data, asynchronous
four-broker transitions, and clock/metadata boundaries. Synthetic evidence
cannot identify real missed ticks, actual broker synchronization or
independence, dealer identity, live liquidity or executable costs.

## Golden arithmetic and reproduction

The short-spike oracle has 60 ms at 0.90 and 2,140 ms at 0.20. Its duration
mean is 241/1,100 USD/troy oz and its p95/p99 are 0.20/0.90. The 0% 100 ms
schedule misses it. The 50% schedule observes it at 150 ms and sees recovery
at 250 ms. Measured onset and recovery are 30 and 70 ms late. The measured
duration is 100 ms, an error of +40 ms. These checks use exact integer
timestamps and Decimal arithmetic.

Run from the committed repository root after syncing the frozen environment.

```sh
uv sync --frozen --extra dev
uv run --frozen --extra dev python -m xauusd_quote_lab.sampling_experiments --output dist/p2-experiment
```

The output directory must be new. It receives a manifest and content hashes,
all six synthetic input histories, 384 detailed result rows, the 16-pair
summary and 16 phase slices, and six evidence packets below 64 KiB each.
The packets link to the detailed table by SHA-256. They use the predeclared
100/100 ms, 50% audit slice. The 16-pair summary pools truth/detection counts
and averages defined source-level distribution errors and duration coverage
uniformly. Broker coverage and consensus in that summary refer to the
four-broker asynchronous scenario. Phase-only rows use 100 ms tolerance
for broker diagnostics, with unchanged single-source results across tolerance.

The report estimates no execution or latency model. Follow-up research can
vary transport delay jointly with phase and test whether tail errors persist
over a predeclared larger family of synthetic burst durations.
