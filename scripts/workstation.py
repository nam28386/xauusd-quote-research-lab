"""Build, prepare, launch or verify the offline research workstation."""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from http.client import HTTPConnection
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from time import monotonic
from zipfile import BadZipFile

ROOT = Path(__file__).resolve().parents[1]
APP = Path(__file__).resolve()
READY = re.compile(r"Synthetic Research Observatory http://127\.0\.0\.1:([0-9]+)")


def checked_tool(name: str) -> str:
    lookup = f"{name}.cmd" if name == "npm" and os.name == "nt" else name
    path = shutil.which(lookup)
    if path is None:
        raise ValueError(f"{name} is missing from PATH. Install it using the workstation guide.")
    version = subprocess.check_output([path, "--version"], text=True).strip()
    if name == "node":
        match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", version)
        if match is None or tuple(map(int, match.groups())) < (22, 18, 0):
            raise ValueError("Node 22.18 or later is required. Node 24 is used in CI.")
    print(f"{name} {version}", flush=True)
    return path


def preflight(*, offline: bool = False, verify: bool = True) -> dict[str, str]:
    if sys.version_info[:2] != (3, 12):
        raise ValueError(
            "Python 3.12 is required. On Windows install Python 3.12 and the py launcher."
        )
    print(f"Python {sys.version.split()[0]}", flush=True)
    if offline:
        if verify:
            from xauusd_quote_lab.workstation_release import verify_installed

            verify_installed(ROOT)
        print("Offline release files verified; no build tools are required.")
        return {}
    return {tool: checked_tool(tool) for tool in ("uv", "node", "npm", "git")}


def call(command: list[str]):
    subprocess.run(command, cwd=ROOT, check=True)


def prepare(uv: str, artifacts: Path):
    call(
        [
            uv,
            "run",
            "--frozen",
            "--extra",
            "dev",
            "python",
            "scripts/start_observatory.py",
            "--artifacts",
            str(artifacts),
            "--prepare-only",
        ]
    )


def build(tools: dict[str, str]):
    call([tools["uv"], "sync", "--frozen", "--extra", "dev"])
    call([tools["uv"], "build"])
    call([tools["npm"], "--prefix", "web", "ci"])
    call([tools["npm"], "--prefix", "web", "run", "build"])


def start(artifacts: Path, port: int, host: str):
    from xauusd_quote_lab.observatory import main as serve
    from xauusd_quote_lab.workstation_release import MANIFEST_NAME, verify_installed

    bundled = (ROOT / MANIFEST_NAME).is_file()
    if bundled:
        verify_installed(ROOT)
    if not (ROOT / "web/dist/index.html").is_file():
        raise ValueError("Compiled frontend missing. Run build or use a verified release ZIP.")
    if not artifacts.is_dir():
        raise ValueError("Synthetic artifacts missing. Run prepare or use the bundled examples.")
    args = ["--host", host, "--port", str(port), "--web", str(ROOT / "web/dist")]
    for family in ("p1", "p2", "p21"):
        args.extend((f"--{family}", str(artifacts / family)))
    if os.name == "nt" and hasattr(signal, "SIGBREAK"):

        def interrupt(_signum, _frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGBREAK, interrupt)
    serve(args)


def read_http(port: int, route: str) -> tuple[str, bytes]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request("GET", route)
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError(f"Local {route} returned HTTP {response.status}")
        budget = 4 * 1024 * 1024
        data = response.read(budget + 1)
        if len(data) > budget:
            raise ValueError("Smoke response exceeded size limit")
        return response.headers["Content-Type"], data
    finally:
        conn.close()


def smoke_checks(port: int):
    _, health = read_http(port, "/api/v1/health")
    checks = json.loads(health)
    if checks != {
        "api_version": "p3-read-v1",
        "classification": "SYNTHETIC",
        "datasets": ["p1", "p2", "p21"],
        "mode": "read-only",
        "status": "ready",
    }:
        raise ValueError("Unexpected health document")
    _, data = read_http(port, "/api/v1/datasets")
    if {item["id"]: item["row_count"] for item in json.loads(data)["datasets"]} != {
        "p1": None,
        "p2": 384,
        "p21": 6912,
    }:
        raise ValueError("Published datasets do not match the synthetic workstation")
    mime, page = read_http(port, "/")
    asset = re.search(rb'src="(/assets/[a-zA-Z0-9_.-]+\.js)"', page)
    if not mime.startswith("text/html") or not asset:
        raise ValueError("Built frontend HTML is incomplete")
    mime, content = read_http(port, asset[1].decode("ascii"))
    if not mime.startswith("text/javascript") or not content:
        raise ValueError("Bundled frontend cannot be served")


