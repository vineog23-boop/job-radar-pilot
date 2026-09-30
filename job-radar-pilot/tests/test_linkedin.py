from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

import pytest

from job_radar.config import load_profile
from job_radar.linkedin_import import import_into_output, parse_import
from job_radar.manual_search import (
    build_linkedin_search_plan,
    linkedin_search_url,
    location_query,
)
from job_radar.models import WorkplaceModel
from job_radar.preferences import SearchPreferences

PROJECT = Path(__file__).resolve().parents[1]


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        ("brasil", "Brasil"),
        ("remoto-brasil", "Brasil"),
        ("sao-carlos-sp", "Sao Carlos, São Paulo, Brasil"),
        ("santa-catarina", "Santa Catarina, Brasil"),
        ("sc", "Santa Catarina, Brasil"),
        ("portugal", "Portugal"),
    ],
)
def test_location_query(scope: str, expected: str) -> None:
    assert location_query(scope) == expected


def test_search_url_carries_level_workplace_and_recency_filters() -> None:
    url = linkedin_search_url(
        "java backend",
        location="Brasil",
        seniority_levels=("junior",),
        workplace_models=(WorkplaceModel.REMOTE, WorkplaceModel.HYBRID),
        period="day",
    )
    parts = urlsplit(url)
    query = _query(url)
    assert parts.netloc == "www.linkedin.com" and parts.path == "/jobs/search/"
    assert query["keywords"] == ["java backend"]
    assert query["f_E"] == ["2,3"]
    assert query["f_WT"] == ["2,3"]
    assert query["f_TPR"] == ["r86400"]
    assert query["sortBy"] == ["DD"]


def test_search_url_omits_filters_that_would_not_narrow_anything() -> None:
    url = linkedin_search_url(
        "java",
        location="Brasil",
        seniority_levels=("estagio", "junior", "pleno", "senior"),
        workplace_models=(WorkplaceModel.REMOTE, WorkplaceModel.HYBRID, WorkplaceModel.ONSITE),
        period="any",
    )
    query = _query(url)
    assert "f_E" not in query and "f_WT" not in query and "f_TPR" not in query


def test_plan_lists_a_link_per_term_and_location_and_keeps_labels_only_searches() -> None:
    preferences = SearchPreferences(
        search_terms=("java junior", "spring boot"),
        seniority_levels=("junior",),
        workplace_models=(WorkplaceModel.REMOTE,),
        location_scopes=("brasil", "sao-carlos-sp"),
    )
    plan = build_linkedin_search_plan(preferences, period="month")
    assert plan["period"] == "month"
    assert all(set(item) == {"label"} for item in plan["searches"])  # type: ignore[attr-defined]
    links = plan["links"]
    assert [item["term"] for item in links] == ["java junior", "spring boot"]  # type: ignore[index]
    assert len(links[0]["locations"]) == 2  # type: ignore[index]
    assert all(
        loc["url"].startswith("https://www.linkedin.com/jobs/search/")
        for item in links  # type: ignore[union-attr]
        for loc in item["locations"]
    )
    fallback = build_linkedin_search_plan(preferences, period="invalid")
    assert fallback["period"] == "week"


def test_parse_links_derives_title_and_company_from_slug() -> None:
    text = """
    https://www.linkedin.com/jobs/view/desenvolvedor-java-pleno-na-acme-tech-4012345678/?trackingId=abc
    https://br.linkedin.com/jobs/view/java-developer-at-globex-4023456789
    https://www.linkedin.com/jobs/view/4034567890
    https://www.linkedin.com/jobs/search/?currentJobId=4045678901&keywords=java
    https://www.linkedin.com/feed/
    https://example.com/jobs/view/4056789012
    """
    jobs, ignored = parse_import(text)
    assert [job.job_id for job in jobs] == ["4012345678", "4023456789", "4034567890", "4045678901"]
    assert jobs[0].title == "Desenvolvedor Java Pleno" and jobs[0].company == "Acme Tech"
    assert jobs[1].title == "Java Developer" and jobs[1].company == "Globex"
    assert jobs[2].title is None
    assert jobs[0].url == "https://www.linkedin.com/jobs/view/4012345678"
    assert ignored == 1  # /feed/ do LinkedIn; example.com nem conta


def test_parse_alert_email_uses_lines_before_link() -> None:
    text = """
    Engenheiro de Software Java
    Acme Ltda · São Paulo, SP
    Ver vaga: https://www.linkedin.com/comm/jobs/view/4012345678?ref=email
    """
    jobs, _ = parse_import(text)
    assert len(jobs) == 1
    assert jobs[0].title == "Engenheiro de Software Java"
    assert jobs[0].company == "Acme Ltda"
    assert jobs[0].location == "São Paulo, SP"


