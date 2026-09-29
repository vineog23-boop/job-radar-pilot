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
