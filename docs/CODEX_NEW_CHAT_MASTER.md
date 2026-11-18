# XAUUSD Quote Research Lab V2 — New-Chat / Codex Cloud Master Handoff

**Document version:** 2026-11-18 / v1.0  
**Target repository:** `nam28386/xauusd-quote-research-lab` (new repository to be created by the user)  
**Existing reference:** `nam28386/xauusd-spread-intelligence`, branch `feat/phase-02-mt5-connector`, reference commit `807b92a9d006007634eccb1ba1b3faaa00301bcb`.  
**Scope:** Codex Cloud research on fully synthetic quotes. No live broker access.

> This handoff is SELF-CONTAINED. A fresh chat or Codex task must not rely on prior chat messages, failed Codex tasks, inaccessible `/workspace` files, or previous cloud VM state.

## 1. Objective and strict boundaries

Build a new Python 3.12, cloud-first, research-grade **XAUUSD Multi-Broker Quote Intelligence Lab**. The new repository is intentionally smaller and more reproducible than the existing MT5-focused XBSIS repository. The existing repository remains the legacy local collector / verified software reference. Do NOT copy its runtime wholesale.

The new lab must perform reproducible synthetic market-quote measurement, N-source descriptive comparison, sampling-bias experiments, research evidence packet generation, and eventually an optional localhost research UI. The lab is NOT a trading engine, broker connector, executable-price comparison, latency benchmark, or dealer-identification system.

Cloud-specific rules:
- Synthetic data only. No real MT5 SDK, terminals, passwords, account numbers, real price files, or live broker connections in Codex Cloud.
- Never make Python import `MetaTrader5`, call trading APIs, or install Windows-only MT5 packages on Linux.
- No unattended live ingestion, no cloud broker API credentials, no telemetry.
- The new repo should be **private initially**, with user-controlled GitHub/Codex access. Public release can occur after an explicit security review.
- The previous `No usable execution environment is available` error indicates a Codex compute provisioning failure. Creating a new repo does not itself repair missing compute. Fail fast if `pwd` cannot run.
- Codex Cloud (ChatGPT product) and the separate OpenAI Agents API hosted sandbox are different products. Do not assume API sandbox provisioning solves a Codex Cloud task failure.

## 2. Design principles

1. Source identity, account environment, and instrument units are declarations until independently verified.
2. Preserve raw observations unchanged; derive measurements in separately versioned objects.
3. Keep source, wall-receive, processing, and research decision times distinct. Monotonic time is for measuring durations inside a process, not comparing absolute timestamps across processes.
4. A quote is usable at decision time t only when it was received at or before t, is not invalid/stale, and satisfies explicit age tolerance.
5. Do not replace an invalid latest quote with an older valid quote.
6. A duplicate sampled snapshot is not a new market tick.
7. When fewer than THREE eligible distinct broker aliases exist, do not report an N-broker consensus median; allow explicit two-source pairwise descriptive comparison.
8. Multiple accounts from the same broker cannot inflate broker count. Broker aliases alone do not prove economic independence.
9. REAL and DEMO may be compared descriptively with separate labels but do not have equivalent execution conditions.
10. Distinguish FACT, MEASUREMENT, INFERENCE, HYPOTHESIS, UNKNOWN and REJECTED. Never promote an observation to causal identification.
11. Use Decimal for prices and aggregations. Decimal values and nanosecond timestamps must cross JSON as strings when precision is at risk.
12. Every claim must be tied to code revision, input fixture hash, metric version, exclusions and clock assumptions.
13. No feature creep: no React, Redis, Kafka, PostgreSQL, ML, options, GC or automated execution in the initial vertical slice.

## 3. Domain contracts to implement

### 3.1 BrokerSource v1
`source_id`, `broker_alias`, `server_alias`, `environment: MOCK|REAL|DEMO|UNKNOWN`, `account_type_user_label`, `ingestion_mode`, `provenance_class`, `source_identity_verification_state`, `session_id`. No account identifiers or secrets.

### 3.2 InstrumentSpec v1
`raw_symbol`, `canonical_symbol=XAUUSD`, `price_unit=USD_PER_TROY_OUNCE|UNKNOWN`, `quote_currency`, `point_size`, `tick_size`, `digits`, `contract_size`, `spec_version`, `spec_source`, `user_unit_asserted`. Unknown values remain null. Do not infer a universal pip/point size.

