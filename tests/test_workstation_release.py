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


def make_bundle(
    path, *, file="README.md", content=b"approved", expected=b"approved", mode=None, version=VERSION
):
    m = {
        "schema_version": SCHEMA,
        "release_version": version,
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


def directory_alias(link: Path, target: Path) -> None:
    if sys.platform == "win32":
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
        )
        assert result.returncode == 0, "Could not create temporary test junction"
        assert link.is_junction()
    else:
        link.symlink_to(target, target_is_directory=True)


def test_snapshot_normalizes_temp_ancestry_only(tmp_path):
    from xauusd_quote_lab.workstation_release import file_digest, snapshot_root

    root = tmp_path.resolve()
    actual = root / "Canonical Temp"
    actual.mkdir()
    alias = root / "Alias"
    directory_alias(alias, actual)
    temp = alias / "workstation-package-fixture"
    temp.mkdir()
    file = temp / "evidence.json"
    file.write_bytes(b"synthetic")
    member = "examples/p1/evidence.json"
    assert file.is_file() and not file.is_symlink() and file.resolve() != file
    with pytest.raises(InvalidArtifact, match="ancestor-normalized") as error:
        file_digest(file, member=member)
    assert member in str(error.value)
    assert str(root) not in str(error.value)
    canonical = snapshot_root(temp)
    assert canonical == actual / temp.name
    assert file_digest(canonical / file.name, member=member) == (
        hashlib.sha256(b"synthetic").hexdigest(),
        9,
    )


def test_snapshot_leaf_and_descendant_redirects_are_rejected(tmp_path):
    from xauusd_quote_lab.workstation_release import file_digest, snapshot_root

    root = tmp_path.resolve()
    outside = root / "Outside"
    outside.mkdir()
    (outside / "evidence.json").write_bytes(b"synthetic")
    cache = root / "Snapshot"
    cache.mkdir()
    redirected = cache / "p1"
    directory_alias(redirected, outside)
    with pytest.raises(InvalidArtifact, match="Unsafe private release snapshot directory"):
        snapshot_root(redirected)
    with pytest.raises(InvalidArtifact, match="ancestor-normalized"):
        file_digest(redirected / "evidence.json", member="examples/p1/evidence.json")


def test_missing_and_directory_diagnostics_are_safe(tmp_path):
    from xauusd_quote_lab.workstation_release import file_digest

    root = tmp_path.resolve()
    directory = root / "not-a-file"
    directory.mkdir()
    for path, fields in (
        (root / "missing", "exists=False, file=False, directory=False"),
        (directory, "exists=True, file=False, directory=True"),
    ):
        with pytest.raises(InvalidArtifact, match=fields) as error:
            file_digest(path, member="examples/p1/evidence.json")
        assert str(root) not in str(error.value)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native short path API")
def test_windows_short_temp_ancestry_when_available(tmp_path):
    import ctypes

    from xauusd_quote_lab.workstation_release import file_digest, snapshot_root

    root = tmp_path.resolve()
    long = root / "Temporary Folder With Long Name"
    long.mkdir()
    short_name = ctypes.create_unicode_buffer(32768)
    result = ctypes.windll.kernel32.GetShortPathNameW(str(long), short_name, len(short_name))
    assert 0 < result < len(short_name), "Could not query Windows path spelling"
    short = Path(short_name.value)
    if short == long:
        pytest.skip("Temporary volume does not assign a distinct short path")
    temp = short / "workstation-package-fixture"
    temp.mkdir()
    whole = snapshot_root(temp)
    assert whole == long / temp.name
    sample = whole / "evidence.json"
    sample.write_bytes(b"fixture")
    assert file_digest(sample, member="examples/p1/evidence.json")[1] == 7


@pytest.mark.parametrize("version", ["0.4.0rc1", "0.4.0rc2"])
def test_historical_manifest_remains_readable(tmp_path, version):
    archive = tmp_path / f"{version}.zip"
    make_bundle(archive, version=version)
    assert verify_archive(archive)["release_version"] == version


def test_rc3_distribution_gate_binds_sidecars_and_candidate_sha(tmp_path):
    root = tmp_path / "release"
    root.mkdir()
    archive_name = "xauusd-quote-lab-0.4.0rc3.zip"
    file = b"approved"
    manifest = {
        "schema_version": SCHEMA,
        "release_version": "0.4.0rc3",
        "classification": "SYNTHETIC",
        "code_sha": "a" * 40,
        "datasets": {"p1": {}, "p2": {}, "p21": {}},
        "files": {"README.md": entry_meta(hashlib.sha256(file).hexdigest(), len(file), "source")},
    }
    payload = json_bytes(manifest)
    archive = root / archive_name
    with ZipFile(archive, "x") as bundle:
        bundle.writestr(zip_info(MANIFEST_NAME), payload)
        bundle.writestr(zip_info("README.md"), file)

    def set_sidecar(value):
        (root / MANIFEST_NAME).write_bytes(value)
        (root / "SHA256SUMS").write_text(
            f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive_name}\n"
            f"{hashlib.sha256(value).hexdigest()}  {MANIFEST_NAME}\n",
            encoding="ascii",
        )

    def check(sha):
        return subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "scripts/release_gate.py",
                "bundle",
                "--sha",
                sha,
                "--directory",
                str(root),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    set_sidecar(payload)
    result = check("a" * 40)
    assert result.returncode == 0, result.stderr
    assert "Distribution code SHA differs" in check("b" * 40).stderr
    set_sidecar(json_bytes({**manifest, "code_sha": "b" * 40}))
    assert "External and embedded manifests differ" in check("a" * 40).stderr
