"""Abrir exportações pelo servidor real, sem iniciar apps nativos."""
import json
import os
from pathlib import Path
from threading import Thread
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from job_radar import webapp


@pytest.mark.parametrize("platform,command", [("darwin", "open"), ("linux", "xdg-open"), ("win32", None)])
@pytest.mark.parametrize("fails", [False, True])
def test_open_export_folder_without_shell(monkeypatch, tmp_path, platform, command, fails):
    monkeypatch.setattr(webapp.sys, "platform", platform)
    opener = Mock(side_effect=OSError("sem aplicativo") if fails else None)
    monkeypatch.setattr(webapp.subprocess, "Popen", opener)
    if platform == "win32":
        monkeypatch.setattr(webapp.os, "startfile", opener, raising=False)
    folder = tmp_path / "exportações com espaços; literal"
    monkeypatch.setenv("JOB_RADAR_EXPORT_DIR", str(folder))
    server = webapp.create_server("127.0.0.1", 0,
                                 webapp.SearchController(tmp_path / "output", runner=lambda *_: 0),
                                 tmp_path, preferences_path=tmp_path / "prefs.json")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = Request(f"http://127.0.0.1:{server.server_port}/api/auto-export/open",
                          data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=5) as response:
                status, payload = response.status, json.loads(response.read())
        except HTTPError as error:
            status, payload = error.code, json.loads(error.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
    assert status == (500 if fails else 200)
    assert folder.is_dir()
    if platform == "win32":
        opener.assert_called_once_with(str(folder))
    else:
        opener.assert_called_once_with([command, str(folder)])
    if not fails:
        assert payload == {"folder": str(folder)}


def test_mac_scripts_are_versioned_and_have_valid_bash_syntax():
    import shutil
    import subprocess
    root = Path(__file__).resolve().parents[2]
    scripts = [root / "scripts/setup-mac.sh", root / "Radar de Vagas.command"]
    for script in scripts:
        assert script.is_file()
        if os.name != "nt":
            assert script.stat().st_mode & 0o111
        text = script.read_text(encoding="utf-8")
        assert "3.13" in text
        assert "BASH_SOURCE[0]" in text
        if os.name != "nt" and shutil.which("bash"):
            subprocess.run(["bash", "-n", str(script)], check=True)