def smoke(script: Path, artifacts: Path | None):
    args = [sys.executable, "-I", "-S", str(script), "start", "--port", "0"]
    if artifacts is not None:
        args.extend(("--artifacts", str(artifacts)))
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    with subprocess.Popen(
        args,
        cwd=script.parent.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
    ) as child:
        output: Queue[str | None] = Queue()

        def lines():
            for line in child.stdout:
                output.put(line.strip())
            output.put(None)

        reader = Thread(target=lines, daemon=True)
        reader.start()
        timeout = monotonic() + 45
        line = None
        try:
            while (remaining := timeout - monotonic()) > 0:
                try:
                    line = output.get(timeout=remaining)
                except Empty:
                    line = None
                    break
                if line is None:
                    raise ValueError(f"Workstation exited before readiness (exit {child.poll()})")
                if matched := READY.fullmatch(line):
                    smoke_checks(int(matched[1]))
                    break
                if "Observatory startup:" in line or line.startswith("Workstation:"):
                    raise ValueError(line)
            else:
                line = None
            if not line or not READY.fullmatch(line):
                raise ValueError("Timed out waiting for the loopback server")
        finally:
            if child.poll() is None:
                child.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                    raise ValueError("Workstation did not shut down cleanly") from None
            reader.join(timeout=5)
        if child.returncode != 0:
            raise ValueError(f"Workstation shutdown exited with {child.returncode}")
    print("Smoke passed | health, 3 datasets, HTML and JS, clean shutdown")


def path_value(path: str | None, fallback: Path) -> Path:
    return Path(path).resolve() if path else fallback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight").add_argument("--offline", action="store_true")
    commands.add_parser("build")
    for name in ("prepare", "package", "start", "smoke"):
        command = commands.add_parser(name)
        command.add_argument("--artifacts")
        if name == "package":
            command.add_argument("--output", required=True, type=Path)
        if name == "start":
            command.add_argument("--host", choices=["127.0.0.1"], default="127.0.0.1")
            command.add_argument("--port", default=8765, type=int)
        if name == "smoke":
            command.add_argument("--archive", type=Path)
            command.add_argument("--sha256")
    verifier = commands.add_parser("verify")
    verifier.add_argument("--archive", type=Path)
    verifier.add_argument("--sha256")
    args = parser.parse_args()

    sys.dont_write_bytecode = True
    sys.path.append(str(ROOT / "src"))
    from tempfile import TemporaryDirectory

    from xauusd_quote_lab.workstation_release import (
        MANIFEST_NAME,
        create_release,
        unpack_verified,
        verify_archive,
        verify_installed,
    )

    bundled = (ROOT / MANIFEST_NAME).is_file()
    default = ROOT / ("examples" if bundled else "dist/workstation-data")
    artifacts = path_value(getattr(args, "artifacts", None), default)
    if args.command == "preflight":
        preflight(offline=args.offline or bundled)
    elif args.command == "build":
        build(preflight())
    elif args.command == "prepare":
        prepare(checked_tool("uv"), artifacts)
    elif args.command == "package":
        # Rebuild the frontend from the committed, locked source before shipping its bytes.
        from xauusd_quote_lab.replay import verified_checkout_revision

        verified_checkout_revision(ROOT)
        build(preflight())
        print(create_release(ROOT, artifacts, args.output.resolve()))
    elif args.command == "start":
        start(artifacts, args.port, args.host)
    elif args.command == "verify":
        if not args.archive and args.sha256:
            parser.error("--sha256 requires --archive")
        manifest = (
            verify_archive(args.archive, args.sha256) if args.archive else verify_installed(ROOT)
        )
        print(
            f"Verified {manifest['release_version']} | {manifest['code_sha']} | {len(manifest['files'])} files"
        )
    elif args.command == "smoke":
        if not args.archive and args.sha256:
            parser.error("--sha256 requires --archive")
        if args.archive:
            with TemporaryDirectory(prefix="XAUUSD clean install ") as clean:
                destination = Path(clean) / "Offline Workstation"
                unpack_verified(args.archive, destination, args.sha256)
                script = destination / "scripts/workstation.py"
                subprocess.run(
                    [sys.executable, "-I", "-S", str(script), "preflight", "--offline"],
                    cwd=destination,
                    check=True,
                )
                smoke(script, None)
        else:
            smoke(APP, artifacts)


if __name__ == "__main__":
    try:
        if sys.version_info[:2] != (3, 12):
            raise ValueError("Python 3.12 is required")
        main()
    except (ValueError, OSError, BadZipFile, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Workstation: {exc}") from None
