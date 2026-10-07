"""Scripts executados em workspace temporário com ferramentas locais controladas."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="Launcher macOS usa Bash/POSIX")
ROOT = Path(__file__).resolve().parents[2]


def executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/bash\nset -eu\n" + text, encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "workspace com espaços"
    root.mkdir()
    (root / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts/setup-mac.sh", root / "scripts/setup-mac.sh")
    shutil.copy2(ROOT / "Radar de Vagas.command", root / "Radar de Vagas.command")
    python = root / "job-radar-pilot/.venv/bin/python"
    executable(python, '''echo "$*" >> "$RECORD"
if [[ "$#" == 1 && "$1" == "-" ]]; then cat >/dev/null; exit "${PORT_PROBE:-1}"; fi
if [[ "$*" == *version_info* ]]; then exit "${WRONG_PYTHON:-0}"; fi
''')
    executable(python.with_name("scrapling"), 'echo "scrapling $*" >> "$RECORD"\n')
    tools = root / "tools"
    tools.mkdir()
    executable(tools / "git", '''case "$*" in
  *remote*) echo https://github.com/D4Vinci/Scrapling.git ;;
  *describe*) echo "${SCRAPLING_TAG:-v0.4.15}" ;;
  *rev-parse*) echo 333fa22b7a5821194ce66b59b11f4b16a6484f02 ;;
  *) exit 7 ;;
esac
''')
    executable(tools / "lsof", 'echo 4242\n')
    executable(tools / "ps", 'echo "$PANEL_COMMAND"\n')
    executable(tools / "open", 'echo "open $*" >> "$RECORD"\n')
    (root / "vendor/Scrapling/.git").mkdir(parents=True)
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "dados"))
    monkeypatch.setenv("JOBRADAR_PYTHON", str(python))
    monkeypatch.setenv("RECORD", str(root / "calls.log"))
    return root, python


def run(root, script):
    return subprocess.run(["/bin/bash", str(root / script)], cwd=root.parent,
                          capture_output=True, text=True, timeout=10)


def test_setup_is_reentrant_and_preserves_existing_user_data(workspace, tmp_path):
    root, _ = workspace
    prefs = tmp_path / "dados/JobRadar/search-preferences.json"
    prefs.parent.mkdir(parents=True)
    prefs.write_text('{"preservar": true}')
    for _ in range(2):
        result = run(root, "scripts/setup-mac.sh")
        assert result.returncode == 0, result.stderr
    assert prefs.read_text() == '{"preservar": true}'
    calls = (root / "calls.log").read_text()
    assert calls.count("-m pip check") == 2
    assert "-m venv" not in calls
    assert "Scrapling v0.4.15" in result.stdout


@pytest.mark.parametrize("variable,value,message", [
    ("WRONG_PYTHON", "1", "exige Python 3.13"),
    ("SCRAPLING_TAG", "v0.4.16", "fixado em v0.4.15"),
])
def test_setup_refuses_wrong_versions(workspace, monkeypatch, variable, value, message):
    root, _ = workspace
    monkeypatch.setenv(variable, value)
    result = run(root, "scripts/setup-mac.sh")
    assert result.returncode != 0
    assert message in result.stderr
    assert "-m pip install" not in (root / "calls.log").read_text()


@pytest.mark.parametrize("own_panel", [False, True])
def test_launcher_checks_occupied_port_and_only_reuses_own_panel(workspace, monkeypatch, own_panel):
    root, python = workspace
    monkeypatch.setenv("PORT_PROBE", "0")
    monkeypatch.setenv("PANEL_COMMAND", f"{python} -u -m job_radar.webapp" if own_panel else "python outra_app.py")
    result = run(root, "Radar de Vagas.command")
    assert result.returncode == (0 if own_panel else 1)
    calls = (root / "calls.log").read_text()
    assert "-u -m job_radar.webapp" not in calls
    assert ("open http://127.0.0.1:8765/" in calls) == own_panel
    assert "já está aberto" in result.stdout if own_panel else "outro processo" in result.stderr


def test_launcher_uses_own_workspace_and_writes_readable_log(workspace, tmp_path):
    root, _ = workspace
    result = run(root, "Radar de Vagas.command")
    assert result.returncode == 0, result.stderr
    assert "-u -m job_radar.webapp" in (root / "calls.log").read_text()
    log = (tmp_path / "dados/JobRadar/logs/interface.log").read_text()
    assert str(root) in log
    assert "Ctrl+C encerra" in log
