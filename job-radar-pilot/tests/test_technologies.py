"""O classificador não grava o próprio palpite em ``technologies``.

``technologies`` é dado do portal. O que o classificador encontrou fica nos
rótulos ``TECH_MATCH:``; a exibição (painel, CSV, xlsx, texto para IA) junta
os dois. Antes, o palpite virava dado e a reclassificação o lia de volta: um
falso positivo ficava "grudado" na vaga mesmo depois de trocar o perfil.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread

from job_radar.classifier import classify
from job_radar.fit import job_technologies
from job_radar.models import SearchProfile, VacancyRecord, WorkplaceModel
from job_radar.output import _record_payload
from job_radar.reclassify import reclassify_payloads
from job_radar.webapp import build_jobs_ai_text, build_jobs_csv

PROJECT = Path(__file__).resolve().parents[1]

JAVA = SearchProfile(
    positive_keywords=("java", "kafka"),
    seniority_levels=("junior",),
    location_scopes=("remoto-brasil",),
)
PYTHON = SearchProfile(
    positive_keywords=("python",),
    seniority_levels=("junior",),
    location_scopes=("remoto-brasil",),
)


def _payload() -> dict:
    record = VacancyRecord(
        source="gupy",
        source_job_id="1",
        canonical_url="https://x.com/1",
        title="Desenvolvedor Java Júnior",
        company="Acme",
        description_summary="Mensageria com Kafka",
        location="Remoto",
        workplace_model=WorkplaceModel.REMOTE,
        technologies=("Spring",),
    )
    return _record_payload(classify(record, JAVA, default_country="BR"))


def test_classifier_guess_does_not_become_source_data() -> None:
    payload = _payload()

    assert payload["technologies"] == ["Spring"]
    assert "TECH_MATCH:kafka" in payload["match_labels"]
    assert job_technologies(payload) == ["Spring", "java", "kafka"]


def test_reclassify_with_other_profile_drops_old_guess() -> None:
    (updated,) = reclassify_payloads([_payload()], PYTHON, {"gupy": "BR"})

    assert updated["technologies"] == ["Spring"]
    assert job_technologies(updated) == ["Spring"]


def test_job_technologies_dedupes_ignoring_case() -> None:
    job = {"technologies": ["Java", "SQL"], "match_labels": ["TECH_MATCH:java", "FIT:READY"]}

    assert job_technologies(job) == ["Java", "SQL"]


def test_exports_show_merged_technologies() -> None:
    payload = _payload()

    csv_text = build_jobs_csv([payload], {}).decode("utf-8-sig")
    ai_text = build_jobs_ai_text([payload], {}).decode("utf-8")

    assert "Spring, java, kafka" in csv_text
    assert "Spring, java, kafka" in ai_text


def test_dashboard_shows_technologies_found_by_classifier(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    output.mkdir()
    job = {
        "title": "Dev Java",
        "company": "Acme",
        "canonical_url": "https://example.com/java",
        "source": "example",
        "technologies": [],
        "match_labels": ["FIT:READY", "FIT_SCORE:3", "TECH_MATCH:java"],
    }
    (output / "vagas.jsonl").write_text(json.dumps(job) + "\n", encoding="utf-8")
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(output, runner=lambda *_: 0),
        PROJECT / "src" / "job_radar" / "web",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.wait_for_selector("#jobs-table-body tr")
            row = page.locator("#jobs-table-body tr").first.inner_text()
            assert "java" in row
            assert "Tecnologias não informadas" not in row
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
