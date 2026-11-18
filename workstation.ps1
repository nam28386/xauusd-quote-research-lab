$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "scripts/workstation.py"
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.12 -I -S $script @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -I -S $script @args
} else {
    Write-Error "Python 3.12 is required. Install Python 3.12 and its Windows launcher."
    exit 1
}
exit $LASTEXITCODE
