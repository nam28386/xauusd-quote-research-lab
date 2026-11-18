# Domain contracts v1

| Contract | Meaning |
|---|---|
| BrokerSource | Declared source, account environment label and session. Synthetic provenance is required to construct a research stream. |
| InstrumentSpec | Explicit XAUUSD canonical mapping and USD per troy ounce unit for eligible prices. Point, tick, contract size and digits can remain null. |
| QuoteObservation | Frozen raw bid/ask strings, poll sequence, distinct timestamps, quality flags, source/session and spec version. |
| QualityState | Per-quote reason codes and eligibility. Duplicate snapshot and partial coverage are informational flags. |
| QuoteDynamics | Versioned single-session spread, mid changes, revisions, weighting, widening intervals and exclusions. |
| BrokerComparison | Decision-time source matches, eligibility, descriptive mode, pairwise or consensus results, ages and coverage. |
| ResearchEvidencePacket | Frozen claims, fixture/session/source provenance, code and metric versions, assumptions, findings and limitations. |

Each stream binds one source session. An observation with a different source,
session or ingestion mode fails stream construction. Spec versions have one
definition per stream. An unknown version is excluded. A known version change
keeps quoted measurements under its own unit declaration and breaks dynamics
continuity. Unrelated sessions cannot be concatenated into one stream.

All measurements in the fixture are synthetic. REAL and DEMO are retained as
distinct simulated account-environment labels.
