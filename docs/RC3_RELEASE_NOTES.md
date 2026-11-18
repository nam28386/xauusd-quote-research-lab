# XAUUSD Quote Research Lab 0.4.0rc3

RC3 is a prerelease of the synthetic-only offline research workstation.
It includes the P1 Golden evidence, P2 sampling laboratory, P2.1 factorial
study and read-only Observatory. RC3 adds verification of a single canonical
ZIP on Ubuntu and Windows. P1, P2 and P2.1 measurement definitions and
their frozen numeric outputs are preserved. The verifier also reads the
historical RC1 and RC2 manifests, which retain their original checksums.

## Assets and verification

An approved GitHub Release should carry three assets.

- `xauusd-quote-lab-0.4.0rc3.zip` contains source, bundled frontend,
  synthetic examples and offline documentation.
- `release-manifest.json` records exact code SHA, datasets, and file hashes.
- `SHA256SUMS` records the digests of the ZIP and manifest.

Before extracting, compare the ZIP digest with a digest obtained from a
trusted release channel. On Linux run `sha256sum -c SHA256SUMS` in the
download directory. On Windows run `Get-FileHash` on the ZIP and manifest
and check both against SHA256SUMS. From trusted source use the `verify`
command with `--archive PATH --sha256 DIGEST` to verify the internal inventory
and per-file checksums before unpacking. A digest from the same download
confirms consistency. Independent trust in distribution still matters.

## Offline quick start

Install Python 3.12 if needed, verify the download, extract it and open a
terminal inside the extracted directory. A browser and Python suffice to
run the bundled examples. The archive does not include a Python interpreter.

- Windows PowerShell: `.\workstation.ps1 preflight --offline` and
  `.\workstation.ps1 start --port 8765`. If scripts are disabled locally,
  run `py -3.12 -I -S scripts/workstation.py start --port 8765`.
- Linux: `sh workstation.sh preflight --offline` and
  `sh workstation.sh start --port 8765`.

Open `http://127.0.0.1:8765/`. Readiness is available at
`http://127.0.0.1:8765/api/v1/health`. Stop the launcher with Ctrl+C.
The workstation serves only a local, read-only Observatory. The Windows
hosted job exercises the launcher and clean archive smoke. It does not
represent a Windows desktop acceptance session.

## Research and provenance limits

Frozen CI compares the normalized P1 evidence and 17 P2/P2.1 files by
SHA-256, including the 384 P2 configurations and 6,912 P2.1 rows. All
release examples are synthetic. The offline input command validates
declared formats and quarantines inadmissible data. A valid receipt does
not authorize import into the Observatory. No live broker connection,
execution, trading, or market-validity claims are included.

See `docs/P4_WORKSTATION.md` for a source build and troubleshooting, and
`docs/RC3_PUBLICATION.md` for the release procedure. LOCAL_MT5_UNVERIFIED.
