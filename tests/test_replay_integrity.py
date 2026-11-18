import subprocess
import sys
from pathlib import Path
from shutil import copyfile

from xauusd_quote_lab.synthetic import FIXTURE_PATH


def test_replay_rejects_git_sha_from_unrelated_checkout(tmp_path: Path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    fixture = tmp_path / FIXTURE_PATH
    fixture.parent.mkdir(parents=True)
    copyfile(FIXTURE_PATH, fixture)
    subprocess.run(["git", "add", "--", FIXTURE_PATH.as_posix()], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "Synthetic fixture without research code",
        ],
        cwd=tmp_path,
        check=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "xauusd_quote_lab.replay"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Replay provenance" in result.stderr
    assert result.stdout == ""


def test_replay_uses_fixed_decimal_defaults_in_fresh_process():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import decimal; decimal.DefaultContext.rounding = decimal.ROUND_DOWN; "
            "from xauusd_quote_lab.replay import replay; print(replay('a' * 40).to_json())",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    from xauusd_quote_lab.replay import replay

    assert result.stdout.strip() == replay("a" * 40).to_json()
