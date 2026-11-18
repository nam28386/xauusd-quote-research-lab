# RC3 publication runbook

The [release notes](RC3_RELEASE_NOTES.md) describe the intended prerelease.
Source review, CI artifacts, GitHub draft assets and a published prerelease
are separate states. For the historical RC2 provenance see the
[public handoff](PUBLIC_RELEASE_HANDOFF.md).

## Non-publishing verification

Push and pull request runs use a read-only repository token. The two-OS
research matrix checks out the workflow SHA, checks the locks, runs the
security and scientific regressions and exercises the frontend. The Ubuntu
packaging job then writes one ZIP and both checksum sidecars from that SHA.
It uploads a workflow artifact named `rc3-<sha>`. Separate Ubuntu and Windows
jobs download that same artifact, check hashes and source provenance, then
exercise the corresponding workstation launcher and clean extraction with
a temporary path containing spaces. Publish gates require both jobs to
succeed. Deterministic rebuilds are compared locally with the same
toolchain; the downloaded ZIP is the distribution under review.

For local reproduction from a committed checkout, use the
[workstation build guide](P4_WORKSTATION.md). With Python 3.12, uv and
Node installed, a POSIX terminal can run:

```sh
sha=$(git rev-parse HEAD)
python scripts/release_gate.py source --sha "$sha"
sh workstation.sh prepare --artifacts dist/rc3-inputs
python scripts/release_gate.py goldens --sha "$sha" --directory dist/rc3-inputs
sh workstation.sh package --artifacts dist/rc3-inputs --output dist/rc3-release
python -I -S scripts/release_gate.py bundle --sha "$sha" --directory dist/rc3-release
sh workstation.sh smoke --archive dist/rc3-release/xauusd-quote-lab-0.4.0rc3.zip
```

Use new output directories when reproducing twice. Record the platform,
Python, uv, Node and npm versions alongside the observed checksums.

## Publication after human approval

1. Review and merge the release PR. Verify CI against the actual merged
   `main` SHA. Use the push run for the exact revision if the PR run tested
   GitHub's synthetic merge commit.
2. Review and create tag `v0.4.0rc3` at the verified revision. Protect that tag
   against movement or deletion under the repository's tag policy.
3. Set up the `release-publication` environment for `main` with required
   reviewers where supported. Dispatch **Synthetic CI and release
   verification** from `main` with `create_draft` enabled and
   `reviewed_tag=v0.4.0rc3`. Verify the selected SHA is still the tip of
   `main`.
4. The dispatch builds or regenerates the canonical archive for that exact
   SHA. Wait for Ubuntu and Windows verification of the same artifact.
   Approve the protected environment after checking both results.
5. The isolated write job checks the tag and main again, validates the
   downloaded archive and sidecars, and creates a Draft GitHub Release
   marked as a prerelease. It uploads the ZIP, manifest and SHA256SUMS.
   Existing releases are not overwritten.
6. Inspect the actual draft, confirm the tag, prerelease flag and all three
   assets, and verify their downloaded bytes. Publish the prerelease through
   GitHub after final approval.

If API or environment permissions prevent publication, retain the CI
artifact and report the missing permission. Never describe a feature
branch build, dry run, or Actions artifact as a published main release.