def test_parse_linkedin_export_csv() -> None:
    text = (
        "Application Date,Contact Email,Company Name,Job Title,Job Url\r\n"
        "09/20/26,a@b.c,Acme,Desenvolvedor Java,https://www.linkedin.com/jobs/view/4012345678/\r\n"
        "09/21/26,a@b.c,Globex,Analista,https://www.linkedin.com/jobs/view/4012345678/\r\n"
        "09/22/26,a@b.c,Initech,Dev Spring,https://www.linkedin.com/jobs/view/4023456789/\r\n"
    )
    jobs, ignored = parse_import(text)
    assert [(j.job_id, j.company) for j in jobs] == [
        ("4012345678", "Acme"),
        ("4023456789", "Initech"),
    ]
    assert ignored == 1  # repetido


def test_import_merges_without_duplicates_and_validates_schema(tmp_path: Path) -> None:
    profile = load_profile(PROJECT / "config" / "profile.yaml")
    text = (
        "https://www.linkedin.com/jobs/view/desenvolvedor-java-junior-na-acme-4012345678\n"
        "https://www.linkedin.com/jobs/view/4023456789\n"
    )
    first = import_into_output(tmp_path, text, profile)
    assert first["added"] == 2 and first["skipped"] == 0
    rows = [json.loads(line) for line in (tmp_path / "vagas.jsonl").read_text("utf-8").splitlines()]
    assert {row["source"] for row in rows} == {"linkedin"}
    assert "IMPORT:MANUAL" in rows[0]["match_labels"]
    assert rows[0]["canonical_url"] == "https://www.linkedin.com/jobs/view/4012345678"

    second = import_into_output(tmp_path, text, profile)
    assert second["added"] == 0
    assert len((tmp_path / "vagas.jsonl").read_text("utf-8").splitlines()) == 2

    # Mesma vaga, agora com título: atualiza a entrada do LinkedIn sem duplicar.
    third = import_into_output(
        tmp_path,
        "Dev Java Pleno\nAcme · Remoto\nhttps://www.linkedin.com/jobs/view/4023456789\n",
        profile,
    )
    assert third["updated"] == 1
    titles = {
        json.loads(line)["title"]
        for line in (tmp_path / "vagas.jsonl").read_text("utf-8").splitlines()
    }
    assert "Dev Java Pleno" in titles


def _serve(tmp_path: Path):
    from job_radar.webapp import SearchController, create_server

    static_dir = PROJECT / "src" / "job_radar" / "web"
    preferences_path = tmp_path / "search-preferences.json"
    preferences_path.write_text(
        json.dumps(
            {
                "search_terms": ["java junior", "spring boot"],
                "seniority_levels": ["junior"],
                "workplace_models": ["REMOTE"],
                "location_scopes": ["brasil"],
            }
        ),
        encoding="utf-8",
    )
    controller = SearchController(tmp_path / "output", runner=lambda *_: 0)
    server = create_server(
        "127.0.0.1", 0, controller, static_dir, preferences_path=preferences_path
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _post(url: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    from urllib.error import HTTPError

    request = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def test_api_import_and_period_plan(tmp_path: Path) -> None:
    server, thread = _serve(tmp_path)
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base}/api/linkedin-searches?period=day", timeout=5) as response:
            plan = json.loads(response.read())
        status, result = _post(
            f"{base}/api/linkedin/import",
            {"text": "https://www.linkedin.com/jobs/view/desenvolvedor-java-na-acme-4012345678"},
        )
        empty_status, _ = _post(f"{base}/api/linkedin/import", {"text": "  "})
        with urlopen(f"{base}/api/state", timeout=5) as response:
            state = json.loads(response.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert plan["period"] == "day"
    assert _query(plan["links"][0]["locations"][0]["url"])["f_TPR"] == ["r86400"]
    assert status == 200 and result["added"] == 1
    assert empty_status == 400
    assert any(job["source"] == "linkedin" for job in state["jobs"])


def test_dashboard_linkedin_panel_links_period_and_import(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    server, thread = _serve(tmp_path)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.get_by_role("button", name="Pesquisar no LinkedIn").click()
            page.wait_for_selector("#linkedin-searches .linkedin-open a")
            opens = page.locator("#linkedin-searches .linkedin-open a")
            assert opens.count() == 2
            href = opens.first.get_attribute("href")
            assert "f_TPR=r604800" in href and "f_WT=2" in href
            assert opens.first.get_attribute("rel") == "noopener noreferrer"

            page.select_option("#linkedin-period", "day")
            page.wait_for_function(
                "(document.querySelector('#linkedin-searches .linkedin-open a')"
                "?.href ?? '').includes('r86400')"
            )

            page.fill(
                "#linkedin-import-text",
                "https://www.linkedin.com/jobs/view/desenvolvedor-java-na-acme-4012345678",
            )
            page.click("#linkedin-import-button")
            page.wait_for_function(
                "document.querySelector('#linkedin-import-status').textContent.includes('1 nova')"
            )
            assert page.locator("#linkedin-import-text").input_value() == ""
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
