"""Isola os testes dos dados reais do usuário.

Sem isto, um teste que não define LOCALAPPDATA leria (ou gravaria) o
tracking/histórico/preferências de verdade em %LOCALAPPDATA%\\JobRadar, e a
exportação automática escreveria em Documentos\\Radar de Vagas.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_user_dirs(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path_factory.mktemp("usuario")
    monkeypatch.setenv("LOCALAPPDATA", str(base / "AppData" / "Local"))
    monkeypatch.setenv("JOB_RADAR_EXPORT_DIR", str(base / "Documentos" / "Radar de Vagas"))
