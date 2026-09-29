from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT / "vendor" / "Scrapling"


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(UPSTREAM), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_python_and_scrapling_versions() -> None:
    assert sys.version_info[:2] == (3, 13)
    assert importlib.metadata.version("scrapling") == "0.4.15"
    assert importlib.metadata.version("job-radar-pilot") == "0.1.0"
    assert _git("describe", "--tags", "--exact-match") == "v0.4.15"

    commit = _git("rev-parse", "HEAD")
    assert len(commit) == 40
    assert all(character in "0123456789abcdef" for character in commit)
