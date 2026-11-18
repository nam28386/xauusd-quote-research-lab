# Research methods v1

Prices are positive finite decimal strings with up to 32 digits on each side
of the decimal point. Spread is ask minus bid and mid is half their sum.
Crossed, missing or invalid prices produce no quoted measurement. The
calculation context uses 128 significant digits with half-even rounding.
Finite fixture price arithmetic is exact. Recurring ratios round in that
context.

## Quote Dynamics

Use a closed receive-time window and observations available by its end. No
pre-window quote is carried in. Deltas compare consecutive eligible snapshots
within the same continuity segment. An unchanged bid/ask pair is a duplicate
snapshot even if another poll receipt exists. An input duplicate flag also
prevents counting a new revision. Quote revisions per second use covered
duration as the denominator. Zero covered duration yields a null intensity.

Snapshot weighting includes eligible duplicate snapshots. Duration weighting
uses observed left-endpoint spreads over half-open intervals bounded by the
next received observation and the age tolerance. An invalid arrival closes
coverage at arrival. A reversed next clock contributes zero interval after
the last eligible observation. An outage leaves a gap beyond age expiry.
The last snapshot contributes zero duration without a bounding arrival.
Coverage is the sum of valid interval durations divided by window length.
The resulting duration weights describe sampled paths under this convention.

Widening begins at the first eligible spread at or above the explicit
threshold. An event starting without a preceding eligible snapshot in the
continuity segment is left-censored. Recovery requires an eligible below-
threshold quote within continuity. Missingness, staleness, a clock reversal,
an instrument metadata version change or the observation window boundary
censors an open event. Event durations run between the stated observation
boundaries and cannot reconstruct unseen onset or recovery.

## Broker Comparison

Assign an explicitly configured representative to repeated broker aliases.
Without a predeclared representative, the alias is ambiguous and its accounts
are excluded. The policy never chooses a different account after the chosen
representative becomes ineligible. Each eligible broker contributes one quote.
One broker reports descriptive prices. Two report signed pairwise differences
in lexicographic alias order. Three or four report Decimal medians of spreads
and mids separately. Valid coverage divides eligible source matches by all
configured source-decision slots. Consensus coverage divides decisions with
three or more eligible brokers by all decisions. Empty grids have null
coverage.

## Golden calculations

At 125 ns the four spreads are 0.60, 0.40, 0.30 and 0.50. Their median is
0.45 and the median mid is 2000.375. At 130 ns alpha's missing ask blocks the
120 ns quote. Alpha's spread sequence contains four eligible snapshots with
mean 0.325. Its three 10 ns intervals contribute spread weights 2.5, 2.5 and
6.0, for duration mean 11/30. Alpha's 120 ns widening is censored at 130 ns.
