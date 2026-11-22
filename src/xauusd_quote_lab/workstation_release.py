"""Build and validate bounded, reproducible synthetic workstation ZIPs."""

import hashlib
import os
import re
import stat
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .observatory import P2_FILES, P21_FILES, classify, json_bytes, load_dataset
from .observatory_schema import COMMIT, SHA, InvalidArtifact, decode, is_count, matches, require
from .replay import verified_checkout_revision

VERSION = "0.5.0rc1"
SUPPORTED_VERSIONS = ("0.4.0rc1", "0.4.0rc2", VERSION)
MANIFEST_NAME = "release-manifest.json"
SCHEMA = "xauusd-workstation-release-v1"
MAX_TOTAL = 128 * 1024 * 1024
MAX_ENTRY = 96 * 1024 * 1024
MAX_MEMBERS = 512
MAX_MANIFEST = 512 * 1024
SEGMENT = re.compile(r"[a-zA-Z0-9_.-]{1,120}")
ASSET = re.compile(r"(?:app|chunk)-[a-zA-Z0-9]+\.(?:js|css)")
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{name}{n}" for name in ("COM", "LPT") for n in range(1, 10)
}
ROOT_SOURCE = {
    ".gitattributes",
    ".gitignore",
    ".python-version",
    "AGENTS.md",
    "README.md",
    "pyproject.toml",
    "uv.lock",
    "workstation.sh",
    "workstation.ps1",
}
SOURCE_DIRS = {"src", "tests", "scripts", "docs", "fixtures", "web", ".github"}
TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".typed",
    ".toml",
    ".json",
    ".jsonl",
    ".yml",
    ".ts",
    ".tsx",
    ".html",
    ".css",
}


def safe_name(name: str) -> str:
    parts = name.split("/")
    require(
        len(name) <= 240
        and all(
            SEGMENT.fullmatch(part)
            and not part.endswith(".")
            and part.split(".")[0].upper() not in RESERVED
            for part in parts
        ),
        "Unsafe or non-portable release member",
    )
    return name


def approved_source(name: str) -> bool:
    parts = name.split("/")
    return name in ROOT_SOURCE or (
        len(parts) > 1
        and parts[0] in SOURCE_DIRS
        and not {"dist", "node_modules", "__pycache__", ".venv"} & set(parts)
        and all(not part.startswith(".") for part in parts[1:])
        and Path(name).suffix in TEXT_SUFFIXES
    )


def classification(name: str) -> str | None:
    if approved_source(name):
        return "source"
    if name == "web/dist/index.html" or (
        name.startswith("web/dist/assets/")
        and ASSET.fullmatch(name.removeprefix("web/dist/assets/"))
    ):
        return "frontend"
    if name == "examples/p1/evidence.json":
        return "research-evidence"
    parts = name.split("/")
    if len(parts) == 3 and parts[0] == "examples" and parts[1] in ("p2", "p21"):
        if parts[2] == "manifest.json":
            return "research-manifest"
        if parts[2] in (P2_FILES if parts[1] == "p2" else P21_FILES):
            return classify(parts[2])
    return None


def resolution_relationship(path: Path) -> str:
    try:
        resolved = path.resolve(strict=True)
        if resolved == path:
            return "same"
        if resolved == path.parent.resolve(strict=True) / path.name:
            return "ancestor-normalized"
        return "redirected-or-leaf-normalized"
    except (OSError, RuntimeError):
        return "unavailable"


def file_digest(path: Path, *, member: str, max_bytes: int = MAX_ENTRY) -> tuple[str, int]:
    safe_name(member)
    try:
        is_file = path.is_file()
        symlink = path.is_symlink()
        junction = path.is_junction()
        relationship = resolution_relationship(path)
        if not is_file or symlink or junction or relationship != "same":
            raise InvalidArtifact(
                f"Unsafe or missing release file: {member} "
                f"(exists={path.exists()}, file={is_file}, directory={path.is_dir()}, "
                f"symlink={symlink}, junction={junction}, resolution={relationship}, platform={os.name})"
            )
        with path.open("rb") as file:
            return stream_digest(file, max_bytes=max_bytes)
    except (OSError, RuntimeError):
        raise InvalidArtifact(f"Could not inspect or read release file: {member}") from None


def snapshot_root(path: Path) -> Path:
    """Normalize ancestry only at the boundary of a newly created private temp directory."""
    require(
        path.is_dir() and not path.is_symlink() and not path.is_junction(),
        "Unsafe private release snapshot directory",
    )
    resolved = path.resolve(strict=True)
    require(
        resolved == path.parent.resolve(strict=True) / path.name,
        "Private release snapshot directory was redirected",
    )
    if resolved != path:
        print(f"Normalized private release snapshot ancestry (platform={os.name})", flush=True)
    return resolved


