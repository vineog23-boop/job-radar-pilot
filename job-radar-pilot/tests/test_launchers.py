from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


WORKSPACE = Path(__file__).resolve().parents[2]


def test_cli_launcher_prioritizes_workspace_source_over_existing_pythonpath(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell 7 nao disponivel neste ambiente.")

    shadow_root = tmp_path / "shadow"
    shadow_package = shadow_root / "job_radar"
    shadow_package.mkdir(parents=True)
    (shadow_package / "__init__.py").write_text(
        'raise RuntimeError("PACOTE_EXTERNO_INCORRETO")\n',
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(shadow_root)

    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-File",
            str(WORKSPACE / "scripts" / "run-job-radar.ps1"),
            "--dry-run",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "DRY_RUN" in completed.stdout
    assert "PACOTE_EXTERNO_INCORRETO" not in completed.stdout + completed.stderr


def test_buscar_vagas_propagates_workers_to_collection(tmp_path: Path) -> None:
    powershell = shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell 7 nao disponivel neste ambiente.")

    launcher = tmp_path / "buscar-vagas.ps1"
    shutil.copy2(WORKSPACE / "buscar-vagas.ps1", launcher)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    calls = tmp_path / "calls.txt"
    fake_runner = scripts / "run-job-radar.ps1"
    fake_runner.write_text(
        "Add-Content -LiteralPath $env:JOB_RADAR_TEST_CALLS -Value ($args -join '|')\n"
        "if ($args[0] -ne 'validate-output') {\n"
        "  $outputIndex = [Array]::IndexOf($args, '--output')\n"
        "  $outputDir = $args[$outputIndex + 1]\n"
        "  New-Item -ItemType Directory -Path $outputDir -Force | Out-Null\n"
        "  Set-Content -LiteralPath (Join-Path $outputDir 'vagas.jsonl') -Value ''\n"
        "}\n"
        "exit 0\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["JOB_RADAR_TEST_CALLS"] = str(calls)

    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-File",
            str(launcher),
            "-Workers",
            "3",
            "-Fonte",
            "programathor",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    first_call = calls.read_text(encoding="utf-8").splitlines()[0]
    assert "--workers|3" in first_call


@pytest.mark.parametrize(
    ("launcher", "script"),
    [
        ("Radar de Vagas.cmd", "abrir-interface.ps1"),
        ("Criar atalho na area de trabalho.cmd", "scripts\\criar-atalho.ps1"),
    ],
)
def test_double_click_launchers_call_powershell_without_policy_prompt(
    launcher: str, script: str
) -> None:
    content = (WORKSPACE / launcher).read_bytes()

    assert b"\r\n" in content and b"\n" not in content.replace(b"\r\n", b"")
    text = content.decode("ascii")
    assert "-ExecutionPolicy Bypass" in text
    assert "-NoProfile" in text
    assert f'"%~dp0{script}"' in text
    assert (WORKSPACE / script.replace("\\", "/")).exists()


def test_open_interface_runs_setup_on_first_use(tmp_path: Path) -> None:
    powershell = shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell 7 nao disponivel neste ambiente.")

    launcher = tmp_path / "abrir-interface.ps1"
    shutil.copy2(WORKSPACE / "abrir-interface.ps1", launcher)
    (tmp_path / "job-radar-pilot" / "src").mkdir(parents=True)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    marker = tmp_path / "setup-called.txt"
    (scripts / "setup.ps1").write_text(
        f"Set-Content -LiteralPath '{marker}' -Value 'ok'\nexit 7\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [powershell, "-NoProfile", "-File", str(launcher)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )

    assert marker.exists(), completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert "instala" in (completed.stdout + completed.stderr).casefold()


def test_create_shortcut_writes_desktop_link(tmp_path: Path) -> None:
    powershell = shutil.which("pwsh")
    if powershell is None or os.name != "nt":
        pytest.skip("Atalho .lnk exige Windows com PowerShell 7.")

    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-File",
            str(WORKSPACE / "scripts" / "criar-atalho.ps1"),
            "-Destino",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (tmp_path / "Radar de Vagas.lnk").exists()
