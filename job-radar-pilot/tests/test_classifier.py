from __future__ import annotations

from job_radar.classifier import classify
from job_radar.models import SearchProfile, VacancyRecord, WorkplaceModel


PROFILE = SearchProfile(
    positive_keywords=("java", "spring boot", "api rest"),
    seniority_levels=("estagio", "junior"),
    location_scopes=("remoto-brasil", "sao-carlos-sp"),
    excluded_terms=("senior", "especialista"),
)


def _record(**overrides: object) -> VacancyRecord:
    values: dict[str, object] = {
        "source": "example",
        "source_job_id": "123",
        "canonical_url": "https://jobs.example.com/123",
        "title": "Estágio em Desenvolvimento Java",
        "company": "Acme",
        "description_summary": "APIs com Spring Boot",
        "location": "São Carlos, SP",
        "workplace_model": WorkplaceModel.HYBRID,
        "evidence_snippets": ("Conhecimento em Java",),
        "published_at": None,
        "application_deadline": None,
    }
    values.update(overrides)
    return VacancyRecord(**values)  # type: ignore[arg-type]


def test_classify_matches_utf8_technology_seniority_and_location() -> None:
    original = _record()

    classified = classify(original, PROFILE)

    assert "TECH_MATCH:java" in classified.match_labels
    assert "TECH_MATCH:spring boot" in classified.match_labels
    assert "SENIORITY_MATCH:estagio" in classified.match_labels
    assert "LOCATION_MATCH:sao-carlos-sp" in classified.match_labels
    assert classified.evidence_snippets == original.evidence_snippets
    assert not any(label.startswith("SCORE:") for label in classified.match_labels)


def test_classify_marks_incompatible_seniority() -> None:
    classified = classify(
        _record(title="Pessoa Desenvolvedora Java Sênior"),
        PROFILE,
    )

    assert "SENIORITY_MISMATCH:senior" in classified.match_labels


def test_classify_keeps_remote_without_country_uncertain() -> None:
    classified = classify(
        _record(
            title="Java Junior remoto",
            location=None,
            workplace_model=WorkplaceModel.REMOTE,
            remote_scope=None,
        ),
        PROFILE,
    )

    assert "SENIORITY_MATCH:junior" in classified.match_labels
    assert "LOCATION_UNCLEAR:remote_scope" in classified.match_labels
    assert "LOCATION_MATCH:remote_brazil" not in classified.match_labels


def test_classify_marks_missing_location_without_inventing_dates() -> None:
    classified = classify(_record(location=None), PROFILE)

    assert "LOCATION_UNCLEAR:missing" in classified.match_labels
    assert classified.published_at is None
    assert classified.application_deadline is None
