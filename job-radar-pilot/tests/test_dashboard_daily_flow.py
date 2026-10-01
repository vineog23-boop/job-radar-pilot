"""Fluxo do dia no painel: novidades, filtros rápidos, desfazer e celular."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from threading import Thread

import pytest

from job_radar.webapp import SearchController, create_server

WEB = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
RECENT = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
OLD = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()


def _job(index: int, title: str, labels: list[str], **extra) -> dict:
    return {
        "title": title,
        "company": f"Empresa {index}",
        "canonical_url": f"https://example.com/vaga/{index}",
        "source": "example",
        "match_labels": labels,
        **extra,
    }


JOBS = [
    _job(1, "Java Júnior Remoto", ["FIT:READY", "FIT_SCORE:4", "STATUS:NEW", "SENIORITY_MATCH:junior", "WORKPLACE_MATCH:REMOTE"], workplace_model="REMOTE", published_at=RECENT),
    _job(2, "Estágio Java Presencial", ["FIT:CONDITIONAL", "FIT_SCORE:2", "STATUS:NEW", "SENIORITY_MATCH:estagio"], workplace_model="ONSITE", published_at=OLD),
    _job(3, "Java Júnior antiga", ["FIT:READY", "FIT_SCORE:3", "SENIORITY_MATCH:junior"], workplace_model="HYBRID", published_at=OLD),
    _job(4, "Python Júnior", ["FIT:OTHER_STACK", "FIT_SCORE:2", "STATUS:NEW"], published_at=RECENT),
]


@pytest.fixture()
def dashboard(tmp_path: Path):
    output = tmp_path / "output"
    output.mkdir()
    (output / "vagas.jsonl").write_text(
        "".join(json.dumps(job, ensure_ascii=False) + "\n" for job in JOBS), encoding="utf-8"
    )
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(output, runner=lambda *_: 0),
        WEB,
        preferences_path=tmp_path / "prefs" / "search-preferences.json",
        tracking_path=tmp_path / "prefs" / "tracking.json",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def _titles(page) -> list[str]:
    return page.locator("#jobs-table-body .job-title").all_inner_texts()


def test_news_banner_shows_and_filters_new_compatible_jobs(dashboard: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(dashboard)
        page.wait_for_selector("#jobs-table-body tr")

        banner = page.locator("#news-banner")
        assert banner.is_visible()
        assert "2 vagas compatíveis novas" in banner.inner_text()

        page.get_by_role("button", name="Ver só as novidades").click()
        assert sorted(_titles(page)) == ["Estágio Java Presencial", "Java Júnior Remoto"]

        page.get_by_role("button", name="Marcar como vistas").click()
        assert banner.is_hidden()
        assert _titles(page) == []  # "Não vistas" ativo e tudo foi visto

        page.reload()
        page.wait_for_selector("#jobs-table-body tr, #empty-state:not([hidden])")
        assert page.locator("#news-banner").is_hidden()  # lembrado no navegador
        browser.close()


def test_quick_filters_combine_and_are_remembered(dashboard: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(dashboard)
        page.wait_for_selector("#jobs-table-body tr")

        page.get_by_role("button", name="Júnior", exact=True).click()
        assert sorted(_titles(page)) == ["Java Júnior Remoto", "Java Júnior antiga"]
        page.get_by_role("button", name="Remoto", exact=True).click()
        assert _titles(page) == ["Java Júnior Remoto"]

        page.reload()
        page.wait_for_selector("#jobs-table-body tr")
        assert _titles(page) == ["Java Júnior Remoto"]
        assert page.get_by_role("button", name="Remoto", exact=True).get_attribute("aria-pressed") == "true"

        page.locator("#clear-filters").click()
        page.get_by_role("button", name="Últimos 7 dias", exact=True).click()
        assert sorted(_titles(page)) == ["Java Júnior Remoto", "Python Júnior"]
        page.get_by_role("button", name="Estágio", exact=True).click()
        assert _titles(page) == []
        browser.close()


def test_discard_can_be_undone(dashboard: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(dashboard)
        page.wait_for_selector("#jobs-table-body tr")

        page.get_by_label("Acompanhamento da vaga Java Júnior Remoto").select_option("DISCARDED")
        toast = page.locator("#toast")
        toast.wait_for(state="visible")
        assert "Descartada" in toast.inner_text()
        assert "Java Júnior Remoto" not in _titles(page)

        page.get_by_role("button", name="Desfazer").click()
        page.wait_for_function(
            "[...document.querySelectorAll('#jobs-table-body .job-title')]"
            ".some((el) => el.textContent.includes('Java Júnior Remoto'))"
        )
        assert toast.is_hidden()
        browser.close()


def test_phone_layout_has_no_horizontal_scroll(dashboard: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(dashboard)
        page.wait_for_selector("#jobs-table-body tr")

        assert page.evaluate("document.documentElement.scrollWidth") <= 390
        page.get_by_role("button", name="Configurar busca").click()
        page.wait_for_timeout(300)
        assert page.evaluate("document.documentElement.scrollWidth") <= 390
        browser.close()
