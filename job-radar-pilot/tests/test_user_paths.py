"""Caminhos nativos sem ler ou gravar dados reais."""
from pathlib import Path

import pytest

from job_radar import adaptive, fetching, history, preferences, tracking
from job_radar import user_paths


@pytest.mark.parametrize("platform", ["darwin", "win32", "linux"])
def test_localappdata_has_priority_on_every_platform(monkeypatch, tmp_path, platform):
    monkeypatch.setattr(user_paths.sys, "platform", platform)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "override"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert user_paths.user_data_dir() == tmp_path / "override" / "JobRadar"


@pytest.mark.parametrize("platform,xdg,relative", [
    ("darwin", None, "Library/Application Support/JobRadar"),
    ("win32", None, "AppData/Local/JobRadar"),
    ("linux", None, ".local/share/job-radar"),
    ("linux", "xdg", "xdg/job-radar"),
    ("linux", "", ".local/share/job-radar"),
])
def test_native_defaults(monkeypatch, tmp_path, platform, xdg, relative):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(user_paths.sys, "platform", platform)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    if xdg is not None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / xdg) if xdg else "")
    root = tmp_path / relative
    assert user_paths.user_data_dir() == root
    assert preferences.preferences_path() == root / "search-preferences.json"
    assert tracking.tracking_path() == root / "tracking.json"
    assert history.history_path() == root / "history.json"
    assert fetching.default_profile_root() == root / "profiles"
    assert adaptive.adaptive_db_path() == root / "adaptive/adaptive.db"
    assert not root.exists()


def test_explicit_file_and_profile_overrides_are_preserved(tmp_path):
    assert history.SeenHistory(tmp_path / "history.json")._path == tmp_path / "history.json"
    assert tracking.TrackingStore(tmp_path / "tracking.json")._path == tmp_path / "tracking.json"
    assert fetching._profile_directory("example", tmp_path / "browser") == tmp_path / "browser/example"
