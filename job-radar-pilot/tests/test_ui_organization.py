from __future__ import annotations

from urllib.request import urlopen

from test_xlsx_export import NOW, _job, _serve
from job_radar.webapp import build_jobs_ai_text


def test_ai_text_is_ranked_markdown_with_escaped_cells() -> None:
    jobs = [
        _job(1, fit="CONDITIONAL", points=2, title="A|B\nC"),
        _job(2, description_summary="ignorada"),
    ]
    text = build_jobs_ai_text(
        jobs,
        {"https://example.com/vaga/2?a=1&b=2": {"status": "APPLIED"}},
        [("Aderência", "Todas")],
        now=NOW,
    ).decode()
    assert text.startswith("# Vagas de TI para revisão")
    rows = [line for line in text.splitlines() if line.startswith("| 1 ") or line.startswith("| 2 ")]
    assert "Dev Java 2 [Aplicada]" in rows[0] and "| 100 |" in rows[0]
    assert "A/B C" in rows[1]
    assert "Aderência: Todas" in text


def test_ai_endpoint(tmp_path) -> None:
    server, thread = _serve(tmp_path)
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/api/export/ai?match=ready", timeout=5) as r:
            body = r.read().decode()
            disposition = r.headers["Content-Disposition"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert "vagas-para-ia.md" in disposition
    assert "Dev Java 1" in body and "Dev Java 2" not in body


def test_dashboard_details_clear_filters_cards_and_memory(tmp_path) -> None:
    from playwright.sync_api import sync_playwright

    server, thread = _serve(tmp_path)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.evaluate("localStorage.removeItem('radar.filters')")
            page.reload()  # filtros de fábrica, inclusive "Últimos 30 dias"
            page.wait_for_selector("#jobs-table-body tr")
            assert page.locator("#jobs-table-body tr").count() == 2
            assert page.locator("#clear-filters").is_hidden()

            # detalhes expansíveis
            page.locator(".title-cell").first.click()
            page.wait_for_selector(".detail-row")
            detail = page.locator(".detail-row").text_content()
            assert "Score" in detail and "/100" in detail and "Java" in detail
            page.locator(".title-cell").first.click()
            assert page.locator(".detail-row").count() == 0

            # card "Compatíveis" filtra e aparece "Limpar filtros"
            page.click("#card-ready")
            page.wait_for_function("document.querySelectorAll('#jobs-table-body tr').length === 1")
            assert page.locator("#match-filter").input_value() == "ready"
            assert page.locator("#clear-filters").is_visible()

            # filtro lembrado após recarregar
            page.reload()
            page.wait_for_selector("#jobs-table-body tr")
            assert page.locator("#match-filter").input_value() == "ready"
            page.click("#clear-filters")
            page.wait_for_function("document.querySelectorAll('#jobs-table-body tr').length === 2")
            assert page.locator("#match-filter").input_value() == ""

            # atalho "/" foca a busca e Esc fecha o painel de exportação
            page.keyboard.press("/")
            assert page.evaluate("document.activeElement.id") == "text-filter"
            page.locator("body").click(position={"x": 5, "y": 5})
            page.get_by_role("button", name="Exportar vagas").click()
            assert page.locator("#export-panel").is_visible()
            page.keyboard.press("Escape")
            assert page.locator("#export-panel").is_hidden()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
