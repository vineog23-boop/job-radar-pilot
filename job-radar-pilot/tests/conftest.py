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


_AGE_ANY_SCRIPT = (
    "if (!sessionStorage.getItem('age-any-seeded')) {"
    "sessionStorage.setItem('age-any-seeded', '1');"
    "if (!localStorage.getItem('radar.filters')) "
    "localStorage.setItem('radar.filters', JSON.stringify({age: ''}));}"
)


@pytest.fixture(autouse=True)
def _dashboard_without_age_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """O painel abre em "Últimos 30 dias"; as fixtures antigas não têm data.

    Os testes de navegador começam em "Qualquer data" (salvo se o teste já
    guardou filtros próprios); o filtro de período tem testes dedicados.
    """

    try:
        from playwright.sync_api import Page
    except ImportError:  # pragma: no cover
        return
    original = Page.goto

    def goto(self, url, **kwargs):  # type: ignore[no-untyped-def]
        if not getattr(self, "_age_any_installed", False):
            self.add_init_script(_AGE_ANY_SCRIPT)
            self._age_any_installed = True
        return original(self, url, **kwargs)

    monkeypatch.setattr(Page, "goto", goto)
