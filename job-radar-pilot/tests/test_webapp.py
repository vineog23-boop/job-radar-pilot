from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
import sys
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class _ElementIdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs) -> None:
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.add(attributes["id"])


def test_parse_progress_line_extracts_source_result() -> None:
    from job_radar.webapp import parse_progress_line

    result = parse_progress_line(
        "programathor: PARTIAL; pages=1; cards=16; records=12; "
        "stop=PAGINATION_UNVERIFIED"
    )

    assert result == {
        "source": "programathor",
        "status": "PARTIAL",
        "pages": 1,
        "cards": 16,
        "records": 12,
        "stop_reason": "PAGINATION_UNVERIFIED",
    }


def test_parse_progress_line_ignores_regular_log() -> None:
    from job_radar.webapp import parse_progress_line

    assert parse_progress_line("INFO: Fetched (200) <GET https://example.com>") is None


def test_parse_progress_line_ignores_source_warning() -> None:
    from job_radar.webapp import parse_progress_line

    assert parse_progress_line(
        "WARNING programathor: SELECTOR_RELOCATED:card"
    ) is None


def test_load_output_returns_jobs_and_report(tmp_path) -> None:
    from job_radar.webapp import load_output

    output = tmp_path / "output"
    output.mkdir()
    job = {
        "title": "Pessoa Desenvolvedora Java Junior",
        "company": "Empresa Exemplo",
        "canonical_url": "https://example.com/vagas/123",
        "source": "example",
        "match_labels": ["TECH_MATCH:java"],
    }
    (output / "vagas.jsonl").write_text(
        json.dumps(job, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report = {
        "finished_at": "2026-09-29T04:00:00+00:00",
        "totals": {"raw": 1, "unique": 1},
        "sources": [{"source": "example", "status": "SUCCESS", "records": 1}],
    }
    (output / "relatorio-execucao.json").write_text(
        json.dumps(report), encoding="utf-8"
    )

    result = load_output(output)

    assert result["jobs"] == [job]
    assert result["report"] == report
    assert result["read_error"] is None


def test_search_controller_runs_once_and_tracks_source_progress(tmp_path) -> None:
    from job_radar.webapp import SearchController

    release = Event()
    emitted = Event()

    def runner(output_dir, sources, workers, on_line):
        assert output_dir == tmp_path
        assert sources == ["programathor"]
        assert workers == 3
        on_line(
            "programathor: PARTIAL; pages=1; cards=16; records=12; "
            "stop=PAGINATION_UNVERIFIED"
        )
        emitted.set()
        release.wait(timeout=2)
        return 3

    controller = SearchController(tmp_path, runner=runner, workers=3)

    assert controller.start(["programathor"]) is True
    assert emitted.wait(timeout=2) is True
    assert controller.start(["programathor"]) is False
    running = controller.snapshot()
    assert running["status"] == "RUNNING"
    assert running["sources"]["programathor"]["records"] == 12

    release.set()
    assert controller.wait(timeout=2) is True

    finished = controller.snapshot()
    assert finished["status"] == "PARTIAL"
    assert finished["exit_code"] == 3


def test_stream_process_forwards_lines_and_returns_exit_code() -> None:
    from job_radar.webapp import stream_process

    lines: list[str] = []
    command = [
        sys.executable,
        "-c",
        "print('programathor: SUCCESS; pages=1; cards=2; records=2; stop=EXHAUSTED')",
    ]

    exit_code = stream_process(command, lines.append)

    assert exit_code == 0
    assert lines == [
        "programathor: SUCCESS; pages=1; cards=2; records=2; stop=EXHAUSTED"
    ]


def test_build_collection_command_includes_selected_sources(tmp_path) -> None:
    from job_radar.webapp import build_collection_command

    command = build_collection_command(
        tmp_path / "output",
        ["programathor", "companhia-de-estagios"],
        workers=3,
        executable=Path("python.exe"),
    )

    assert command == [
        "python.exe",
        "-m",
        "job_radar.cli",
        "collect",
        "--output",
        str(tmp_path / "output"),
        "--workers",
        "3",
        "--source",
        "programathor",
        "--source",
        "companhia-de-estagios",
    ]


def test_http_server_serves_dashboard_and_state_api(tmp_path) -> None:
    from job_radar.webapp import SearchController, create_server

    static_dir = tmp_path / "web"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        "<!doctype html><title>Radar de vagas</title>", encoding="utf-8"
    )
    controller = SearchController(tmp_path / "output", runner=lambda *_: 0)
    server = create_server("127.0.0.1", 0, controller, static_dir)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with urlopen(f"{base_url}/", timeout=2) as response:
            page = response.read().decode("utf-8")
        with urlopen(f"{base_url}/api/state", timeout=2) as response:
            state = json.loads(response.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert "Radar de vagas" in page
    assert state["status"] == "IDLE"
    assert state["jobs"] == []


def test_export_api_downloads_markdown_from_fixed_output(tmp_path) -> None:
    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    output.mkdir()
    (output / "vagas.jsonl").write_text(
        "".join(
            json.dumps(job) + "\n"
            for job in [
                {
                "title": "Desenvolvedor Java Junior",
                "company": "Acme",
                "location": "Remoto",
                "source": "gupy",
                "canonical_url": "https://example.com/vaga/1",
                "match_labels": ["FIT:READY"],
                },
                {
                    "title": "Analista Python Senior",
                    "company": "Beta",
                    "location": "Sao Paulo",
                    "source": "indeed",
                    "canonical_url": "https://example.com/vaga/2",
                    "match_labels": ["FIT:EXCLUDE"],
                },
            ]
        ),
        encoding="utf-8",
    )
    (output / "relatorio-execucao.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source": "gupy",
                        "status": "PARTIAL",
                        "stop_reason": "PAGINATION_UNVERIFIED",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    static_dir = tmp_path / "web"
    static_dir.mkdir()
    controller = SearchController(output, runner=lambda *_: 0)
    server = create_server("127.0.0.1", 0, controller, static_dir)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with urlopen(
            f"http://127.0.0.1:{server.server_port}/api/export/markdown?text=java&source=gupy&match=ready",
            timeout=2,
        ) as response:
            status = response.status
            disposition = response.headers["Content-Disposition"]
            content_type = response.headers["Content-Type"]
            document = response.read().decode("utf-8-sig")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 200
    assert disposition == 'attachment; filename="relatorio-vagas.md"'
    assert content_type == "text/markdown; charset=utf-8"
    assert "## Mais compativeis (1)" in document
    assert "Desenvolvedor Java Junior" in document
    assert "Analista Python Senior" not in document
    assert "Filtros aplicados:" in document
    assert "gupy: PARTIAL" in document


def test_export_api_rejects_corrupt_local_output_instead_of_returning_empty_report(tmp_path) -> None:
    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    output.mkdir()
    (output / "vagas.jsonl").write_text('{"title":"Java Junior"}\n', encoding="utf-8")
    (output / "relatorio-execucao.json").write_text("{invalid", encoding="utf-8")
    static_dir = tmp_path / "web"
    static_dir.mkdir()
    server = create_server(
        "127.0.0.1", 0, SearchController(output, runner=lambda *_: 0), static_dir
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        try:
            urlopen(
                f"http://127.0.0.1:{server.server_port}/api/export/markdown",
                timeout=2,
            )
        except HTTPError as exc:
            status = exc.code
            payload = json.loads(exc.read())
        else:
            raise AssertionError("Saida corrompida nao pode gerar download")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 500
    assert "error" in payload
    assert "Total: 0 vagas" not in json.dumps(payload)


def test_search_api_starts_collection_and_rejects_duplicate(tmp_path) -> None:
    from job_radar.webapp import SearchController, create_server

    release = Event()
    received_sources: list[list[str] | None] = []

    def runner(output_dir, sources, workers, on_line):
        assert workers == 1
        received_sources.append(sources)
        release.wait(timeout=2)
        return 0

    static_dir = tmp_path / "web"
    static_dir.mkdir()
    controller = SearchController(tmp_path / "output", runner=runner)
    server = create_server("127.0.0.1", 0, controller, static_dir)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}/api/search"
    body = json.dumps({"sources": ["programathor"]}).encode("utf-8")

    try:
        request = Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            accepted = json.loads(response.read())
            accepted_status = response.status

        duplicate = Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urlopen(duplicate, timeout=2)
            duplicate_status = 200
        except HTTPError as exc:
            duplicate_status = exc.code
    finally:
        release.set()
        controller.wait(timeout=2)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert accepted_status == 202
    assert accepted == {"accepted": True}
    assert duplicate_status == 409
    assert received_sources == [["programathor"]]


def test_preferences_api_saves_validated_search_configuration(tmp_path) -> None:
    from job_radar.webapp import SearchController, create_server

    static_dir = tmp_path / "web"
    static_dir.mkdir()
    preferences_path = tmp_path / "search-preferences.json"
    controller = SearchController(tmp_path / "output", runner=lambda *_: 0)
    server = create_server(
        "127.0.0.1",
        0,
        controller,
        static_dir,
        preferences_path=preferences_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}/api/preferences"
    payload = {
        "search_terms": ["java junior", "estagio backend"],
        "seniority_levels": ["estagio", "junior"],
        "workplace_models": ["REMOTE", "HYBRID"],
        "location_scopes": ["sao-carlos-sp", "florianopolis-sc"],
        "technologies": ["java", "spring boot"],
        "excluded_terms": ["pleno"],
    }

    try:
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urlopen(request, timeout=2) as response:
            saved = json.loads(response.read())
            saved_status = response.status
        with urlopen(endpoint, timeout=2) as response:
            loaded = json.loads(response.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert saved_status == 200
    assert {key: saved[key] for key in payload} == payload
    assert {key: loaded[key] for key in payload} == payload
    # refinos opcionais voltam com os valores neutros
    assert loaded["required_keywords"] == [] and loaded["contract_types"] == []
    assert loaded["avoid_advanced_english"] is False
    assert preferences_path.exists()


def test_preferences_api_rejects_unknown_fields_without_overwriting(tmp_path) -> None:
    from job_radar.webapp import SearchController, create_server

    static_dir = tmp_path / "web"
    static_dir.mkdir()
    preferences_path = tmp_path / "search-preferences.json"
    controller = SearchController(tmp_path / "output", runner=lambda *_: 0)
    server = create_server(
        "127.0.0.1",
        0,
        controller,
        static_dir,
        preferences_path=preferences_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}/api/preferences"
    invalid = {
        "search_terms": ["java"],
        "seniority_levels": ["junior"],
        "workplace_models": ["REMOTE"],
        "location_scopes": ["brasil"],
        "output_path": "C:/fora-do-radar",
    }

    try:
        request = Request(
            endpoint,
            data=json.dumps(invalid).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        try:
            urlopen(request, timeout=2)
            status = 200
        except HTTPError as exc:
            status = exc.code
            error = json.loads(exc.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 400
    assert "error" in error
    assert preferences_path.exists() is False


def test_preferences_api_rejects_body_over_16kb(tmp_path) -> None:
    from job_radar.webapp import SearchController, create_server

    static_dir = tmp_path / "web"
    static_dir.mkdir()
    controller = SearchController(tmp_path / "output", runner=lambda *_: 0)
    server = create_server(
        "127.0.0.1",
        0,
        controller,
        static_dir,
        preferences_path=tmp_path / "search-preferences.json",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}/api/preferences"
    oversized = json.dumps({"search_terms": ["x" * 16_384]}).encode("utf-8")

    try:
        request = Request(
            endpoint,
            data=oversized,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        try:
            urlopen(request, timeout=2)
            status = 200
        except HTTPError as exc:
            status = exc.code
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 400


def test_linkedin_api_returns_manual_plan_without_starting_collection(tmp_path) -> None:
    from job_radar.webapp import SearchController, create_server

    searches: list[list[str] | None] = []

    def runner(output_dir, sources, workers, on_line):
        assert workers == 1
        searches.append(sources)
        return 0

    static_dir = tmp_path / "web"
    static_dir.mkdir()
    preferences_path = tmp_path / "search-preferences.json"
    preferences_path.write_text(
        json.dumps(
            {
                "search_terms": ["java junior", "estagio backend"],
                "seniority_levels": ["estagio", "junior"],
                "workplace_models": ["REMOTE"],
                "location_scopes": ["remoto-brasil", "florianopolis-sc"],
            }
        ),
        encoding="utf-8",
    )
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(tmp_path / "output", runner=runner),
        static_dir,
        preferences_path=preferences_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with urlopen(
            f"http://127.0.0.1:{server.server_port}/api/linkedin-searches",
            timeout=2,
        ) as response:
            payload = json.loads(response.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert payload["access_mode"] == "MANUAL_FOREGROUND"
    assert payload["network_access"] is False
    assert len(payload["searches"]) == 2
    assert payload["home_url"] == "https://www.linkedin.com/"
    assert all(set(item) == {"label"} for item in payload["searches"])
    assert searches == []


def test_project_dashboard_exposes_expected_controls(tmp_path) -> None:
    from job_radar.webapp import SearchController, create_server

    project = Path(__file__).resolve().parents[1]
    static_dir = project / "src" / "job_radar" / "web"
    controller = SearchController(tmp_path / "output", runner=lambda *_: 0)
    server = create_server("127.0.0.1", 0, controller, static_dir)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with urlopen(f"{base_url}/", timeout=2) as response:
            html = response.read().decode("utf-8")
        with urlopen(f"{base_url}/styles.css", timeout=2) as response:
            assert response.status == 200
        with urlopen(f"{base_url}/app.js", timeout=2) as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    parser = _ElementIdCollector()
    parser.feed(html)
    assert {
        "search-button",
        "preferences-button",
        "preferences-panel",
        "linkedin-button",
        "linkedin-panel",
        "linkedin-searches",
        "download-report",
        "text-filter",
        "source-filter",
        "match-filter",
        "summary-cards",
        "source-statuses",
        "jobs-table-body",
        "live-status",
    }.issubset(parser.ids)


def test_dashboard_lists_manual_linkedin_searches_without_starting_collection(
    tmp_path,
) -> None:
    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    searches: list[list[str] | None] = []

    def runner(output_dir, sources, workers, on_line):
        assert workers == 1
        searches.append(sources)
        return 0

    output = tmp_path / "output"
    static_dir = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
    preferences_path = tmp_path / "search-preferences.json"
    preferences_path.write_text(
        json.dumps(
            {
                "search_terms": ["java junior", "estagio backend"],
                "seniority_levels": ["estagio", "junior"],
                "workplace_models": ["REMOTE"],
                "location_scopes": ["remoto-brasil", "florianopolis-sc"],
            }
        ),
        encoding="utf-8",
    )
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(output, runner=runner),
        static_dir,
        preferences_path=preferences_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            with page.expect_response(
                lambda response: response.url.endswith("/api/linkedin-searches")
            ) as response_info:
                page.get_by_role("button", name="Pesquisar no LinkedIn").click()
            assert response_info.value.status == 200
            assert page.locator("#linkedin-panel").is_visible() is True
            terms = page.locator("#linkedin-searches button")
            assert terms.count() == 2
            assert terms.first.text_content() == "Copiar"
            home = page.locator("#linkedin-home-link")
            assert home.get_attribute("href") == "https://www.linkedin.com/"
            assert home.get_attribute("target") == "_blank"
            assert home.get_attribute("rel") == "noopener noreferrer"
            assert searches == []
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_dashboard_saves_preferences_without_starting_search(tmp_path) -> None:
    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    searches: list[list[str] | None] = []

    def runner(output_dir, sources, workers, on_line):
        assert workers == 1
        searches.append(sources)
        return 0

    output = tmp_path / "output"
    static_dir = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
    preferences_path = tmp_path / "search-preferences.json"
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(output, runner=runner),
        static_dir,
        preferences_path=preferences_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.get_by_role("button", name="Configurar busca").click()
            assert page.locator("#preferences-panel").is_visible() is True

            page.locator("#search-terms").fill("java junior\nestagio backend")
            page.locator("#seniority-internship").check()
            page.locator("#seniority-junior").check()
            page.locator("#workplace-remote").check()
            page.locator("#workplace-hybrid").check()
            page.locator("#workplace-onsite").uncheck()
            page.locator("#location-scopes").fill(
                "sao-carlos-sp\nflorianopolis-sc"
            )
            # campos de etiquetas: limpa o padrão (Backspace) e digita com Enter
            for field, values in (
                ("technologies", ["Java", "Spring Boot"]),
                ("excluded-terms", ["Pleno", "Sênior"]),
            ):
                entry = page.locator(f"#{field}-entry")
                entry.click()
                while page.locator(f"#{field}").input_value():
                    entry.press("Backspace")
                for value in values:
                    entry.fill(value)
                    entry.press("Enter")
            with page.expect_response(
                lambda response: response.url.split("?")[0].endswith("/api/preferences")
                and response.request.method == "PUT"
            ) as response_info:
                page.get_by_role("button", name="Salvar configurações").click()
            assert response_info.value.status == 200
            page.get_by_text("Configurações salvas").wait_for()
            assert searches == []

            page.locator("#seniority-internship").uncheck()
            page.locator("#seniority-junior").uncheck()
            page.get_by_role("button", name="Salvar configurações").click()
            page.get_by_text("Selecione ao menos um nível.").wait_for()

            page.locator("#seniority-junior").check()
            page.locator("#location-scopes").fill("")
            page.get_by_role("button", name="Salvar configurações").click()
            page.get_by_text("Informe ao menos uma localidade.").wait_for()
            assert searches == []

            page.get_by_role("button", name="Buscar vagas agora").click()
            page.wait_for_function("() => document.querySelector('#search-button').disabled === false")
            assert searches == [None]
            assert page.locator("#download-report").get_attribute("href") == (
                "/api/export/markdown?tracked=active"
            )
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    saved = json.loads(preferences_path.read_text(encoding="utf-8"))
    expected = {
        "search_terms": ["java junior", "estagio backend"],
        "seniority_levels": ["estagio", "junior"],
        "workplace_models": ["REMOTE", "HYBRID"],
        "location_scopes": ["sao-carlos-sp", "florianopolis-sc"],
        "technologies": ["java", "spring boot"],
        "excluded_terms": ["pleno", "sênior"],
    }
    assert {key: saved[key] for key in expected} == expected
    assert saved["required_keywords"] == [] and saved["avoid_advanced_english"] is False


def test_dashboard_browser_renders_local_jobs(tmp_path) -> None:
    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    output.mkdir()
    jobs = [
        {
            "title": "Desenvolvedor Java Junior",
            "company": "Acme",
            "canonical_url": "https://example.com/vagas/1",
            "source": "programathor",
            "location": "Remoto",
            "technologies": ["Java", "Spring"],
            "match_labels": ["TECH_MATCH:java"],
            "observed_at": "2026-09-29T04:00:00+00:00",
        },
        {
            "title": "Engenheiro Backend Senior",
            "company": "Beta",
            "canonical_url": "https://example.com/vagas/2",
            "source": "companhia-de-estagios",
            "location": "Sao Paulo",
            "technologies": ["Java"],
            "match_labels": ["SENIORITY_MISMATCH:senior"],
            "observed_at": "2026-09-29T04:00:00+00:00",
        },
    ]
    (output / "vagas.jsonl").write_text(
        "".join(json.dumps(job) + "\n" for job in jobs), encoding="utf-8"
    )
    (output / "relatorio-execucao.json").write_text(
        json.dumps(
            {
                "finished_at": "2026-09-29T04:00:00+00:00",
                "scrapling_version": "0.4.15",
                "sources": [
                    {"source": "programathor", "status": "SUCCESS", "records": 1},
                    {
                        "source": "companhia-de-estagios",
                        "status": "PARTIAL",
                        "records": 1,
                    },
                ],
                "totals": {"unique": 2},
            }
        ),
        encoding="utf-8",
    )
    static_dir = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(output, runner=lambda *_: 0),
        static_dir,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.wait_for_selector("#jobs-table-body tr")
            assert page.locator("#jobs-table-body tr").count() == 2
            assert page.locator("#summary-jobs").inner_text() == "2"
            assert "Desenvolvedor Java Junior" in page.locator("body").inner_text()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_dashboard_browser_filters_jobs_by_text(tmp_path) -> None:
    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    output.mkdir()
    jobs = [
        {
            "title": "Desenvolvedor Java Junior",
            "company": "Acme",
            "canonical_url": "https://example.com/1",
            "source": "programathor",
            "technologies": ["Java"],
            "match_labels": [],
        },
        {
            "title": "Analista de Dados",
            "company": "Beta",
            "canonical_url": "https://example.com/2",
            "source": "example",
            "technologies": ["SQL"],
            "match_labels": [],
        },
    ]
    (output / "vagas.jsonl").write_text(
        "".join(json.dumps(job) + "\n" for job in jobs), encoding="utf-8"
    )
    static_dir = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(output, runner=lambda *_: 0),
        static_dir,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.wait_for_selector("#jobs-table-body tr")
            page.locator("#text-filter").fill("java")
            assert page.locator("#jobs-table-body tr").count() == 1
            assert page.locator("#visible-count").inner_text() == "1 vaga"
            assert "Desenvolvedor Java Junior" in page.locator("#jobs-table-body").inner_text()
            assert page.locator("#download-report").get_attribute("href") == (
                "/api/export/markdown?text=java&tracked=active"
            )
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_dashboard_browser_uses_fit_state_for_labels_filter_and_order(tmp_path) -> None:
    """A missing FIT label must not be presented as a positive match."""
    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    output.mkdir()
    jobs = [
        {
            "title": "Android Developer",
            "company": "Mobile Co",
            "canonical_url": "https://example.com/android",
            "source": "example",
            "match_labels": ["TECH_MATCH:android"],
            "description_summary": "Android nativo",
        },
        {
            "title": "Java Ready score menor",
            "company": "Acme",
            "canonical_url": "https://example.com/ready-low",
            "source": "example",
            "match_labels": ["FIT:READY", "FIT_SCORE:67"],
        },
        {
            "title": "Java A revisar",
            "company": "Beta",
            "canonical_url": "https://example.com/review",
            "source": "example",
            "match_labels": ["FIT:CONDITIONAL", "FIT_SCORE:93"],
        },
        {
            "title": "Java Ready score maior",
            "company": "Gamma",
            "canonical_url": "https://example.com/ready-high",
            "source": "example",
            "match_labels": ["FIT:READY", "FIT_SCORE:88"],
        },
    ]
    (output / "vagas.jsonl").write_text(
        "".join(json.dumps(job) + "\n" for job in jobs), encoding="utf-8"
    )
    static_dir = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(output, runner=lambda *_: 0),
        static_dir,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.wait_for_selector("#jobs-table-body tr")

            android_row = page.locator("#jobs-table-body tr").filter(has_text="Android Developer")
            assert "Dados insuficientes" in android_row.inner_text()
            assert "Mais compatível" not in android_row.inner_text()
            assert page.locator("#summary-matches").inner_text() == "2"

            page.locator("#match-filter").select_option("ready")
            visible_titles = page.locator("#jobs-table-body .job-title").all_inner_texts()
            assert visible_titles == ["Java Ready score maior", "Java Ready score menor"]
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_dashboard_browser_sorts_by_published_date_and_shows_it(tmp_path) -> None:
    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    output.mkdir()
    jobs = [
        {
            "title": "Java sem data",
            "canonical_url": "https://example.com/sem-data",
            "source": "example",
            "match_labels": ["FIT:READY", "FIT_SCORE:4"],
            "published_at": None,
        },
        {
            "title": "Java antiga",
            "canonical_url": "https://example.com/antiga",
            "source": "example",
            "match_labels": ["FIT:READY", "FIT_SCORE:3"],
            "published_at": "2026-09-01T12:00:00+00:00",
        },
        {
            "title": "Java recente",
            "canonical_url": "https://example.com/recente",
            "source": "example",
            "match_labels": ["ALSO_SEEN_IN:indeed", "FIT:CONDITIONAL", "FIT_SCORE:2"],
            "published_at": "2026-09-28T12:00:00+00:00",
        },
    ]
    (output / "vagas.jsonl").write_text(
        "".join(json.dumps(job) + "\n" for job in jobs), encoding="utf-8"
    )
    static_dir = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(output, runner=lambda *_: 0),
        static_dir,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.wait_for_selector("#jobs-table-body tr")

            titles = page.locator("#jobs-table-body .job-title").all_inner_texts()
            assert titles == ["Java sem data", "Java antiga", "Java recente"]

            page.locator("#sort-order").select_option("recent")
            titles = page.locator("#jobs-table-body .job-title").all_inner_texts()
            assert titles == ["Java recente", "Java antiga", "Java sem data"]

            recent_row = page.locator("#jobs-table-body tr").filter(has_text="Java recente")
            assert "28/09/2026" in recent_row.inner_text()
            assert "também em indeed" in recent_row.inner_text()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_webapp_main_rejects_non_loopback_host(capsys) -> None:
    from job_radar.webapp import main

    exit_code = main(["--host", "0.0.0.0", "--no-browser"])

    assert exit_code == 2
    assert "127.0.0.1" in capsys.readouterr().err


def test_webapp_parser_accepts_workers_for_local_collection() -> None:
    from job_radar.webapp import _parser

    args = _parser().parse_args(["--workers", "3"])

    assert args.workers == 3


def test_dashboard_browser_reveals_source_details_on_request(tmp_path) -> None:
    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    output.mkdir()
    (output / "relatorio-execucao.json").write_text(
        json.dumps(
            {
                "sources": [
                    {"source": "programathor", "status": "PARTIAL", "records": 12}
                ]
            }
        ),
        encoding="utf-8",
    )
    static_dir = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(output, runner=lambda *_: 0),
        static_dir,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            details = page.locator("#source-statuses")
            assert details.is_visible() is False
            button = page.get_by_role("button", name="Ver detalhes")
            assert button.count() == 1
            button.click()
            assert details.is_visible() is True
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_dashboard_browser_shows_source_count_warnings(tmp_path) -> None:
    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    output.mkdir()
    (output / "relatorio-execucao.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source": "nube",
                        "status": "SUCCESS",
                        "records": 0,
                        "warnings": ["SOURCE_COUNT_ZERO:0<900"],
                    },
                    {"source": "gupy", "status": "SUCCESS", "records": 50, "warnings": []},
                ]
            }
        ),
        encoding="utf-8",
    )
    static_dir = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(output, runner=lambda *_: 0),
        static_dir,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.get_by_role("button", name="Ver detalhes").click()
            nube = page.locator(".source-row").filter(has_text="nube")
            nube.locator(".source-warning").wait_for()
            assert "zerou" in nube.inner_text()
            gupy = page.locator(".source-row").filter(has_text="gupy")
            assert gupy.locator(".source-warning").count() == 0
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _tracking_server(tmp_path, jobs):
    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    output.mkdir(exist_ok=True)
    (output / "vagas.jsonl").write_text(
        "".join(json.dumps(job, ensure_ascii=False) + "\n" for job in jobs),
        encoding="utf-8",
    )
    static_dir = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(output, runner=lambda *_: 0),
        static_dir,
        tracking_path=tmp_path / "tracking.json",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _put_json(url: str, payload: dict) -> tuple[int, dict]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


_TRACKING_JOBS = [
    {
        "title": "Java Júnior; Remoto",
        "company": "Acme",
        "canonical_url": "https://example.com/a",
        "source": "gupy",
        "location": "Brasil",
        "workplace_model": "REMOTE",
        "technologies": ["java", "spring boot"],
        "published_at": "2026-09-28T12:00:00+00:00",
        "match_labels": ["FIT:READY"],
    },
    {
        "title": "Estágio Backend",
        "company": "Beta",
        "canonical_url": "https://example.com/b",
        "source": "nube",
        "match_labels": ["FIT:CONDITIONAL"],
    },
]


def test_tracking_api_saves_and_clears_job_status(tmp_path) -> None:
    server, thread = _tracking_server(tmp_path, _TRACKING_JOBS)
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, saved = _put_json(
            f"{base}/api/tracking",
            {"url": "https://example.com/a", "status": "APPLIED", "note": "Enviado"},
        )
        with urlopen(f"{base}/api/tracking", timeout=2) as response:
            loaded = json.loads(response.read())
        bad_status, bad = _put_json(
            f"{base}/api/tracking", {"url": "javascript:x", "status": "SAVED"}
        )
        cleared_status, cleared = _put_json(
            f"{base}/api/tracking", {"url": "https://example.com/a", "status": None}
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 200
    assert saved["jobs"]["https://example.com/a"]["status"] == "APPLIED"
    assert loaded["jobs"]["https://example.com/a"]["note"] == "Enviado"
    assert bad_status == 400 and "error" in bad
    assert cleared_status == 200 and cleared == {"jobs": {}}


def test_csv_export_respects_filters_and_tracking(tmp_path) -> None:
    import csv
    import io

    server, thread = _tracking_server(tmp_path, _TRACKING_JOBS)
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        _put_json(f"{base}/api/tracking", {"url": "https://example.com/b", "status": "DISCARDED"})
        _put_json(f"{base}/api/tracking", {"url": "https://example.com/a", "status": "SAVED"})
        with urlopen(f"{base}/api/export/csv?tracked=active", timeout=2) as response:
            content_type = response.headers["Content-Type"]
            disposition = response.headers["Content-Disposition"]
            body = response.read().decode("utf-8-sig")
        with urlopen(f"{base}/api/export/csv?tracked=discarded", timeout=2) as response:
            discarded = response.read().decode("utf-8-sig")
        with urlopen(f"{base}/api/export/csv?match=review", timeout=2) as response:
            review = response.read().decode("utf-8-sig")
        try:
            urlopen(f"{base}/api/export/csv?tracked=bogus", timeout=2)
            bogus_status = 200
        except HTTPError as error:
            bogus_status = error.code
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert content_type.startswith("text/csv")
    assert "vagas.csv" in disposition
    rows = list(csv.DictReader(io.StringIO(body), delimiter=";"))
    assert [row["url"] for row in rows] == ["https://example.com/a"]
    assert rows[0]["titulo"] == "Java Júnior; Remoto"
    assert rows[0]["aderencia"] == "Mais compatível"
    assert rows[0]["acompanhamento"] == "Salva"
    assert rows[0]["tecnologias"] == "java, spring boot"
    assert rows[0]["publicada_em"] == "2026-09-28T12:00:00+00:00"
    assert "https://example.com/b" in discarded and "https://example.com/a" not in discarded
    assert "https://example.com/b" in review and "https://example.com/a" not in review
    assert bogus_status == 400


def test_dashboard_browser_marks_jobs_and_hides_discarded(tmp_path) -> None:
    from playwright.sync_api import sync_playwright

    server, thread = _tracking_server(tmp_path, _TRACKING_JOBS)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.wait_for_selector("#jobs-table-body tr")

            row_b = page.locator("#jobs-table-body tr").filter(has_text="Estágio Backend")
            with page.expect_response(lambda r: r.url.endswith("/api/tracking")):
                row_b.locator("select.tracking-select").select_option("DISCARDED")
            page.wait_for_function(
                "() => document.querySelectorAll('#jobs-table-body tr').length === 1"
            )

            row_a = page.locator("#jobs-table-body tr").filter(has_text="Java Júnior")
            with page.expect_response(lambda r: r.url.endswith("/api/tracking")):
                row_a.locator("select.tracking-select").select_option("APPLIED")

            page.locator("#tracking-filter").select_option("discarded")
            titles = page.locator("#jobs-table-body .job-title").all_inner_texts()
            assert titles == ["Estágio Backend"]

            page.locator("#tracking-filter").select_option("applied")
            titles = page.locator("#jobs-table-body .job-title").all_inner_texts()
            assert titles == ["Java Júnior; Remoto"]
            assert "tracked=applied" in page.locator("#download-csv").get_attribute("href")

            page.reload()
            page.wait_for_selector("#jobs-table-body tr")
            page.locator("#tracking-filter").select_option("applied")
            row = page.locator("#jobs-table-body tr").filter(has_text="Java Júnior")
            assert row.locator("select.tracking-select").input_value() == "APPLIED"
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    saved = json.loads((tmp_path / "tracking.json").read_text(encoding="utf-8"))
    assert saved["jobs"]["https://example.com/a"]["status"] == "APPLIED"


def test_new_untracked_filter_keeps_only_fresh_unmarked_jobs() -> None:
    from job_radar.webapp import filter_jobs_for_export

    jobs = [
        {"canonical_url": "https://example.com/1", "match_labels": ["STATUS:NEW"]},
        {"canonical_url": "https://example.com/2", "match_labels": ["STATUS:NEW"]},
        {"canonical_url": "https://example.com/3", "match_labels": []},
    ]
    tracking = {"https://example.com/2": {"status": "SAVED"}}

    result = filter_jobs_for_export(jobs, tracked="new", tracking=tracking)

    assert [job["canonical_url"] for job in result] == ["https://example.com/1"]


# --- Revisão 29/09/2026: fora do escopo e motivos ---------------------------


def test_filter_hides_off_topic_unless_requested() -> None:
    from job_radar.webapp import filter_jobs_for_export

    jobs = [
        {"title": "Dev Java", "source": "a", "match_labels": ["FIT:READY"]},
        {
            "title": "Auxiliar",
            "source": "a",
            "match_labels": ["FIT:AMBIGUOUS", "RELEVANCE:OFF_TOPIC"],
        },
    ]

    assert [j["title"] for j in filter_jobs_for_export(jobs, match="all")] == [
        "Dev Java",
        "Auxiliar",
    ]
    assert [j["title"] for j in filter_jobs_for_export(jobs, match="offtopic")] == [
        "Auxiliar"
    ]
    assert [j["title"] for j in filter_jobs_for_export(jobs, match="ready")] == [
        "Dev Java"
    ]


def test_fit_reasons_explains_ambiguous_job_without_labels() -> None:
    from job_radar.webapp import fit_reasons

    assert fit_reasons({"match_labels": ["FIT:AMBIGUOUS"]}) == [
        "poucos dados para avaliar"
    ]
    assert fit_reasons({"match_labels": ["FIT:READY"]}) == []
