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

    def runner(output_dir, sources, on_line):
        assert output_dir == tmp_path
        assert sources == ["programathor"]
        on_line(
            "programathor: PARTIAL; pages=1; cards=16; records=12; "
            "stop=PAGINATION_UNVERIFIED"
        )
        emitted.set()
        release.wait(timeout=2)
        return 3

    controller = SearchController(tmp_path, runner=runner)

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
        executable=Path("python.exe"),
    )

    assert command == [
        "python.exe",
        "-m",
        "job_radar.cli",
        "collect",
        "--output",
        str(tmp_path / "output"),
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


def test_search_api_starts_collection_and_rejects_duplicate(tmp_path) -> None:
    from job_radar.webapp import SearchController, create_server

    release = Event()
    received_sources: list[list[str] | None] = []

    def runner(output_dir, sources, on_line):
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
        "text-filter",
        "source-filter",
        "match-filter",
        "summary-cards",
        "source-statuses",
        "jobs-table-body",
        "live-status",
    }.issubset(parser.ids)


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
