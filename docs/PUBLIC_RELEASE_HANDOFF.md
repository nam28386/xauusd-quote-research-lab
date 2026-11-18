# Public project handoff — XAUUSD Quote Research Lab

**Status:** source integrated on `main`; synthetic-only research workstation release candidate **0.4.0rc2**.
**Handoff date:** 2026-11-18 (Asia/Bangkok).
**Public repository:** https://github.com/nam28386/xauusd-quote-research-lab

## Release and evidence anchors

| Subject | Immutable reference |
|---|---|
| P0/P1 hardened source | `e0f7f80a2cb7c382818e728970dde426334af6b4` (PR #1) |
| P2 sampling source | `ee3853ab2089e90dbf514fb0ccde20499b789e9d` (PR #2) |
| P2.1 factorial source | `d19099e78e950bfd08a6029f91c65bac0e6f79b8` (PR #3) |
| P3 observatory source | `e3387cc69029b907da66c1c46956ec1398c80ffd` (PR #4) |
| P4 RC2 release source | `862e23d2d06ce47bbb524445a0d268ffe54a59c2` (PR #5) |
| P4 merge into `main` | `9a67934ad0c472f37ca09feead01af72b94d5815` |
| P4 RC2 CI at exact source SHA | https://github.com/nam28386/xauusd-quote-research-lab/actions/runs/44267545916 |

The exact-head RC2 GitHub Actions run `44267545916` completed **SUCCESS** for both `ubuntu-latest` and `windows-latest`, including the declared packaging and archive smoke pipeline. Local Codex results reported 120 Python tests passed, one platform-specific skip on Linux, three frontend tests and two Chromium tests. The merge commit's Git tree was verified equal to the RC2 source tree before this handoff documentation was added.

The older RC1 is historical. RC2 fixed a path-canonicalization issue in release packaging while preserving symlink/junction, allowlist, Git blob, hash and ZIP safety checks. The original failing Windows run is https://github.com/nam28386/xauusd-quote-research-lab/actions/runs/44262936290.

### RC2 binary provenance — IMPORTANT

The **reported original** RC2 archive was named `xauusd-quote-lab-0.4.0rc2.zip` with SHA-256:
`d3350319d087ef57722b3d6cfaa74f051629aa61350e979b0a977bfac25df9ab`.

That checksum belongs to the original Codex-produced RC2 archive **only**. The original ZIP and its `SHA256SUMS` were in the Codex workspace, **not uploaded as GitHub Release assets by this handoff**. Do not describe a repository checkout as that archived ZIP or use that digest to authenticate a newly rebuilt package.

For distribution, generate a new bundle from a pinned clean checkout, verify it and publish its actual ZIP, manifest and digest through an independently trusted channel. Since release evidence includes the code SHA, a rebuild from a later commit may legitimately produce different bytes and a different digest.

## Architecture and research contracts

- **P1:** Decimal quote observations, quality/clock eligibility, quote dynamics, widening censoring, backward-as-of broker comparisons and deterministic research evidence.
- **P2:** immutable synthetic source truth, polling simulator, 384-row sensitivity matrix and versioned results.
- **P2.1:** 6,912-row factorial design, 192 as-of rows, matched-estimand tail decomposition, finite phase checks and observational-equivalence counterexamples.
- **P3:** loopback-only read-only Python backend and React/TypeScript/Plotly Observatory using verified P1/P2/P2.1 artifacts.
- **P4:** Python 3.12 offline workstation launcher, Windows PowerShell/Linux shell workflows, verified ZIP packaging, and **validation/quarantine only** for declared offline inputs.

Primary source: `docs/CODEX_NEW_CHAT_MASTER.md`. Further contracts: `docs/RESEARCH_METHODS.md`, `docs/P1_INDEPENDENT_AUDIT.md`, `docs/P2_SAMPLING.md`, `docs/P21_FACTORIAL.md`, `docs/P3_OBSERVATORY.md`, `docs/P4_WORKSTATION.md`, `docs/P4_OFFLINE_IMPORT.md` and `docs/P4_RELEASE_ACCEPTANCE.md`.

## Quick start from public source checkout

Prerequisites for a **developer checkout**: Python 3.12, Git, uv, Node 24 and npm.

```sh
git clone https://github.com/nam28386/xauusd-quote-research-lab.git
cd xauusd-quote-research-lab
python scripts/preflight.py
uv sync --frozen --extra dev
npm --prefix web ci
npm --prefix web run build
uv run --frozen --extra dev pytest -q
```

Windows PowerShell:

```powershell
.\workstation.ps1 preflight
.\workstation.ps1 build
.\workstation.ps1 prepare
.\workstation.ps1 start --port 8765
```

Linux:

```sh
sh workstation.sh preflight
sh workstation.sh build
sh workstation.sh prepare
sh workstation.sh start --port 8765
```

Open `http://127.0.0.1:8765/` and check `http://127.0.0.1:8765/api/v1/health`. First-time preparation needs a new output directory; see `docs/P4_WORKSTATION.md`. For an approved, separately verified RC2 ZIP, extraction needs Python 3.12 and a browser, not the full developer toolchain.

To make and inspect a new release from a clean **committed** checkout, follow `docs/P4_WORKSTATION.md` for `package`, `verify`, and `smoke`; capture the new checksum rather than reusing the historical RC2 checksum.

## Acceptance and public safety

- All committed sample histories are explicitly **SYNTHETIC**; the public repository is **not** a live broker quote feed.
- Offline import only validates and quarantines explicitly declared data. It does not promote outside files automatically into synthetic measurements.
- Polling cannot identify missed real broker ticks or latent unobserved quote paths without further assumptions. Broker economic independence, clock synchronization and executable trading costs are **UNKNOWN**.
- The observatory binds to `127.0.0.1`, but software running on the same computer may access loopback. Do not use it as a remotely exposed authenticated application.
- Git SHA and self-consistent manifests establish provenance/consistency, not independent authenticity. Distribution requires a trusted digest or signature.
- Public source inspection did not reveal obvious broker credential or real tick files in the P4 RC2 tracked tree; this is not a guarantee about every previous commit or external artifact. Review the full Git history and distribution ZIP before publicly distributing additional files.
- **LOCAL_MT5_UNVERIFIED.** No live MT5, broker connection, real-data scientific acceptance or trade execution is claimed.
- Hosted GitHub Actions Windows success is not equivalent to an observed physical Windows desktop user-acceptance session.

## GitHub handoff

PRs #1 through #5 were merged **sequentially with merge commits** into `main` to preserve research-stage history. The merge commit `9a67934ad0c472f37ca09feead01af72b94d5815` has the exact same tree hash as the P4 RC2 head `862e23d2d06ce47bbb524445a0d268ffe54a59c2` before this documentation update. For precise reproduction of the original RC2 measurements and archive, **pin the original P4 RC2 source SHA**.

**Handoff scope:** public source + documentation + passing exact-source CI. **Not included:** an uploaded GitHub Release ZIP, signed installer, local Windows desktop testing, live broker access, trading execution or proven real-market predictive validity.
