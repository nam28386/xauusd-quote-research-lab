"""Audit candidate repository files without printing matched values."""

import ast
import re
import subprocess
from pathlib import Path

from xauusd_quote_lab.synthetic import FIXTURE_PATH, load_fixture

FORBIDDEN_IMPORTS = {
    "metatrader5",
    "socket",
    "requests",
    "httpx",
    "urllib",
    "aiohttp",
    "websocket",
    "ccxt",
}
SENSITIVE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|github_pat_[a-zA-Z0-9_]{20,}|"
    r"gh[pousr]_[a-zA-Z0-9]{20,}|AKIA[A-Z0-9]{16}|"
    r"(?im:^[ \t]*(?:password|api[_-]?key|access[_-]?token|account[_-]?(?:id|number))"
    r"[ \t]*[:=][ \t]*\S+)|(?:[A-Za-z]:\\[^\r\n]*|/Users/[^\s]+|/home/[^\s]+)"
    r"(?:terminal64?\.exe|MetaTrader)",
    re.IGNORECASE,
)


def inspect_python(source: str) -> list[str]:
    issues = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        if any(name.split(".")[0].lower() in FORBIDDEN_IMPORTS for name in names):
            issues.append(f"line {node.lineno}: forbidden import")
    return issues


def main() -> None:
    names = (
        subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
        )
        .decode("utf-8")
        .split("\0")
    )
    issues = []
    for name in sorted(set(filter(None, names))):
        path = Path(name)
        if path.is_symlink():
            issues.append(f"{name}: symlink")
            continue
        if path.suffix.lower() not in {
            ".md",
            ".py",
            ".toml",
            ".lock",
            ".yml",
            ".json",
            ".typed",
            "",
        }:
            issues.append(f"{name}: unreviewed file type")
            continue
        if path.suffix == ".json" and path != FIXTURE_PATH:
            issues.append(f"{name}: unreviewed data file")
        source = path.read_text(encoding="utf-8")
        if path.name != "audit_public_files.py" and SENSITIVE.search(source):
            issues.append(f"{name}: possible sensitive content")
        if path.suffix == ".py":
            issues.extend(f"{name}: {issue}" for issue in inspect_python(source))
    load_fixture()
    if issues:
        raise SystemExit("\n".join(issues))
    print("Source audit passed | allowlisted synthetic fixture hash verified")


if __name__ == "__main__":
    main()
