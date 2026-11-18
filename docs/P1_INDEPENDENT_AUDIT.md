# Independent P1 release audit

## Baseline and method

The feature branch and PR #1 both resolved to
`190bc8723acc5fee21f10e9ece894cdce603e465` through Git. The working tree was
clean before adding the regressions. The original tree remains available at that
SHA. The full frozen baseline suite passed 43 tests. Six new regression tests
failed against the original implementation. The corrected suite passes 49 tests.

The canonical SHA-256 is
`014e306b446ece5e4eed5f33806dd715222a46c4939fd2ff04ec1c083d2fb0bd`.
The synthetic fixture SHA-256 is
`6a50516270328b855a3007b350001fc675bc7ce62ffef3f382dee5d7ad57fb9f`.
The baseline replay JSON including its final LF hashes to
`ba909b341ae7396c9f76b208fd7e8d1b757bd2ddd3a265fa67de56b7c26fd952`.

## Confirmed findings

Locations below refer to the baseline SHA.

| ID | Severity and location | Minimal counterexample | Baseline observation and required behavior | Regression |
|---|---|---|---|---|
| P1-A01 | BLOCKING · `src/xauusd_quote_lab/dynamics.py:71` | Window starts at 100. Poll order is wide at 120, reversed receipt at 90, narrow at 140. | Filtering individual timestamps drops the reversal and reports recovery, 20 ns of coverage and a revision. Censor at 120, credit zero duration and break the delta chain. | `test_regression_below_window_start_censors_instead_of_recovering` |
| P1-A02 | BLOCKING · `src/xauusd_quote_lab/quality.py:78`, `:128` | Comparable source times. Receipt 1 ms has processing −1 ns and source 10 ms. Receipt 2 ms has valid processing and source 2 ms. | A malformed processing clock hides the future source timestamp. The first row sets the source-order watermark to 10 ms and the second is excluded. Mark both problems on the first row and keep the second eligible. | `test_malformed_wall_clock_cannot_hide_future_source_or_poison_watermark` |
| P1-A03 | MAJOR · `src/xauusd_quote_lab/quality.py:10` | Set `decimal.DefaultContext.rounding = ROUND_DOWN` before importing the package in a fresh process. | The last reported digit of 11/30 changes from 7 to 6 at the same code SHA and with identical inputs. The declared half-even context should produce identical JSON. | `test_replay_uses_fixed_decimal_defaults_in_fresh_process` |
| P1-A04 | BLOCKING · `src/xauusd_quote_lab/evidence.py:86`, `:129` | Supply a nonempty dictionary as an input record with no fixture hash or session identity, or a dictionary as a finding with a binary float value. | Untyped dictionaries bypass nested validations and remain mutable. Evidence must require typed provenance and claims with validated scalar values. | `test_evidence_rejects_untyped_nested_provenance` |
| P1-A05 | MAJOR · `src/xauusd_quote_lab/evidence.py:122` | Put a 65,536-character limitation in the golden replay packet. | Serialization emits more than 65,536 bytes. The packet must reject oversized output. The 64 KiB UTF-8 wire budget is the policy selected for this audit. | `test_evidence_serialization_rejects_over_budget_packet` |
| P1-A06 | BLOCKING · `src/xauusd_quote_lab/replay.py:137` | Run the installed editable package from an unrelated Git repository with only the copied, committed golden fixture. | Replay succeeds and attributes measurements to the unrelated SHA. Require the running checkout's editable code and verify its source, fixture and project files against the recorded commit blobs. | `test_replay_rejects_git_sha_from_unrelated_checkout` |

The window rule keeps the leading pre-window prefix out of the estimator and
retains later regressed polls for censoring and exclusion accounting. The
source watermark accepts comparable source times only after the independent
future-source check. Dynamics and comparison publish v1.1 metric identifiers.
The packet layout remains v1. Its CLI verifies the running checkout and
committed bytes. The Python packet constructor accepts caller-supplied
provenance declarations and validates their shape.

## Measurement review and golden comparison

The unchanged tests exercise exact quoted prices, missing or crossed sides,
staleness, receive and processing cutoffs, source clock comparability, poll
ties, withdrawal of an invalid latest quote, age accounting, known and unknown
units, sessions, one through four distinct aliases, configured representatives
and separate account-environment labels. The audit also reviewed the poll
prefix, zero tail duration, no pre-window carry-in, capped interval duration,
recovery and right/left censoring. Retrospective receive-window duration is a
declared sampled-path estimator. Decision-time comparison separately enforces
processing eligibility.

Metrics from the original Git archive and the hardened checkout were serialized
with exact Decimal strings and compared byte for byte.

| Golden output | Baseline and hardened |
|---|---|
| Decisions at 124, 125 and 130 ns | 3, 4 and 3 eligible brokers |
| Median spreads at those decisions | 0.40, 0.45 and 0.40 USD/troy oz |
| Median mids at those decisions | 2000.35, 2000.375 and 2000.35 USD/troy oz |
| Broker coverage, unmatched slots, matched ages | 10/12, 2, ages 0, 4, 5, 5, 6, 7, 9, 10, 12 and 15 ns |
| Alpha snapshot mean and duration mean | 0.325 and 11/30 USD/troy oz, with the latter rounded to 128 significant digits |
| Alpha duration, coverage and revisions | 30 ns, 0.6, 1 |
| Alpha widening | Starts at 120 ns, censored at 130 ns for missing ask, duration 10 ns |

## Reproduction and release gate

Python 3.12.14 and uv 0.13.6. The Linux environment resolved pytest 8.4.2,
Ruff 0.17.5, iniconfig 2.3.1, packaging 26.3, pluggy 1.7.0, Pygments 2.21.0
and the editable project 0.1.0. The lock also includes platform-specific
dependencies such as Windows colorama 0.4.6.

```sh
git fetch --no-tags origin refs/heads/feat/p0-p1-cloud-research-core
git ls-remote origin refs/pull/1/head refs/heads/feat/p0-p1-cloud-research-core
python scripts/preflight.py
uv sync --frozen --extra dev
uv pip list
uv run --frozen --extra dev ruff check .
uv run --frozen --extra dev ruff format --check .
uv run --frozen --extra dev pytest -q
uv build
uv run --frozen --extra dev python -m xauusd_quote_lab.synthetic
uv run --frozen --extra dev python -m xauusd_quote_lab.replay
uv run --frozen --extra dev python scripts/audit_public_files.py
```

The local preflight, lint, format, tests, wheel and sdist build, fixture
loading, replay and source audit passed. GitHub Actions returned Forbidden
for the exact baseline SHA. Hosted Ubuntu and Windows require separate
exact-head evidence before acceptance. The source audit is a static screen
with pinned fixture verification. Synthetic software evidence cannot identify
live tick completeness, cross-broker independence, clock alignment, dealer
intent, tradability or realized trading costs. P2 is outside this release
audit. Local MT5 remains unverified.
