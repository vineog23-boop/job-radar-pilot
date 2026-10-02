from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Thread
from urllib.request import urlopen
import zipfile
from xml.etree import ElementTree

from job_radar.webapp import filter_jobs_for_export
from job_radar.xlsx_export import build_jobs_xlsx, job_score

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _job(number: int, *, fit: str = "READY", points: int = 4, days: int = 1, **extra):
    published = datetime(2026, 9, 30 - min(days, 29), 8, 0, tzinfo=timezone.utc)
    job = {
        "source": "gupy-api",
        "title": f"Dev Java {number}",
        "company": f"Empresa {number}",
        "location": "Remoto",
        "workplace_model": "REMOTE",
        "seniority": "junior",
        "technologies": ["Java", "Spring"],
        "published_at": published.isoformat(),
        "canonical_url": f"https://example.com/vaga/{number}?a=1&b=2",
        "match_labels": [f"FIT:{fit}", f"FIT_SCORE:{points}", "STATUS:NEW"],
    }
    job.update(extra)
    return job


def test_score_rewards_fit_and_recency_and_zeroes_excluded() -> None:
    assert job_score(_job(1, days=1), NOW) == 100
    assert job_score(_job(2, days=20), NOW) == 92
    assert job_score(_job(3, fit="CONDITIONAL", points=2, days=1), NOW) == 50
    assert job_score(_job(4, fit="EXCLUDE", points=-1), NOW) == 0
    assert job_score(_job(5, published_at=None), NOW) == 90


def test_workbook_is_valid_sorted_and_has_clickable_links() -> None:
    jobs = [_job(1, fit="CONDITIONAL", points=2), _job(2), _job(3, days=25)]
    data = build_jobs_xlsx(
        jobs,
        {"https://example.com/vaga/3?a=1&b=2": {"status": "APPLIED", "note": "enviei CV"}},
        filters=[("Aderência", "Todas")],
        reasons_for=lambda job: ["local não confirmado"],
        now=NOW,
    )
    archive = zipfile.ZipFile(io.BytesIO(data))
    for name in archive.namelist():
        ElementTree.fromstring(archive.read(name))  # todo XML bem formado
    sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows = sheet.findall(".//m:row", NS)
    assert len(rows) == 4

    def text(row, index):
        cell = rows[row].findall("m:c", NS)[index]
        node = cell.find(".//m:t", NS)
        return node.text if node is not None else (cell.findtext("m:v", namespaces=NS) or "")

    assert [text(0, i) for i in range(4)] == ["Empresa", "Cargo", "Nível", "Modalidade"]
    assert text(1, 0) == "Empresa 2"  # maior score primeiro
    assert text(1, 2) == "Júnior" and text(1, 3) == "Remoto"
    assert text(1, 5) == "100"
    assert text(3, 0) == "Empresa 1"
    applied = next(i for i in range(1, 4) if text(i, 0) == "Empresa 3")
    assert text(applied, 6) == "Aplicada"
    assert "enviei CV" in text(applied, 11) and "Atenção: local não confirmado" in text(applied, 11)
    assert sheet.find("m:autoFilter", NS) is not None
    assert sheet.find(".//m:pane", NS).get("state") == "frozen"
    links = sheet.findall(".//m:hyperlink", NS)
    assert len(links) == 3
    rels = archive.read("xl/worksheets/_rels/sheet1.xml.rels").decode()
    assert "https://example.com/vaga/2?a=1&amp;b=2" in rels
    assert b"Filtros e crit" in archive.read("xl/workbook.xml")


def test_workbook_survives_hostile_text_and_empty_list() -> None:
    hostile = _job(1, title="A<b>&\x00\x0b'\"", company=None, canonical_url="javascript:alert(1)")
    archive = zipfile.ZipFile(io.BytesIO(build_jobs_xlsx([hostile], {}, now=NOW)))
    for name in archive.namelist():
        ElementTree.fromstring(archive.read(name))
    assert "xl/worksheets/_rels/sheet1.xml.rels" not in archive.namelist()
    empty = zipfile.ZipFile(io.BytesIO(build_jobs_xlsx([], {}, now=NOW)))
    assert len(ElementTree.fromstring(empty.read("xl/worksheets/sheet1.xml")).findall(".//m:row", NS)) == 1