### 3.3 QuoteObservation v1
Immutable `bid_text`, `ask_text`, `source_time_ms_or_null`, `received_wall_ns`, `processing_wall_ns`, optional per-process `received_monotonic_ns`, `poll_sequence`, `source_id`, `session_id`, `instrument_spec_version`, `quality_flags`, `ingestion_mode`. Timestamps in distinct domains; do not silently overwrite or synthesize source clocks.

### 3.4 QualityState v1
At least: missing sides, invalid sides, crossed, duplicate snapshot, stale, future timestamp, source out-of-order, wall-clock reversal, unsupported instrument, unknown unit, source disconnect, partial source coverage. Record exclusions, not just binary validity.

### 3.5 QuoteDynamics v1
- spread = ask - bid
- mid = (ask + bid) / 2
- delta_bid, delta_ask, delta_mid, delta_spread relative to preceding eligible observation in same session
- observed quote-revision count/intensity (not total real ticks)
- snapshot-weighted and duration-weighted quoted spread
- widening event with explicit threshold
- widened duration, recovery / censored recovery
- coverage, missing/invalid/duplicate exclusions

All formulas, event boundaries, lookback and truncation rules must be versioned and tested with hand-calculated fixtures. Invalid, stale and clock-reversed data break continuity. Do not forward-fill through outages.

### 3.6 BrokerComparison v1
Support 1–4 sources using backward-as-of receive-time alignment only when clock-domain compatibility is justified. The configured quote-age tolerance is not a network-latency measurement. Require explicit same-instrument unit compatibility and source/session boundaries. At each evaluation time: select latest received quote per source, reject an invalid latest quote, cap age, group by distinct broker alias, choose deterministic predeclared representative for a broker if multiple accounts exist (or mark ambiguous and exclude), and calculate median quoted spread and median midprice when >=3 distinct eligible brokers. Return unmatched counts, age distributions, coverage and unavailable reasons. At 2 brokers return pairwise-only results; at 1 return descriptive single-source results.

### 3.7 ResearchEvidencePacket v1
Fields: research_id, hypothesis_id nullable, created timestamp, input fixture/session IDs and SHA-256, code SHA, schema/metric versions, question, clock assumptions, parameters, eligible source count, exclusion counts, quantitative findings, candidate explanations, falsifiers, limitation statements, and epistemic statuses. Generated reports must be deterministic given frozen inputs/config where possible. No fabricated confidence or causal claims.

## 4. Target repository layout

```text
xauusd-quote-research-lab/
  AGENTS.md
  README.md
  .gitignore
  .gitattributes
  pyproject.toml
  uv.lock                      # generated after environment is runnable
  src/xauusd_quote_lab/
    contracts.py
    quality.py
    dynamics.py
    comparison.py
    sampling.py
    evidence.py
    synthetic.py
    io.py
    api.py                   # deferred until core passes
  tests/
    test_contracts.py
    test_dynamics.py
    test_comparison.py
    test_sampling.py
    test_temporal.py
    test_evidence.py
    test_security.py
  fixtures/synthetic/          # synthetic only, immutable golden fixtures
  docs/
    DOMAIN_CONTRACTS.md
    MEASUREMENT_IDENTIFIABILITY.md
    RESEARCH_METHODS.md
    CLOCK_AND_AVAILABILITY.md
    INTEGRATION_WITH_XBSIS.md
    CLOUD_ACCEPTANCE.md
  scripts/
    preflight.py
    audit_public_files.py
  .github/workflows/ci.yml
```

Do not create empty fake modules just to match a tree. Implement the smallest coherent slice first and add files when needed.

## 5. Phase plan and completion gates

### P0 — Cloud-safe repository bootstrap

- Start from initialized GitHub repository with README (created by the user through GitHub UI, or from a provided starter ZIP).
- Confirm workspace runs `pwd`, `python --version`, `git status`, `git rev-parse HEAD` before any setup action.
- Create/verify AGENTS.md, Python 3.12 pyproject, deterministic synthetic fixture, unittest/pytest tests, and Linux + Windows FakeSDK CI.
- Install uv only after execution is possible; generate and commit `uv.lock`. Use `uv sync --frozen --extra dev` after lock creation.
- Validate `ruff check`, `ruff format --check`, `pytest`, build, security audit, and a simple synthetic replay. CI must not import MT5.
- Commit and push a small reviewable P0 milestone. Verify actual remote commit and hosted CI when available.

