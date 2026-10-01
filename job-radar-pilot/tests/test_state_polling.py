"""/api/state só manda a lista de vagas quando ela mudou.

O painel consulta o estado a cada 0,9 s (busca rodando) ou 5 s (parado). Antes,
cada consulta relia o vagas.jsonl inteiro, mandava tudo e o painel redesenhava
a tabela — gastando CPU e tirando o foco de quem navega pelo teclado.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Event, Thread
from urllib.request import urlopen

from job_radar.webapp import SearchController, create_server

PROJECT = Path(__file__).resolve().parents[1]


def _write_jobs(output: Path, titles: list[str]) -> None:
    jobs = [
        {
            "title": title,
            "company": "Acme",
            "canonical_url": f"https://example.com/{index}",
            "source": "example",
            "match_labels": ["FIT:READY", "FIT_SCORE:3"],
        }
        for index, title in enumerate(titles)
    ]
    (output / "vagas.jsonl").write_text(
        "".join(json.dumps(job) + "\n" for job in jobs), encoding="utf-8"
    )


def test_snapshot_skips_unchanged_output(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    _write_jobs(output, ["Dev Java"])
    controller = SearchController(output, runner=lambda *_: 0)

    first = controller.snapshot()
    again = controller.snapshot(since=first["output_version"])
    _write_jobs(output, ["Dev Java", "Dev Kotlin"])
    changed = controller.snapshot(since=first["output_version"])

    assert first["output_version"] and len(first["jobs"]) == 1
    assert again["unchanged"] is True
    assert "jobs" not in again and "report" not in again
    assert again["status"] == "IDLE"  # o estado da busca vem sempre
    assert changed.get("unchanged") is not True
    assert len(changed["jobs"]) == 2
    assert changed["output_version"] != first["output_version"]


def test_snapshot_without_output_has_stable_version(tmp_path: Path) -> None:
    controller = SearchController(tmp_path / "nada", runner=lambda *_: 0)

    first = controller.snapshot()

    assert first["jobs"] == []
    assert controller.snapshot(since=first["output_version"])["unchanged"] is True


def test_dashboard_keeps_table_rows_while_output_is_unchanged(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    output = tmp_path / "output"
    output.mkdir()
    _write_jobs(output, ["Dev Java"])
    release = Event()

    def runner(output_dir, sources, workers, on_line):
        release.wait(timeout=30)
        return 0

    controller = SearchController(output, runner=runner)
    server = create_server(
        "127.0.0.1", 0, controller, PROJECT / "src" / "job_radar" / "web"
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    controller.start()  # busca rodando: o painel consulta a cada 0,9 s
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.wait_for_selector("#jobs-table-body tr")
            page.evaluate(
                "document.querySelector('#jobs-table-body tr').dataset.marker = 'mesma-linha'"
            )
            page.wait_for_timeout(2500)
            assert page.locator("#jobs-table-body tr[data-marker='mesma-linha']").count() == 1

            _write_jobs(output, ["Dev Java", "Dev Kotlin"])
            page.wait_for_function(
                "document.querySelectorAll('#jobs-table-body .job-title').length === 2",
                timeout=5000,
            )
            assert page.locator("#jobs-table-body tr[data-marker='mesma-linha']").count() == 0
            browser.close()
    finally:
        release.set()
        controller.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_state_api_accepts_since(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    _write_jobs(output, ["Dev Java"])
    server = create_server(
        "127.0.0.1", 0, SearchController(output, runner=lambda *_: 0), tmp_path
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base}/api/state", timeout=3) as response:
            first = json.loads(response.read())
        with urlopen(f"{base}/api/state?since={first['output_version']}", timeout=3) as response:
            again = json.loads(response.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert len(first["jobs"]) == 1
    assert again["unchanged"] is True and "jobs" not in again