def stream_digest(file, *, max_bytes: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    length = 0
    while block := file.read(256 * 1024):
        length += len(block)
        require(length <= max_bytes, "Release file exceeds byte limit")
        digest.update(block)
    return digest.hexdigest(), length


def entry_meta(digest: str, size: int, classification: str) -> dict:
    return {"sha256": digest, "bytes": size, "classification": classification}


def committed_source(root: Path, revision: str) -> dict[str, tuple[Path, dict]]:
    names = (
        subprocess.check_output(
            ["git", "ls-tree", "-r", "-z", "--name-only", revision],
            cwd=root,
        )
        .decode("utf-8")
        .split("\0")
    )
    entries = {}
    for name in filter(None, names):
        safe_name(name)
        require(approved_source(name), f"Unapproved tracked release file: {name}")
        data = subprocess.check_output(["git", "cat-file", "blob", f"{revision}:{name}"], cwd=root)
        path = root / name
        digest, count = file_digest(path, member=name)
        require(
            count == len(data) and digest == hashlib.sha256(data).hexdigest(),
            f"Tracked release source differs from commit: {name}",
        )
        entries[name] = (path, entry_meta(digest, count, "source"))
    return entries


def frontend_files(root: Path) -> dict[str, tuple[Path, dict]]:
    base = root / "web/dist"
    assets = base / "assets"
    index = base / "index.html"
    entries = [index]
    require(assets.is_dir() and assets.resolve() == assets, "Missing built frontend")
    for path in sorted(assets.iterdir()):
        require(ASSET.fullmatch(path.name), "Unexpected frontend build artifact")
        entries.append(path)
    require(len(entries) >= 3, "Incomplete frontend build")
    result = {}
    for path in entries:
        member = path.relative_to(root).as_posix()
        digest, count = file_digest(path, member=member)
        result[member] = (path, entry_meta(digest, count, "frontend"))
    return result


def zip_info(name: str) -> ZipInfo:
    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (0o100755 if name == "workstation.sh" else 0o100644) << 16
    info.compress_type = ZIP_DEFLATED
    return info


def create_release(root: Path, artifact_root: Path, output: Path) -> Path:
    root = root.resolve()
    revision = verified_checkout_revision(root)
    entries = committed_source(root, revision)
    entries.update(frontend_files(root))
    datasets = {}
    with TemporaryDirectory(prefix="workstation-package-") as temp:
        cache = snapshot_root(Path(temp))
        for name in ("p1", "p2", "p21"):
            dataset = load_dataset(name, artifact_root / name, cache / name, None)
            require(
                dataset.code_sha == revision,
                "Release datasets must be prepared at the packaged commit",
            )
            datasets[name] = dataset.metadata()
            for filename in sorted(
                dataset.artifacts.keys() | ({"manifest.json"} if dataset.manifest else set())
            ):
                path = dataset.root / filename
                arcname = f"examples/{name}/{filename}"
                digest, count = file_digest(path, member=arcname)
                classification = dataset.artifacts.get(filename, {}).get(
                    "classification", "research-manifest"
                )
                entries[arcname] = (path, entry_meta(digest, count, classification))
        names = sorted(entries)
        require(
            len(names) < MAX_MEMBERS and len({name.casefold() for name in names}) == len(names),
            "Invalid release inventory",
        )
        manifest = {
            "schema_version": SCHEMA,
            "release_version": VERSION,
            "classification": "SYNTHETIC",
            "code_sha": revision,
            "runtime": {"python": "3.12", "bundled_python": False},
            "distribution": "source-and-prebuilt-web-with-synthetic-examples",
            "datasets": datasets,
            "files": {name: entries[name][1] for name in names},
        }
        payload = json_bytes(manifest)
        require(
            len(payload) <= MAX_MANIFEST
            and sum(m["bytes"] for _, m in entries.values()) + len(payload) <= MAX_TOTAL,
            "Release exceeds total byte limit",
        )
        output.mkdir(parents=True, exist_ok=False)
        archive = output / f"xauusd-quote-lab-{VERSION}.zip"
        with ZipFile(archive, "x", compression=ZIP_DEFLATED, compresslevel=9) as bundle:
            bundle.writestr(zip_info(MANIFEST_NAME), payload, compresslevel=9)
            for name in names:
                path, meta = entries[name]
                content = path.read_bytes()
                require(
                    len(content) == meta["bytes"]
                    and hashlib.sha256(content).hexdigest() == meta["sha256"],
                    "Release input changed during packaging",
                )
                bundle.writestr(zip_info(name), content, compresslevel=9)
        verify_archive(archive)
        (output / MANIFEST_NAME).write_bytes(payload)
        zip_digest, _ = file_digest(archive.resolve(), member=archive.name, max_bytes=MAX_TOTAL)
        (output / "SHA256SUMS").write_text(
            f"{zip_digest}  {archive.name}\n{hashlib.sha256(payload).hexdigest()}  {MANIFEST_NAME}\n",
            encoding="ascii",
            newline="\n",
        )
    return archive


def validate_manifest(payload: bytes) -> dict:
    require(len(payload) <= MAX_MANIFEST, "Oversized release manifest")
    manifest = decode(payload)
    require(
        isinstance(manifest, dict)
        and manifest.get("schema_version") == SCHEMA
        and manifest.get("release_version") in SUPPORTED_VERSIONS
        and manifest.get("classification") == "SYNTHETIC"
        and matches(COMMIT, manifest.get("code_sha")),
        "Unsupported release manifest",
    )
    files = manifest.get("files")
    require(
        isinstance(files, dict) and 0 < len(files) < MAX_MEMBERS, "Invalid release file manifest"
    )
    require(
        len({name.casefold() for name in files}) == len(files), "Ambiguous release member names"
    )
    for name, meta in files.items():
        safe_name(name)
        require(
            name != MANIFEST_NAME
            and isinstance(meta, dict)
            and matches(SHA, meta.get("sha256"))
            and is_count(meta.get("bytes"))
            and meta["bytes"] <= MAX_ENTRY,
            "Invalid member metadata",
        )
        category = classification(name)
        require(
            category is not None and meta.get("classification") == category,
            "Unapproved release member",
        )
    require(
        sum(meta["bytes"] for meta in files.values()) + len(payload) <= MAX_TOTAL,
        "Oversized release",
    )
    return manifest


def check_zip(bundle: ZipFile) -> dict:
    infos = bundle.infolist()
    require(0 < len(infos) <= MAX_MEMBERS, "Unexpected ZIP member count")
    names = {}
    folded = set()
    for info in infos:
        name = safe_name(info.filename)
        require(name.casefold() not in folded, "Duplicate or ambiguous ZIP member")
        folded.add(name.casefold())
        mode = (info.external_attr >> 16) & 0o170000
        require(
            mode in (0, stat.S_IFREG)
            and not info.is_dir()
            and not info.flag_bits & 1
            and info.file_size <= MAX_ENTRY,
            "Unsafe ZIP member type or size",
        )
        names[name] = info
    require(
        MANIFEST_NAME in names and names[MANIFEST_NAME].file_size <= MAX_MANIFEST,
        "Missing or oversized release manifest",
    )
    manifest = validate_manifest(bundle.read(MANIFEST_NAME))
    require(
        names.keys() == {MANIFEST_NAME, *manifest["files"]}, "ZIP inventory does not match manifest"
    )
    for name, meta in manifest["files"].items():
        require(names[name].file_size == meta["bytes"], "ZIP member byte count mismatch")
        with bundle.open(name) as file:
            actual = stream_digest(file, max_bytes=meta["bytes"])
        require(actual == (meta["sha256"], meta["bytes"]), "ZIP member digest mismatch")
    return manifest


def check_archive_digest(stream, independent_sha: str | None):
    digest, _ = stream_digest(stream, max_bytes=MAX_TOTAL)
    if independent_sha is not None:
        require(
            matches(SHA, independent_sha) and digest == independent_sha,
            "Release ZIP digest mismatch",
        )
    stream.seek(0)


def verify_archive(path: Path, independent_sha: str | None = None) -> dict:
    with path.open("rb") as stream:
        check_archive_digest(stream, independent_sha)
        with ZipFile(stream) as bundle:
            return check_zip(bundle)


def verify_installed(root: Path) -> dict:
    root = root.resolve()
    path = root / MANIFEST_NAME
    file_digest(path, member=MANIFEST_NAME, max_bytes=MAX_MANIFEST)
    manifest = validate_manifest(path.read_bytes())
    for name, meta in manifest["files"].items():
        actual = file_digest(root / name, member=name, max_bytes=meta["bytes"])
        require(
            actual == (meta["sha256"], meta["bytes"]), f"Installed release file mismatch: {name}"
        )
    return manifest


def unpack_verified(path: Path, destination: Path, independent_sha: str | None = None) -> None:
    with path.open("rb") as stream:
        check_archive_digest(stream, independent_sha)
        with ZipFile(stream) as bundle:
            check_zip(bundle)
            destination.mkdir(parents=True, exist_ok=False)
            for info in bundle.infolist():
                target = destination / safe_name(info.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as source, target.open("xb") as out:
                    while block := source.read(256 * 1024):
                        out.write(block)
    verify_installed(destination)
