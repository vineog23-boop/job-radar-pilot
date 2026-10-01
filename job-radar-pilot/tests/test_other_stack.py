"""Item 1.1: "Dados insuficientes" não pode esconder vaga de outra stack.

E o inverso: "backend"/"api rest" sozinhos não fazem uma vaga Python/Node/.NET
virar "Mais compatível" para um perfil Java.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_radar.classifier import classify
from job_radar.fit import fit_reasons, fit_state
from job_radar.models import SearchProfile, VacancyRecord, WorkplaceModel
from job_radar.reclassify import reclassify_payloads
from job_radar.webapp import filter_jobs_for_export

PROJECT = Path(__file__).resolve().parents[1]

JAVA = SearchProfile(
    positive_keywords=("java", "spring boot", "backend", "api rest", "docker", "sql"),
    seniority_levels=("estagio", "junior"),
    location_scopes=("remoto-brasil", "sao-carlos-sp"),
    excluded_terms=("senior", "especialista"),
)
PYTHON = SearchProfile(
    positive_keywords=("python", "django", "backend"),
    seniority_levels=("junior",),
    location_scopes=("remoto-brasil",),
)
ONLY_BACKEND = SearchProfile(
    positive_keywords=("backend",),
    seniority_levels=("junior",),
    location_scopes=("remoto-brasil",),
)


def _record(title: str, description: str | None = None, **extra) -> VacancyRecord:
    values = dict(
        source="primeiravagatech",
        source_job_id="1",
        canonical_url="https://jobs.example.com/1",
        title=title,
        company="Acme",
        description_summary=description,
        location="Remoto",
        remote_scope="Brasil",
        workplace_model=WorkplaceModel.REMOTE,
    )
    values.update(extra)
    return VacancyRecord(**values)


def _labels(record: VacancyRecord, profile: SearchProfile = JAVA) -> tuple[str, ...]:
    return classify(record, profile, default_country="BR").match_labels


@pytest.mark.parametrize(
    ("title", "stack"),
    [
        ("Desenvolvedor Backend Júnior Remoto (Python)", "python"),
        ("Desenvolvedora Backend Júnior .Net Remoto", ".net"),
        ("Desenvolvedor Backend Júnior Node.js Remoto", "node.js"),
        ("Desenvolvedor PHP Júnior", "php"),
        ("Front-end Júnior React", "react"),
    ],
)
def test_other_stack_backend_job_is_not_ready_for_java_profile(title: str, stack: str) -> None:
    labels = _labels(_record(title))

    assert "FIT:OTHER_STACK" in labels
    assert f"OTHER_STACK:{stack}" in labels
    assert "FIT:READY" not in labels and "FIT:CONDITIONAL" not in labels


def test_other_stack_found_in_description_of_generic_title() -> None:
    labels = _labels(_record("Engenheiro de Software Júnior", "Atuar com Python e Django."))

    assert "FIT:OTHER_STACK" in labels
    assert "OTHER_STACK:python" in labels


@pytest.mark.parametrize(
    ("title", "description"),
    [
        ("Desenvolvedor Backend Júnior", None),
        ("Estágio em Desenvolvimento Backend Remoto", "Venha crescer com a gente."),
        ("Analista de Sistemas Júnior", None),
    ],
)
def test_generic_title_without_any_stack_stays_ambiguous(title: str, description) -> None:
    labels = _labels(_record(title, description))

    assert "FIT:AMBIGUOUS" in labels
    assert not any(label.startswith("OTHER_STACK:") for label in labels)


def test_own_stack_wins_even_when_other_stack_is_mentioned() -> None:
    labels = _labels(
        _record("Desenvolvedor Java Júnior", "Spring Boot. Python é um diferencial.")
    )

    assert "FIT:READY" in labels
    assert not any(label.startswith("OTHER_STACK:") for label in labels)


def test_exclusion_wins_over_other_stack() -> None:
    labels = _labels(_record("Desenvolvedor Python Sênior"))

    assert "FIT:EXCLUDE" in labels


def test_java_is_other_stack_for_python_profile_and_javascript_is_not_java() -> None:
    java_for_python = classify(
        _record("Desenvolvedor Java Júnior"), PYTHON, default_country="BR"
    ).match_labels
    js_for_java = _labels(_record("Desenvolvedor JavaScript Júnior"))

    assert "OTHER_STACK:java" in java_for_python
    assert "FIT:OTHER_STACK" in js_for_java
    assert "OTHER_STACK:javascript" in js_for_java
    assert "TECH_MATCH:java" not in js_for_java


def test_profile_with_only_generic_terms_keeps_backend_as_its_stack() -> None:
    labels = classify(
        _record("Desenvolvedor Backend Python Júnior"), ONLY_BACKEND, default_country="BR"
    ).match_labels

    assert "FIT:READY" in labels
    assert not any(label.startswith("OTHER_STACK:") for label in labels)


def test_other_stack_score_does_not_count_the_technology_point() -> None:
    labels = _labels(_record("Desenvolvedor Backend Júnior Remoto (Python)"))

    # nível + local + (sem modelo exigido) = 2; "backend" não vale ponto de tecnologia
    assert "FIT_SCORE:2" in labels


def test_curated_articles_stay_ambiguous() -> None:
    labels = _labels(_record("Vagas de Python para iniciantes", source="otrainee"))

    assert "FIT:AMBIGUOUS" in labels


def test_reclassify_replaces_other_stack_labels() -> None:
    payload = {
        "source": "gupy",
        "canonical_url": "https://x.com/1",
        "title": "Desenvolvedor Python Júnior",
        "company": "Acme",
        "location": "Remoto",
        "remote_scope": "Brasil",
        "workplace_model": "REMOTE",
        "match_labels": ["FIT:OTHER_STACK", "OTHER_STACK:python", "STATUS:NEW"],
    }

    (updated,) = reclassify_payloads([payload], PYTHON, {"gupy": "BR"})

    assert fit_state(updated) == "READY"
    assert not any(label.startswith("OTHER_STACK:") for label in updated["match_labels"])
    assert "STATUS:NEW" in updated["match_labels"]


def test_panel_filter_and_reason_for_other_stack() -> None:
    other = {"match_labels": ["FIT:OTHER_STACK", "OTHER_STACK:python"], "source": "x"}
    ready = {"match_labels": ["FIT:READY"], "source": "x"}

    assert fit_reasons(other) == ["stack diferente da sua (python)"]
    assert filter_jobs_for_export([other, ready], match="otherstack") == [other]
    assert filter_jobs_for_export([other, ready], match="review") == []
    assert filter_jobs_for_export([other, ready], match="") == [other, ready]


def test_markdown_report_has_other_stack_section() -> None:
    from job_radar.export_document import build_markdown_report

    text = build_markdown_report(
        [{"title": "Dev Python", "match_labels": ["FIT:OTHER_STACK"]}], generated_at="hoje"
    )

    assert "## Outra stack (1)" in text


def test_real_sample_backend_jobs_of_other_stacks_leave_ready() -> None:
    sample = [
        json.loads(line)
        for line in (PROJECT / "tests" / "fixtures" / "amostra-real-2026-10-01.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    titles = {
        "Desenvolvedor Backend Júnior Remoto (Python)",
        "Desenvolvedora Backend Júnior .Net Remoto",
        "Desenvolvedor Backend Júnior Node.js Remoto",
    }
    chosen = [payload for payload in sample if payload["title"] in titles]

    updated = reclassify_payloads(chosen, JAVA, {"primeiravagatech": "BR"})

    assert len(updated) == len(titles)
    assert {fit_state(payload) for payload in updated} == {"OTHER_STACK"}


def test_dashboard_shows_other_stack_pill_reason_and_filter(tmp_path: Path) -> None:
    from threading import Thread

    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    output.mkdir()
    jobs = [
        {
            "title": "Dev Python Júnior",
            "company": "Py Co",
            "canonical_url": "https://example.com/python",
            "source": "example",
            "match_labels": ["FIT:OTHER_STACK", "FIT_SCORE:2", "OTHER_STACK:python"],
        },
        {
            "title": "Dev Java Júnior",
            "company": "Acme",
            "canonical_url": "https://example.com/java",
            "source": "example",
            "match_labels": ["FIT:READY", "FIT_SCORE:3"],
        },
    ]
    (output / "vagas.jsonl").write_text(
        "".join(json.dumps(job) + "\n" for job in jobs), encoding="utf-8"
    )
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

            titles = page.locator("#jobs-table-body .job-title").all_inner_texts()
            python_row = page.locator("#jobs-table-body tr").filter(has_text="Dev Python")
            assert titles == ["Dev Java Júnior", "Dev Python Júnior"]
            assert "Outra stack" in python_row.inner_text()
            assert "stack diferente da sua (python)" in python_row.inner_text()

            page.locator("#match-filter").select_option("otherstack")
            assert page.locator("#jobs-table-body .job-title").all_inner_texts() == [
                "Dev Python Júnior"
            ]
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