def test_export_filters_combine() -> None:
    jobs = [
        _job(1),
        _job(2, seniority="pleno", match_labels=["FIT:READY", "FIT_SCORE:4", "SENIORITY_MATCH:pleno"]),
        _job(3, workplace_model="HYBRID", fit="CONDITIONAL", points=2),
        _job(4, days=29),
        _job(5, published_at=None),
        _job(6, match_labels=["FIT:READY", "FIT_SCORE:4", "RELEVANCE:OFF_TOPIC"]),
    ]

    def ids(**kwargs):
        return [j["title"][-1] for j in filter_jobs_for_export(jobs, now=NOW, **kwargs)]

    assert ids() == ["1", "2", "3", "4", "5"]  # fora da área some por padrão
    assert ids(match="ready") == ["1", "2", "4", "5"]
    assert ids(match="fit", workplaces=("HYBRID",)) == ["3"]
    assert ids(levels=("pleno",)) == ["2"]
    assert ids(max_age_days=7) == ["1", "2", "3"]  # sem data fica de fora
    assert ids(min_score=95) == ["1", "2"]


def _serve(tmp_path: Path):
    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    output.mkdir()
    # Datas relativas a hoje: o painel abre em "Últimos 30 dias" + "Ativas".
    live = datetime.now(timezone.utc)
    dates = {
        "published_at": (live - timedelta(days=1)).isoformat(),
        "observed_at": live.isoformat(),
    }
    jobs = [_job(1, **dates), _job(2, fit="CONDITIONAL", points=2, **dates)]
    (output / "vagas.jsonl").write_text(
        "\n".join(json.dumps(j) for j in jobs) + "\n", encoding="utf-8"
    )
    static_dir = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
    server = create_server(
        "127.0.0.1", 0, SearchController(output, runner=lambda *_: 0), static_dir,
        preferences_path=tmp_path / "prefs.json", tracking_path=tmp_path / "tracking.json",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_export_endpoints_count_and_download(tmp_path: Path) -> None:
    from urllib.error import HTTPError

    server, thread = _serve(tmp_path)
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base}/api/export/count?match=ready", timeout=5) as response:
            ready = json.loads(response.read())["count"]
        with urlopen(f"{base}/api/export/count", timeout=5) as response:
            everything = json.loads(response.read())["count"]
        with urlopen(f"{base}/api/export/xlsx?match=fit&min_score=90", timeout=5) as response:
            body = response.read()
            disposition = response.headers["Content-Disposition"]
            kind = response.headers["Content-Type"]
        try:
            urlopen(f"{base}/api/export/count?min_score=abc", timeout=5)
            bad = 200
        except HTTPError as error:
            bad = error.code
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert (ready, everything) == (1, 2)
    assert kind.startswith("application/vnd.openxmlformats")
    assert ".xlsx" in disposition
    assert zipfile.ZipFile(io.BytesIO(body)).testzip() is None
    assert bad == 400


def test_dashboard_export_panel_presets_and_count(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    server, thread = _serve(tmp_path)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.get_by_role("button", name="Exportar vagas").click()
            page.wait_for_function(
                "document.querySelector('#export-count').textContent.includes('será exportada')"
            )
            assert page.locator("#export-count").text_content() == "1 vaga será exportada."
            href = page.locator("#export-xlsx").get_attribute("href")
            assert "match=ready" in href and "min_score=70" in href
            page.click('[data-preset="all"]')
            page.wait_for_function(
                "document.querySelector('#export-count').textContent.startsWith('2 ')"
            )
            page.check('input[name="export-workplace"][value="HYBRID"]')
            page.wait_for_function(
                "document.querySelector('#export-count').textContent.startsWith('0 ')"
            )
            assert "workplaces=HYBRID" in page.locator("#export-xlsx").get_attribute("href")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
