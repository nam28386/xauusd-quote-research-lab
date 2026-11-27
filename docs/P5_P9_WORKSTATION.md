# P5–P9 research workstation

The public workstation uses synthetic inputs. The private Windows pilot has its own
capture and replay workflow. P4 validation and the published P1/P2/P2.1 metric versions
retain their existing contracts.

## Verified milestones

The implementation in [PR #6](https://github.com/nam28386/xauusd-quote-research-lab/pull/6)
passed Windows and Ubuntu [CI at commit `6f75e33`](https://github.com/nam28386/xauusd-quote-research-lab/actions/runs/44969803699),
including the 25-file baseline comparison and offline archive smoke checks.
A clean Windows extraction was also opened in Chromium and the stress filter
was exercised over loopback. The workflow for a tagged build remains a
separate release step.

## Reproduce the research

Use a committed checkout with Python 3.12 and the frozen dependencies.

```powershell
uv sync --frozen --extra dev
uv run --frozen --extra dev python scripts/accept_baseline.py --artifacts dist/observatory-inputs
uv run --frozen --extra dev python scripts/benchmark_comparison.py
```

The acceptance command checks the candidate artifacts through the Observatory loader
and compares 25 measurement and evidence files to P4 commit
`c3879c4b627c19a8869a75d8aeeaeb7c153e0669`. It compares exact bytes for the research
tables and canonical JSON for evidence packets after removing the commit field.
The loader verifies the candidate manifests and the command checks their commit SHA.
Pass `--verify-only` to check artifacts prepared for the current commit.
The benchmark reports median elapsed time and peak traced allocation for the
comparison operation with one and four sources. Allocation tracing is measured
in a separate run.

## Inspect the P8 stress study

The Overview includes a fixed 64-cell synthetic design spanning burst, jitter,
clustered gaps and clock regressions, four intervals (100/250/500/1000 ms) and
four phases (0/25/50/75 percent). The read-only `/api/v1/sampling-stress` response
binds the ordered inputs and results with separate SHA-256 digests of canonical
JSON. It includes coverage, gap duration, poll counts, source-origin ages,
episode recall and separate duration-weighted and snapshot-weighted spread tails.
Origin age measures elapsed synthetic receive time. Real missed ticks, one-way
network latency and executable costs remain `UNKNOWN`.

## Accept a private pilot

Use the separate Windows collector and start with one symbol. Verify tick
timestamp advances during a market-open capture of at least 60 minutes, observe
disconnect and recovery, and reconcile capture counts and gaps against two
identical replay reports. Establish the instrument unit before publishing
comparative measurements. Evaluate REAL and DEMO in separate groups, and
require compatible receive clocks and three eligible broker aliases for a median.
Keep capture files and reports on the Windows workstation.

Connection and quote availability are initial checks. For the full session
review, preserve raw source timestamps and local receive timestamps separately.
Record any display-time conversion as derived data with its offset and
assumptions. If the clock relationship is unresolved, treat source-based
quote age as unavailable. Use compatible receive clocks for point-in-time
matching and preserve gaps and exclusions. The market-open session review
remains an empirical acceptance gate.

## Build and verify an offline candidate

```powershell
py -3.12 -I -S scripts/workstation.py package --artifacts dist/observatory-inputs --output dist/workstation-release
py -3.12 -I -S scripts/workstation.py smoke --archive dist/workstation-release/xauusd-quote-lab-0.5.0rc1.zip
```

Verify the resulting ZIP against the trusted checksum using the workstation
`verify --archive ... --sha256 ...` command before extraction. For a hosted
candidate, CI verifies the build on Windows and Ubuntu. On a `workstation-v*`
tag, it also uploads the verified ZIP, checksum, manifest and CycloneDX frontend
runtime inventory and attests their provenance after both platform jobs pass.
The offline backend uses the Python standard library. Its build and development
dependencies are pinned in the bundled lockfile. Verify a hosted attestation
with `gh attestation verify <file> --repo nam28386/xauusd-quote-research-lab`.
