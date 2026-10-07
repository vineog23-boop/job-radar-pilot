"""Scripts executados em workspace temporário com ferramentas locais controladas."""
import json
import os
import sys
import sysconfig
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
if [[ "$1" == "-" && "$#" -gt 1 ]]; then exec "$REAL_PYTHON" "$@"; fi
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
    executable(tools / "curl", 'echo "$PANEL_IDENTITY"\n')
    monkeypatch.setenv("REAL_PYTHON", sys.executable)
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


@pytest.mark.parametrize("mismatch", [None, "project_root", "venv", "pid", "malformed"])
def test_launcher_checks_occupied_port_and_only_reuses_own_panel(workspace, monkeypatch, mismatch):
    root, python = workspace
    identity = {"pid": 4242, "project_root": str(root / "job-radar-pilot"),
                "venv": str(python.parents[1])}
    if mismatch and mismatch != "malformed":
        identity[mismatch] = 4243 if mismatch == "pid" else "/outro/workspace"
    monkeypatch.setenv("PANEL_IDENTITY", "invalid" if mismatch == "malformed" else json.dumps(identity))
    monkeypatch.setenv("PORT_PROBE", "0")
    monkeypatch.setenv("PANEL_COMMAND", "/Library/Frameworks/Python.framework/Versions/3.13/Resources/Python.app/Contents/MacOS/Python -u -m job_radar.webapp")
    result = run(root, "Radar de Vagas.command")
    assert result.returncode == (0 if mismatch is None else 1), result.stderr
    calls = (root / "calls.log").read_text()
    assert "-u -m job_radar.webapp" not in calls
    assert ("open http://127.0.0.1:8765/" in calls) == (mismatch is None)
    assert "já está aberto" in result.stdout if mismatch is None else "outro processo" in result.stderr


def test_launcher_uses_own_workspace_and_writes_readable_log(workspace, tmp_path):
    root, _ = workspace
    result = run(root, "Radar de Vagas.command")
    assert result.returncode == 0, result.stderr
    assert "-u -m job_radar.webapp" in (root / "calls.log").read_text()
    log = (tmp_path / "dados/JobRadar/logs/interface.log").read_text()
    assert str(root) in log
    assert "Ctrl+C encerra" in log


@pytest.mark.skipif(sys.platform != "darwin", reason="Representação real de processo macOS")
def test_instance_from_exact_venv_survives_macos_executable_representation(tmp_path):
    from urllib.request import urlopen

    python = ROOT / "job-radar-pilot/.venv/bin/python"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "job-radar-pilot/src"),
           "LOCALAPPDATA": str(tmp_path / "data")}
    code = """
from pathlib import Path
from job_radar.webapp import SearchController, create_server
server = create_server('127.0.0.1', 0, SearchController(Path('output')), Path('.'),
                       preferences_path=Path('prefs.json'), tracking_path=Path('tracking.json'))
print(server.server_port, flush=True)
server.serve_forever()
"""
    process = subprocess.Popen([str(python), "-u", "-c", code], cwd=tmp_path,
                               env=env, stdout=subprocess.PIPE, text=True)
    try:
        port = int(process.stdout.readline())
        command = subprocess.check_output(["/bin/ps", "-ww", "-p", str(process.pid),
                                           "-o", "command="], text=True)
        with urlopen(f"http://127.0.0.1:{port}/api/instance", timeout=2) as response:
            identity = json.load(response)
        assert identity == {"pid": process.pid,
                            "venv": str(python.parents[1].resolve()),
                            "project_root": str((ROOT / "job-radar-pilot").resolve())}
        # Builds de framework reescrevem o executável visível em ps.
        if sysconfig.get_config_var("PYTHONFRAMEWORK"):
            assert "Python.app/Contents/MacOS/Python" in command
            assert not command.startswith(str(python))
    finally:
        process.terminate()
        process.wait(timeout=5)
