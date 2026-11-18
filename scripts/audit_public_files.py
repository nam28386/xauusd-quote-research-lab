"""Audit candidate repository files without printing matched values."""

import ast
import hashlib
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


FRONTEND_CONFIG = {
    Path("web") / name for name in ("package.json", "package-lock.json", "tsconfig.json")
}
OFFLINE_FIXTURES = {
    Path(
        "fixtures/offline/synthetic-valid/manifest.json"
    ): "45c22cec0cb5de1c9e55876f61fba58319355385edf36cdf568eb80919592750",
    Path(
        "fixtures/offline/synthetic-valid/observations.jsonl"
    ): "f66fdf943d91eb9db08166049f4628fa698143a2129a2f98136de91fb08dd737",
    Path(
        "fixtures/offline/synthetic-invalid/manifest.json"
    ): "f1848b80b78d2fa183aef88a36512824be706f864dbfbbc52fe9f180e5c0efde",
    Path(
        "fixtures/offline/synthetic-invalid/observations.jsonl"
    ): "83df657aaeef1d5cd568b1f91055cd6aee8cc7a7f4373c319a1c4bb973ad300e",
}
LAUNCHERS = {Path("workstation.ps1"), Path("workstation.sh")}


def inspect_python(source: str, *, local_server: bool = False) -> list[str]:
    issues = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        if any(
            name.split(".")[0].lower() in FORBIDDEN_IMPORTS
            and not (
                local_server
                and name == "urllib.parse"
                and isinstance(node, ast.ImportFrom)
                and {alias.name for alias in node.names} <= {"parse_qsl", "urlsplit"}
            )
            for name in names
        ):
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
        web_source = path.parts[:1] == ("web",) and path.suffix in {".ts", ".tsx", ".css", ".html"}
        if (
            not web_source
            and path not in OFFLINE_FIXTURES
            and path not in LAUNCHERS
            and path.suffix.lower()
            not in {
                ".md",
                ".py",
                ".toml",
                ".lock",
                ".yml",
                ".json",
                ".typed",
                "",
            }
        ):
            issues.append(f"{name}: unreviewed file type")
            continue
        if (
            path.suffix == ".json"
            and path != FIXTURE_PATH
            and path not in FRONTEND_CONFIG
            and path not in OFFLINE_FIXTURES
        ):
            issues.append(f"{name}: unreviewed data file")
        if (
            path in OFFLINE_FIXTURES
            and hashlib.sha256(path.read_bytes()).hexdigest() != OFFLINE_FIXTURES[path]
        ):
            issues.append(f"{name}: offline synthetic fixture hash mismatch")
        source = path.read_text(encoding="utf-8")
        if path.name != "audit_public_files.py" and SENSITIVE.search(source):
            issues.append(f"{name}: possible sensitive content")
        if path.suffix == ".py":
            local_server = path == Path("src/xauusd_quote_lab/observatory.py")
            issues.extend(
                f"{name}: {issue}" for issue in inspect_python(source, local_server=local_server)
            )
    load_fixture()
    if issues:
        raise SystemExit("\n".join(issues))
    print("Source audit passed | allowlisted synthetic fixture hash verified")


if __name__ == "__main__":
    main()
