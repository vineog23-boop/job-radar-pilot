from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

from job_radar.preferences import preferences_from_dict
from job_radar.presets import (
    MAX_SEARCH_TERMS,
    STACKS,
    ROLE_TITLES,
    make_custom_stack,
    recommended_terms,
    suggest,
    term_catalog,
)


def _terms(groups):
    return [item["term"] for group in groups for item in group["terms"]]


def test_every_preset_stack_has_role_titles() -> None:
    assert {stack.id for stack in STACKS} <= set(ROLE_TITLES)


def test_catalog_mixes_roles_levels_and_synonyms_for_java() -> None:
    groups = term_catalog(["java"], ["estagio", "junior"])
    terms = _terms(groups)
    for expected in (
        "java estagio",
        "java junior",
        "desenvolvedor java junior",
        "programador java junior",
        "dev java estagio",
        "spring boot junior",
        "estagiario java",
        "java jr",
        "desenvolvedor java jr",
        "estagio ti",
        "desenvolvedor junior",
    ):
        assert expected in terms, expected
    assert [group["id"] for group in groups] == ["java", "geral"]


def test_recommended_alternates_between_areas_by_priority() -> None:
    groups = term_catalog(["java", "dados"], ["junior"])
    picked = recommended_terms(groups, limit=6)
    # prioridade 1 de cada área vem antes de qualquer cargo
    assert picked[:2] == ["java junior", "analista de dados junior"]
    assert "desenvolvedor java junior" in picked and "engenheiro de dados junior" in picked
    assert len(picked) == len(set(picked)) == 6


def test_non_dev_area_gets_general_it_terms_not_developer_terms() -> None:
    terms = _terms(term_catalog(["infra"], ["junior"]))
    assert "analista de suporte junior" in terms
    assert "analista de ti junior" in terms
    assert "desenvolvedor junior" not in terms


def test_custom_stack_gets_default_roles() -> None:
    custom = (make_custom_stack("Elixir", "elixir, phoenix"),)
    terms = _terms(term_catalog(["custom-elixir"], ["junior"], custom))
    assert {"elixir junior", "desenvolvedor elixir junior", "programador elixir junior"} <= set(terms)


def test_suggest_fills_up_to_twenty_terms_and_preferences_accept_them() -> None:
    result = suggest(["java", "node"], ["estagio", "junior"])
    assert len(result["search_terms"]) == MAX_SEARCH_TERMS == 20
    prefs = preferences_from_dict(
        {
            "search_terms": result["search_terms"],
            "seniority_levels": ["estagio", "junior"],
            "workplace_models": [],
            "location_scopes": ["brasil"],
        }
    )
    assert len(prefs.search_terms) == 20


def _server(tmp_path: Path):
    from job_radar.webapp import SearchController, create_server

    static_dir = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(tmp_path / "output", runner=lambda *_: 0),
        static_dir,
        preferences_path=tmp_path / "search-preferences.json",
        tracking_path=tmp_path / "tracking.json",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}"


def test_api_terms_and_sources_text_search(tmp_path: Path) -> None:
    server, thread, base = _server(tmp_path)
    try:
        with urlopen(f"{base}/api/presets/terms?stacks=java,inexistente&levels=junior,x", timeout=5) as r:
            payload = json.loads(r.read())
        with urlopen(f"{base}/api/sources", timeout=5) as r:
            sources = json.loads(r.read())["sources"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert payload["limit"] == 20
    assert payload["recommended"][0] == "java junior"
    assert [group["id"] for group in payload["groups"]] == ["java", "geral"]
    assert any(source["text_search"] for source in sources)
    assert all("text_search" in source for source in sources)


def test_dashboard_terms_builder(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    server, thread, base = _server(tmp_path)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"{base}/")
            page.get_by_role("button", name="Configurar busca").click()
            page.locator("#stack-chips .chip").first.wait_for()
            page.locator("#seniority-internship").check()
            page.locator("#seniority-junior").check()
            page.locator("#seniority-mid").uncheck()
            page.locator("#seniority-senior").uncheck()
            page.locator('#stack-chips .chip[data-stack="java"]').click()

            page.get_by_role("button", name="✨ Gerar termos da área").click()
            page.locator('#terms-groups .chip[data-term="programador java junior"]').wait_for()
            assert page.locator("#terms-groups .chip.chip-on").count() == 20
            page.get_by_text("20 selecionados (cabem 20)").wait_for()

            # só os que eu quero
            page.get_by_role("button", name="Desmarcar todos").click()
            for term in ("java junior", "desenvolvedor java junior", "estagiario java"):
                page.locator(f'#terms-groups .chip[data-term="{term}"]').click()
            page.get_by_role("button", name="Usar selecionados").click()
            assert page.locator("#search-terms").input_value() == (
                "java junior\ndesenvolvedor java junior\nestagiario java"
            )
            assert page.locator("#search-terms-count").inner_text() == "3/20"
            assert "consultas por busca completa" in page.locator("#terms-estimate").inner_text()

            # somar não duplica
            page.locator('#terms-groups .chip[data-term="java estagio"]').click()
            page.get_by_role("button", name="Somar aos atuais").click()
            assert page.locator("#search-terms").input_value().splitlines()[-1] == "java estagio"
            assert page.locator("#search-terms-count").inner_text() == "4/20"
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
