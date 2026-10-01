"""Rendimento por portal: quantas vagas úteis cada um trouxe nesta coleta."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread

from job_radar.models import CollectionStatus, SourceRunResult, VacancyRecord
from job_radar.output import write_outputs
from job_radar.pipeline import PipelineResult


def _record(source: str, index: int, labels: tuple[str, ...]) -> VacancyRecord:
    return VacancyRecord(
        source=source,
        source_job_id=str(index),
        canonical_url=f"https://{source}.example.com/{index}",
        title=f"Vaga {index}",
        company="Acme",
        observed_at="2026-10-01T08:00:00+00:00",
        match_labels=labels,
    )


def test_report_counts_useful_discarded_and_ready_per_source(tmp_path: Path) -> None:
    good = [
        _record("bom", 1, ("FIT:READY",)),
        _record("bom", 2, ("FIT:EXCLUDE",)),
        _record("bom", 3, ("FIT:CONDITIONAL",)),
    ]
    bad = [_record("ruim", 4, ("FIT:AMBIGUOUS", "RELEVANCE:OFF_TOPIC"))]
    result = PipelineResult(
        started_at="2026-10-01T08:00:00+00:00",
        finished_at="2026-10-01T08:05:00+00:00",
        records=tuple(good + bad),
        ambiguous=(),
        source_results=(
            SourceRunResult("bom", CollectionStatus.SUCCESS, records=tuple(good)),
            SourceRunResult("ruim", CollectionStatus.SUCCESS, records=tuple(bad)),
        ),
        raw_record_count=4,
        duplicate_count=0,
    )

    manifest = write_outputs(result, tmp_path, prune=True)

    report = json.loads(manifest.report_path.read_text(encoding="utf-8"))
    by_source = {item["source"]: item for item in report["sources"]}
    assert (by_source["bom"]["useful"], by_source["bom"]["discarded"], by_source["bom"]["compatible"]) == (2, 1, 2)
    assert (by_source["ruim"]["useful"], by_source["ruim"]["discarded"], by_source["ruim"]["compatible"]) == (0, 1, 0)


def test_dashboard_shows_yield_and_flags_low_yield_portal(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    output.mkdir()
    (output / "vagas.jsonl").write_text(
        json.dumps({"title": "Vaga", "company": "Acme", "canonical_url": "https://x.com/1",
                    "source": "bom", "match_labels": ["FIT:READY"]}) + "\n",
        encoding="utf-8",
    )
    (output / "relatorio-execucao.json").write_text(
        json.dumps({"finished_at": "2026-10-01T08:05:00+00:00", "sources": [
            {"source": "bom", "status": "SUCCESS", "records": 12, "useful": 9, "discarded": 3, "compatible": 4},
            {"source": "ruim", "status": "SUCCESS", "records": 20, "useful": 0, "discarded": 20, "compatible": 0},
        ]}),
        encoding="utf-8",
    )
    server = create_server(
        "127.0.0.1", 0, SearchController(output, runner=lambda *_: 0),
        Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.get_by_role("button", name="Ver detalhes").click()
            page.wait_for_selector("#source-statuses .source-row")
            rows = page.locator("#source-statuses .source-row")
            good = rows.filter(has_text="bom").inner_text()
            bad = rows.filter(has_text="ruim").inner_text()
            assert "9 úteis" in good and "4 compatíveis" in good
            assert "rende pouco" in bad
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
