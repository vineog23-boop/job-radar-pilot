"""Isola os testes dos dados reais do usuário.

Sem isto, um teste que não define LOCALAPPDATA leria (ou gravaria) o
tracking/histórico/preferências de verdade em %LOCALAPPDATA%\\JobRadar, e a
exportação automática escreveria em Documentos\\Radar de Vagas.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_user_dirs(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    original_local = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and original_local and "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
        # No Windows o Chromium do Playwright fica em %LOCALAPPDATA%\ms-playwright:
        # trocar o LOCALAPPDATA sem isto faria os testes de navegador não o acharem.
        monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(original_local) / "ms-playwright"))
    base = tmp_path_factory.mktemp("usuario")
    monkeypatch.setenv("LOCALAPPDATA", str(base / "AppData" / "Local"))
    monkeypatch.setenv("JOB_RADAR_EXPORT_DIR", str(base / "Documentos" / "Radar de Vagas"))
