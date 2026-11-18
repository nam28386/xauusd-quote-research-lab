# Offline workstation release candidate 0.4.0rc2

The ZIP ships tracked project source and lockfiles, a prebuilt local
Observatory, frozen synthetic examples for P1/P2/P2.1, two synthetic offline
validation examples, this documentation, and a release manifest. It needs an
installed Python 3.12 and a local browser. The ZIP contains neither a Python
interpreter nor a standalone executable. The bundled launch needs no Node,
npm, uv, Git, package downloads or broker network access.

## Windows quick start

Compare the download against a SHA-256 value obtained through a trusted
channel. The adjacent SHA256SUMS records the release bytes for comparison.

```powershell
Get-FileHash .\xauusd-quote-lab-0.4.0rc2.zip -Algorithm SHA256
Expand-Archive -LiteralPath .\xauusd-quote-lab-0.4.0rc2.zip -DestinationPath .\workstation
Set-Location .\workstation
.\workstation.ps1 preflight --offline
.\workstation.ps1 start --port 8765
```

If the local PowerShell execution policy disallows scripts, run the Python
launcher directly with `py -3.12 -I -S scripts/workstation.py start --port 8765`.
Open `http://127.0.0.1:8765/` in a current browser. Use Ctrl+C in the terminal
to stop the server. `Invoke-RestMethod http://127.0.0.1:8765/api/v1/health`
reports readiness and the loaded synthetic datasets. All requests go to the
single loopback origin. Choose another port if the default is in use.
The binding option accepts only `127.0.0.1`.

On Linux replace `.\workstation.ps1` with `sh workstation.sh`. Neither
launcher changes PowerShell policy or installs a system dependency.

## Developer checkout and packaging

From a clean committed checkout install Python 3.12, uv, Git and Node 24
(with npm) using their normal installers. The release wrappers keep each
operation as a single command.

```powershell
.\workstation.ps1 preflight
.\workstation.ps1 build
.\workstation.ps1 prepare
.\workstation.ps1 start --port 8765
```

The build uses frozen uv sync, uv build, npm ci, and the TypeScript/esbuild
frontend build. Initial dependency installation needs access to package
registries or populated caches. Research preparation uses the unchanged
upstream runners and writes to a new `dist/workstation-data` by default.
Use `--artifacts PATH` for an alternate root. Git provenance checks require
a committed checkout for preparation and packaging. The extracted ZIP runs
the prepared data. To regenerate it, use a Git checkout of the manifest SHA.

```powershell
.\workstation.ps1 package --output dist/release-candidate
.\workstation.ps1 verify --archive dist/release-candidate/xauusd-quote-lab-0.4.0rc2.zip
.\workstation.ps1 smoke --archive dist/release-candidate/xauusd-quote-lab-0.4.0rc2.zip
```

Packaging rebuilds the locked frontend, verifies source bytes against Git,
and verifies examples from that same commit through the P3 loader. It writes
the ZIP, release-manifest.json and SHA256SUMS to a new output directory.
The manifest contains the source commit, per-file hashes and classifications.
ZIP member order, metadata and timestamps are fixed. Within the same
toolchain the bytes reproduce. A digest supplied independently can be checked
with `verify --archive PATH --sha256 DIGEST`, including before clean unpack
in the smoke command. A self-consistent manifest or a declared code SHA alone
cannot authenticate a download. The release is not digitally signed.

## Troubleshooting

- Missing Python or unsupported version. Install Python 3.12 and enable the
  Windows launcher, or put Python 3.12 on PATH.
- Missing uv, Node, npm or Git. These are developer tools for build or
  regeneration. A verified release ZIP can launch with just Python 3.12.
- Build cache denied. Point UV_CACHE_DIR and npm_config_cache at writable
  paths, keeping the package locks and integrity verification enabled.
- Missing compiled frontend or synthetic files. Run build and prepare in a
  checkout, or re-extract the verified release.
- Dataset preparation refuses an existing directory. Choose a new path and
  retain the old artifact set for comparison.
- Digest or schema mismatch. Re-obtain the original artifact at a trusted
  hash. Preserve the rejected copy separately for diagnosis.
- Address in use. Try `--port 8766`. The startup smoke uses an OS-assigned
  loopback port and verifies shutdown.
