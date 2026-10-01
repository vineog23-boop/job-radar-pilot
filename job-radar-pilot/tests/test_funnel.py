"""Funil de candidatura: salva → aplicada → entrevista → oferta / recusada."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from threading import Thread

from job_radar.tracking import TRACKING_NAMES, TRACKING_STATUSES, TrackingStore
from job_radar.webapp import build_jobs_csv, filter_jobs_for_export

NOW = datetime(2026, 10, 1, 9, tzinfo=timezone.utc)
URL = "https://example.com/vagas/1"


def test_new_statuses_are_accepted_and_named() -> None:
    assert TRACKING_STATUSES == ("SAVED", "APPLIED", "INTERVIEW", "OFFER", "REJECTED", "DISCARDED")
    assert TRACKING_NAMES["INTERVIEW"] == "Entrevista"
    assert TRACKING_NAMES["OFFER"] == "Oferta"
    assert TRACKING_NAMES["REJECTED"] == "Recusada"


def test_each_stage_keeps_its_date_and_the_note_survives(tmp_path: Path) -> None:
    store = TrackingStore(tmp_path / "t.json")

    store.set_status(URL, "APPLIED", now=NOW, note="Enviei pelo Gupy")
    store.set_status(URL, "INTERVIEW", now=NOW + timedelta(days=5))
    entry = store.load()[URL]

    assert entry["status"] == "INTERVIEW"
    assert entry["applied_at"] == NOW.isoformat()
    assert entry["interview_at"] == (NOW + timedelta(days=5)).isoformat()
    assert entry["note"] == "Enviei pelo Gupy"  # mudar o estado não apaga a nota


def test_empty_note_clears_it(tmp_path: Path) -> None:
    store = TrackingStore(tmp_path / "t.json")
    store.set_status(URL, "SAVED", now=NOW, note="lembrar")

    store.set_status(URL, "SAVED", now=NOW, note="")

    assert "note" not in store.load()[URL]


def test_filters_for_each_stage_and_in_progress() -> None:
    jobs = [
        {"canonical_url": f"https://x.com/{index}", "match_labels": ["FIT:READY"], "source": "x"}
        for index in range(5)
    ]
    tracking = {
        "https://x.com/0": {"status": "APPLIED"},
        "https://x.com/1": {"status": "INTERVIEW"},
        "https://x.com/2": {"status": "OFFER"},
        "https://x.com/3": {"status": "REJECTED"},
    }

    def urls(tracked: str) -> list[str]:
        return [job["canonical_url"] for job in filter_jobs_for_export(jobs, tracked=tracked, tracking=tracking)]

    assert urls("interview") == ["https://x.com/1"]
    assert urls("offer") == ["https://x.com/2"]
    assert urls("rejected") == ["https://x.com/3"]
    assert urls("inprogress") == ["https://x.com/0", "https://x.com/1", "https://x.com/2"]


def test_csv_shows_stage_names() -> None:
    job = {"canonical_url": "https://x.com/1", "match_labels": ["FIT:READY"], "title": "Dev"}

    text = build_jobs_csv([job], {"https://x.com/1": {"status": "INTERVIEW"}}).decode("utf-8-sig")

    assert "Entrevista" in text


def test_dashboard_funnel_counts_and_filters(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    output.mkdir()
    jobs = [
        {"title": f"Vaga {index}", "company": "Acme", "canonical_url": f"https://x.com/{index}",
         "source": "x", "match_labels": ["FIT:READY", "FIT_SCORE:3"]}
        for index in range(3)
    ]
    (output / "vagas.jsonl").write_text("".join(json.dumps(job) + "\n" for job in jobs), encoding="utf-8")
    tracking = tmp_path / "prefs" / "tracking.json"
    store = TrackingStore(tracking)
    store.set_status("https://x.com/0", "APPLIED", now=NOW)
    store.set_status("https://x.com/1", "INTERVIEW", now=NOW)
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(output, runner=lambda *_: 0),
        Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web",
        preferences_path=tmp_path / "prefs" / "search-preferences.json",
        tracking_path=tracking,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.wait_for_selector("#jobs-table-body tr")
            funnel = page.locator("#funnel")
            funnel.wait_for(state="visible")
            assert "1 aplicada" in funnel.inner_text() and "1 entrevista" in funnel.inner_text()

            page.get_by_role("button", name="Em processo: 2").click()
            titles = page.locator("#jobs-table-body .job-title").all_inner_texts()
            assert sorted(titles) == ["Vaga 0", "Vaga 1"]

            page.locator("#tracking-filter").select_option("active")
            page.get_by_label("Acompanhamento da vaga Vaga 2").select_option("OFFER")
            page.wait_for_function("document.querySelector('#funnel').textContent.includes('1 oferta')")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
