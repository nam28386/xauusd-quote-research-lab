import hashlib
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from xauusd_quote_lab.observatory import Observatory, json_bytes
from xauusd_quote_lab.observatory_schema import InvalidArtifact
from xauusd_quote_lab.workstation_release import (
    MANIFEST_NAME,
    SCHEMA,
    VERSION,
    entry_meta,
    safe_name,
    unpack_verified,
    verify_archive,
    verify_installed,
    zip_info,
)


def make_bundle(path, *, file="README.md", content=b"approved", expected=b"approved", mode=None):
    m = {
        "schema_version": SCHEMA,
        "release_version": VERSION,
        "classification": "SYNTHETIC",
        "code_sha": "a" * 40,
        "files": {file: entry_meta(hashlib.sha256(expected).hexdigest(), len(expected), "source")},
    }
    with ZipFile(path, "x") as bundle:
        bundle.writestr(zip_info(MANIFEST_NAME), json_bytes(m))
        info = zip_info(file)
        if mode is not None:
            info.external_attr = mode << 16
        bundle.writestr(info, content)


def test_zip_round_trip_and_independent_digest(tmp_path):
    archive = tmp_path / "test.zip"
    make_bundle(archive)
    pin = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert verify_archive(archive, pin)["release_version"] == VERSION
    with pytest.raises(InvalidArtifact, match="ZIP digest mismatch"):
        verify_archive(archive, "0" * 64)
    root = tmp_path / "Clean offline path"
    unpack_verified(archive, root, pin)
    assert (root / "README.md").read_bytes() == b"approved"
    assert verify_installed(root)["code_sha"] == "a" * 40
    (root / "README.md").write_bytes(b"changed!")
    with pytest.raises(InvalidArtifact, match="mismatch"):
        verify_installed(root)


@pytest.mark.parametrize(
    "filename",
    [
        "../../unsafe",
        "/absolute",
        "C:/drive",
        "docs/NUL.txt",
        "foo/..",
        "foo\\x",
        "foo/alternate:stream",
        "docs/ending.",
    ],
)
def test_zip_names_are_portable_and_cannot_escape(filename):
    with pytest.raises(InvalidArtifact, match="Unsafe"):
        safe_name(filename)


def test_zip_rejects_symlink_members_and_changed_bytes(tmp_path):
    link = tmp_path / "link.zip"
    make_bundle(link, mode=0o120777)
    with pytest.raises(InvalidArtifact, match="member type"):
        verify_archive(link)
    broken = tmp_path / "broken.zip"
    make_bundle(broken, content=b"changed!")
    with pytest.raises(InvalidArtifact, match="member digest mismatch"):
        verify_archive(broken)
    forbidden = tmp_path / "unapproved.zip"
    make_bundle(forbidden, file="tool.exe")
    with pytest.raises(InvalidArtifact, match="Unapproved"):
        verify_archive(forbidden)


def test_case_collisions_rejected_before_extract(tmp_path):
    archive = tmp_path / "ambiguous.zip"
    make_bundle(archive)
    with ZipFile(archive, "a") as bundle:
        bundle.writestr(zip_info("readme.md"), "also here")
    with pytest.raises(InvalidArtifact, match="ambiguous"):
        unpack_verified(archive, tmp_path / "unpacked")
    assert not (tmp_path / "unpacked").exists()


def test_linux_or_windows_launcher_rejects_non_loopback_before_start():
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(Path("scripts/workstation.py").resolve()),
            "start",
            "--host",
            "0.0.0.0",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "127.0.0.1" in result.stderr


def test_local_health_has_no_paths_or_credential_information():
    body, mime, _ = Observatory({"p1": None, "p2": None, "p21": None}).dispatch(
        "/api/v1/health", {}
    )
    assert json.loads(body) == {
        "api_version": "p3-read-v1",
        "classification": "SYNTHETIC",
        "datasets": ["p1", "p2", "p21"],
        "mode": "read-only",
        "status": "ready",
    }
    assert mime == "application/json"