### P1 — Measurement-ready domain core (PRIORITY)

- Freeze versioned contracts and explicit USD/oz unit eligibility.
- Quote Dynamics with Decimal, missingness, exact clock handling and widening censoring.
- N-source backward-as-of median/mid/spread with >=3 distinct brokers.
- Synthetic hand-audited tests for 1/2/3/4 brokers, duplicated broker accounts, latest invalid quote, stale data, missing side, crossed book, time reversal, no-lookahead, unit mismatch, REAL/DEMO labels.
- A bounded JSON evidence packet with source provenance, code revision and unknowns.
- No live feeds and no new frontend. Push P1 only when tests pass.

### P2 — Sampling & measurement robustness

- Construct synthetic ground-truth event streams and sample at 100, 250, 500, 1000 milliseconds.
- Measure event-recall relative to synthetic truth only; quantify p95/p99 and widening undermeasurement, duplicates and coverage.
- Sensitivity across explicitly predeclared 100/250/500/1000 ms as-of tolerances.
- Distinguish event time, source time, local receive time, decision time and process-monotonic time.
- Unknown real-world missed ticks and broker historical completeness remain UNKNOWN.

### P3 — Local read-only API and compact visualization (ONLY AFTER P1/P2)

- Thin FastAPI localhost-only interface and static, local-only dashboard, or JSON-only API if browser UI adds no research value.
- Show source eligibility, spread/mid chart, missing gaps, cross-broker availability, sampling sensitivity and evidence status.
- Do not expose PII, terminal paths, arbitrary file access, upload endpoints, or cloud-hosted public listener.

### P4 — Optional Windows-to-Cloud migration bridge (SEPARATE APPROVAL)

- Existing XBSIS repository remains the Windows collector. No embedded MT5 in this new research repo.
- Define a strictly opt-in, offline, versioned export/import protocol for local data, with schema/clock/unit mapping and privacy review.
- Import only explicit user-approved sanitized artifacts; never automatically sync raw REAL quotes to a public repo or Codex Cloud.
- Verify parity with legacy `observation-v1` on synthetic fixtures. Do not claim parity from docs alone.

## 6. Adversarial test matrix

| Test | Expected invariant | Severity |
|---|---|---|
| Decimal 2000.10 / 2000.35 | spread = 0.25, mid = 2000.225 | BLOCKING |
| Bid 2000.40 / ask 2000.30 | crossed => no valid spread or mid | BLOCKING |
| Null ask | missing flag, no derived metric | BLOCKING |
| Unknown unit | no USD/oz quoted metric | BLOCKING |
| Duplicate polling quote | no new observed broker quote revision | MAJOR |
| Invalid most-recent quote | older quote must not substitute | BLOCKING |
| Candidate quote received at t+1 | unavailable at decision t | BLOCKING |
| 2 distinct brokers | pairwise only, consensus unavailable | BLOCKING |
| 3 distinct brokers | consensus median eligible | BLOCKING |
| 2 accounts from same broker | count broker once, no arbitrary pick | BLOCKING |
| REAL + DEMO | distinct labels and non-equivalent-cost warning | MAJOR |
| Clock reversed | continuity breaks, comparison excluded | BLOCKING |
| Invalid after widening | event censored, no invented recovery | BLOCKING |
| Polling misses short spike | synthetic truth explicitly detects missed spike | MAJOR |
| Source metadata changes | versioned or rejected, never silently reused | BLOCKING |
| CI Linux & Windows | synthetic-only tests and no MT5 imports | MAJOR |
| Security audit | no secrets, raw real quotes, account IDs or terminals | BLOCKING |

## 7. Operational prompt for NEW CODEX CHAT / TASK 01

Copy this complete section into a new Codex Cloud task after a repository and working environment have been created. Alternatively attach this entire Markdown and ask the agent to execute this section. If attachment reading fails, paste the text rather than relying on inaccessible workspace files.

