# P4 release acceptance protocol

## Integration and provenance

P4 branches from P3 e3387cc69029b907da66c1c46956ec1398c80ffd.
At the frozen baseline, PR #4 points to that commit. The supplied exact-head
GitHub Actions run 44257733141 records the P3 Ubuntu and Windows checks.
A P4 release review must use its own exact-head evidence.

Review stack from the bottom up. Review and merge PR #1 into main first.
After verifying the landed SHA and reviewing the next diff, retarget PR #2
to main. Repeat for PR #3 and PR #4. Review and retarget P4 after its parent
lands. A squash merge can leave earlier changes appearing in a stacked diff.
Check ancestry and the retargeted diff, and restore a clean review base
before relying on the next approval. Re-run the release gates against each
actual merge candidate. This protocol grants no automatic merge authority.

The P3 baseline must reproduce 88 Python tests, three frontend tests and two
Chromium tests. Its P2 384-row primary digest is
`bdc5083df7a118fce5d48c68def2d30317e7bec17910801a9a0f4e6cd90327d1`.
Its P2.1 6,912-row primary digest is
`16626a948ce64fc59c42644a38fef0fd4f55463ff088c1b81676fe8f496acd92`.
Generate P1/P2/P2.1 from the candidate commit and compare the research
tables byte for byte. Candidate evidence and manifests may identify a new
code SHA. Accept that provenance difference only after validating the
candidate hashes and comparing inherited quantities. In particular, the
short-spike no-lookahead and tail decomposition golden invariants must pass.

## Release gates

| Gate | Required evidence |
|---|---|
| Research regression | All prior P1/P2/P2.1/P3 tests and frozen tables reproduced |
| Security | Source audit, npm dependency audit, offline parser quarantine and read-only Host/Origin/path checks |
| Packaging | Approved files and synthetic sources only, instructions and hash manifest included, deterministic rebuild, verified clean unpack |
| Windows | Exact candidate build, PowerShell preflight and archive smoke, Chromium integration against freshly prepared artifacts |
| Ubuntu | Exact candidate build, shell preflight and archive smoke, Chromium integration against freshly prepared artifacts |
| Provenance | Local and remote SHA agreement, health check, immutable artifact bytes and independent digest comparison for distribution |

The clean archive smoke verifies the release in a temporary path with
spaces, launches using Python's standard library, checks readiness, all
three synthetic datasets, the shipped HTML and JavaScript, and checks
shutdown. It exercises the offline archive launch. Hosted automation
validates the Windows runner, while actual Windows desktop operation
requires a separate observed session when available.

If API permission prevents reading hosted CI, report that gate as UNKNOWN.
The release can be evaluated locally while cross-platform acceptance remains
pending. Do not infer real-data readiness from the fixture suite. The
workstation has no live collector or automatic data promotion.

The P4 dependency audit identified PYSEC-2026-1845 in the baseline pytest
version. The developer lock pins pytest 9.0.3, the audited fixed version.
This affects the test harness. Candidate acceptance still requires exact
baseline replay comparisons.
