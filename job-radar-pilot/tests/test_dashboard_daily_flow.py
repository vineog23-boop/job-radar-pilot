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


def test_preferences_show_profile_summary_and_collapsed_advanced_filters(dashboard: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(dashboard)
        page.get_by_role("button", name="Configurar busca").click()
        summary = page.locator("#profile-summary")
        page.wait_for_function("document.querySelector('#profile-summary').textContent.length > 0")
        assert summary.inner_text().startswith("Você procura:")

        page.locator("#workplace-remote").check()
        assert "Remoto" in summary.inner_text()

        details = page.locator("#refine-details")
        if details.get_attribute("open") is None:
            page.locator("#refine-details summary").click()
        page.locator("#contract-pj").check()
        assert "ativo" in page.locator("#refine-count").inner_text()
        assert page.locator("#refine-count").inner_text() != "nenhum ativo"
        browser.close()


def test_first_use_empty_state_and_live_progress(tmp_path: Path) -> None:
    from threading import Event

    from playwright.sync_api import sync_playwright

    release = Event()

    def runner(output_dir, sources, workers, on_line):
        on_line("gupy-api: SUCCESS; pages=2; cards=150; records=120; stop=EXHAUSTED")
        release.wait(timeout=20)
        return 0

    controller = SearchController(tmp_path / "output", runner=runner)
    server = create_server("127.0.0.1", 0, controller, WEB)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.locator("#empty-state").wait_for(state="visible")
            assert page.locator("#empty-title").inner_text() == "Ainda não há vagas aqui"
            assert page.locator("#empty-clear").is_hidden()

            controller.start()
            page.wait_for_function(
                "document.querySelector('#live-status').textContent.includes('1 portal concluído')",
                timeout=10000,
            )
            assert "120 vagas lidas" in page.locator("#live-status").inner_text()
            browser.close()
    finally:
        release.set()
        controller.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_detail_quick_actions_save_and_toggle(dashboard: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(dashboard)
        page.wait_for_selector("#jobs-table-body tr")
        page.locator("#jobs-table-body .title-cell", has_text="Java Júnior Remoto").click()

        page.get_by_role("button", name="★ Salvar").click()
        page.wait_for_function(
            "document.querySelector('[aria-label=\"Acompanhamento da vaga Java Júnior Remoto\"]').value === 'SAVED'"
        )
        assert page.get_by_role("button", name="★ Salvar").get_attribute("aria-pressed") == "true"

        page.get_by_role("button", name="★ Salvar").click()  # clicar de novo desfaz
        page.wait_for_function(
            "document.querySelector('[aria-label=\"Acompanhamento da vaga Java Júnior Remoto\"]').value === ''"
        )
        browser.close()


def test_default_period_is_30_days_and_hides_undated_jobs(dashboard: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(dashboard)
        page.evaluate("localStorage.removeItem('radar.filters')")
        page.reload()
        page.wait_for_selector("#age-filter")
        assert page.locator("#age-filter").input_value() == "30"
        within_window = len(_titles(page))
        # "Qualquer data" nunca mostra menos que a janela de 30 dias.
        page.locator("#age-filter").select_option("")
        page.wait_for_selector("#jobs-table-body tr")
        assert len(_titles(page)) >= within_window
        browser.close()
