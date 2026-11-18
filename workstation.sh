#!/usr/bin/env sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if command -v python3.12 >/dev/null 2>&1; then
    python=python3.12
elif command -v python3 >/dev/null 2>&1; then
    python=python3
else
    printf '%s\n' 'Python 3.12 is required. Install it and add it to PATH.' >&2
    exit 1
fi
exec "$python" -I -S "$root/scripts/workstation.py" "$@"
