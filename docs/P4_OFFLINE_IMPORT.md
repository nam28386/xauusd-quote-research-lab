# Offline validation security and data contract

The validator supports `offline-quote-jsonl-v1` only. A local directory holds
`manifest.json` and `observations.jsonl`. The manifest itself is UTF-8 JSON
using these exact object fields.

| Field | Contract |
|---|---|
| schema_version | offline-quote-jsonl-v1 |
| source | identity and acquisition_method |
| environment | MOCK, REAL, DEMO or UNKNOWN |
| provenance_class | SYNTHETIC, EXTERNAL or UNKNOWN |
| authorization | decision and license_or_permission declaration |
| instrument | symbol, price_unit, quote_currency and spec_version |
| clocks | source_domain, receive_domain, processing_domain, monotonic_domain and source_comparable_to_receive |
| session_id | One declared source session |
| data_file | observations.jsonl |
| source_sha256 | Lowercase SHA-256 of exact JSONL bytes |
| processing | producer, policy_version raw-v1 and empty transformations |

Each observation has exactly sequence, bid, ask, source_time_ms,
received_wall_ns, processing_wall_ns and received_monotonic_ns. Sequence is
a nonnegative safe JSON integer. Prices are decimal strings or null. Floating
JSON numbers, exponent notation and malformed text are rejected. Timestamps
are canonical unsigned integer strings with a 64-bit upper bound. Source
milliseconds and monotonic nanoseconds may be null. Mandatory wall receive
and processing values are separate fields. Clock order is diagnosed within
each declared domain. Source/receive comparison requires an explicit
comparability declaration. Processing/receive comparison requires equal
declared domains. No timestamp is invented, repaired or filled.

The parser hashes the byte-capped file before observation parsing and checks
exact schema, provenance and source classification. It rejects unsafe file
references and symbolic input files. Budgets are 32 KiB for the manifest,
8 MiB for observations, 4 KiB per row and 50,000 rows. Oversize conditions
lead to a receipt with incomplete scan. Receipt fields contain counts, fixed
reason codes and digests. They omit raw quotes and arbitrary input metadata
values.

Only authorized MOCK with SYNTHETIC provenance and SYNTHETIC_GENERATOR can
receive a synthetic validation verdict. REAL, DEMO or UNKNOWN labels are
quarantined without row parsing. A bounded local file may be hashed so the
receipt can identify it. An authorization declaration is a claim supplied
by the dataset owner. The validator cannot establish legal authorization or
prove that a label truthfully describes the source. Use the bundled synthetic
examples in Cloud.

```powershell
py -3.12 -I -S scripts/validate_offline.py fixtures/offline/synthetic-valid --reports local-receipts
py -3.12 -I -S scripts/validate_offline.py fixtures/offline/synthetic-invalid --reports local-receipts
```

Linux can use `python3.12` in the same commands. Exit 0 writes a validated
receipt. Exit 2 writes a quarantined receipt. The quarantine directory holds
immutable, content-addressed receipts. Source bytes remain at their original
location. No raw dataset is copied to the workstation, evidence catalog or
Observatory. There is no promotion command. A validated row count is a count
of rows passing syntax and row-quality checks. Dataset admissibility also
requires provenance and compatible units. Duplicate snapshots remain
visible in the report. Query counts are integrity diagnostics rather than
evidence of market data quality.

Future empirical work requires a separate authorized policy, ingestion
review and research design. No validation verdict reveals live missed ticks,
network latency, broker independence, executable arbitrage, actor identity
or realized execution cost. LOCAL_MT5_UNVERIFIED.