> You are a Principal Quant Research Engineer, Domain-Driven Architect and Adversarial Software Auditor. Repository: `nam28386/xauusd-quote-research-lab`. Parent historical reference: `nam28386/xauusd-spread-intelligence@807b92a9d006007634eccb1ba1b3faaa00301bcb` (read-only reference, not a required runtime dependency).
>
> First execute `pwd`, `python --version`, `git status --short` and `git rev-parse HEAD`. If the shell itself is unavailable, stop with `WORKSPACE_BOOT_FAILURE`; do not fabricate work, retry indefinitely or conflate infrastructure failure with repository bugs.
>
> Inspect the current repository, README and AGENTS.md. If the starter already has working synthetic math, preserve its functionality. Work in a new feature branch (`feat/p0-p1-cloud-research-core`) based on actual main. Do not overwrite changes or force-push.
>
> Implement P0 and P1 only, following the domain contracts, versioning, no-lookahead rules and adversarial tests in this document. Use Python 3.12, Decimal, typed immutable models and minimal dependencies. Produce `uv.lock` and reproducible tests. Cloud must use SYNTHETIC data only; never import or initialize MetaTrader5 or touch live brokers. Keep the whole project read-only and local-first.
>
> Run and report actual commands: `uv sync --frozen --extra dev`, `uv run --frozen --extra dev ruff check .`, `uv run --frozen --extra dev ruff format --check .`, `uv run --frozen --extra dev pytest -q`, `uv build`, an explicit synthetic replay or smoke, and source-file security audit. When commands are unavailable, mark as not executed. Add Linux and Windows CI with synthetic-only tests; do not call FakeSDK CI a live broker validation.
>
> Create versioned docs and tests; calculate Quote Dynamics, N-source median with 3 distinct broker minimum, exclusions, no-lookahead comparisons and Research Evidence Packets. Do not implement P2/P3/P4 or ML in this task. Commit, push and verify remote SHA. Create Draft PR to main when permitted; do not merge. If permissions prevent pushing, retain a verifiable local commit and state blockers.
>
> Final response MUST be in Vietnamese: baseline SHA, new SHA, branch/PR URLs, files changed, tests executed, CI results, security audit, scientific limitations, unknowns and next phase. Use verdict `P0_P1_CLOUD_VERIFIED`, `P0_P1_INCOMPLETE`, `WORKSPACE_BOOT_FAILURE`, `REPO_ACCESS_BLOCKED`, or `BLOCKED`. Do not claim success without evidence.

## 8. Fresh ChatGPT (analysis-only) starter message

Use this if starting a new normal ChatGPT conversation rather than a Codex execution task:

> Read the attached `XAUUSD_QUOTE_RESEARCH_LAB_V2_NEW_CHAT_MASTER.md` in full. Help me create `nam28386/xauusd-quote-research-lab` as a cloud-first synthetic-only financial research repository. Audit the plan, identify blocking assumptions, and give step-by-step GitHub/Codex Cloud instructions. Do not assume any code was executed or a new repository has already been created. If execution tools are available, implement only P0/P1 with actual tests. Separate reproducible software evidence from real MT5 evidence. Respond in Vietnamese.

## 9. Security and provenance gates

- NO account identifiers, passwords, broker terminal paths, logs, live REAL quote data or private source files in GitHub or cloud tasks.
- Do not run MT5 capture in cloud, do not call trading/order/account-history endpoints.
- Do not use raw historical browser screenshots as ground truth of all ticks.
- Keep Python/Linux sandbox operations deterministic and bounded; no long-running service or background scheduling is required for P0/P1.
- Include SHA-256 hash of synthetic fixture and metric schema versions in the evidence packet.
- Existing legacy source remains unaffected. Do not change its `main` or feature branches.

## 10. Stopping condition and status vocabulary

- `WORKSPACE_BOOT_FAILURE`: no shell command possible. No code changes claimed.
- `REPO_ACCESS_BLOCKED`: execution works but repo checkout/permissions do not.
- `P0_P1_INCOMPLETE`: partial work/failed tests or missing CI evidence.
- `P0_P1_CLOUD_VERIFIED`: source changes, synthetic tests, push, and required cloud checks verifiably succeeded (record each gate separately).
- `LOCAL_MT5_UNVERIFIED`: always unchanged in this Cloud task.

**External setup:** The user must create/authorize the repository if the Codex or GitHub connection lacks create-repository permissions. A downloaded starter ZIP is a local scaffold, not proof of a GitHub remote repository.