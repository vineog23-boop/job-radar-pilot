from __future__ import annotations

from job_radar.identity import canonicalize_url, deduplicate, identity_key
from job_radar.models import VacancyRecord


def _record(
    *,
    source_job_id: str | None = None,
    url: str = "https://jobs.example.com/vaga/123",
    title: str | None = "Pessoa Desenvolvedora Java",
    company: str | None = "Acme",
    location: str | None = "São Carlos, SP",
) -> VacancyRecord:
    return VacancyRecord(
        source="example",
        source_job_id=source_job_id,
        canonical_url=url,
        title=title,
        company=company,
        location=location,
    )


def test_canonicalize_url_removes_tracking_tokens_and_fragment() -> None:
    raw = (
        "https://Jobs.Example.com/vaga/123?utm_source=email&jobId=123"
        "&token=secret&utm_campaign=weekly#details"
    )

    assert canonicalize_url(raw) == "https://jobs.example.com/vaga/123?jobId=123"


def test_identity_prefers_source_job_id_then_url_then_fallback() -> None:
    assert identity_key(_record(source_job_id="ABC-123")) == (
        "SOURCE_JOB_ID",
        "example:ABC-123",
    )
    assert identity_key(_record()) == (
        "CANONICAL_URL",
        "https://jobs.example.com/vaga/123",
    )

    kind, value = identity_key(_record(url=""))
    assert kind == "FALLBACK_HASH"
    assert len(value) == 64


def test_deduplicate_collapses_equivalent_urls_and_marks_fallback_weak() -> None:
    first = _record(url="https://jobs.example.com/vaga/123?utm_source=alert")
    duplicate = _record(url="https://jobs.example.com/vaga/123#apply")
    weak = _record(url="", title="Java Junior", company="Acme")

    result = deduplicate([first, duplicate, weak])

    assert len(result.unique) == 2
    assert result.duplicate_count == 1
    assert result.ambiguous == ()
    assert result.unique[1].identity_strength == "WEAK"


def test_deduplicate_preserves_conflicting_job_ids_as_ambiguous() -> None:
    first = _record(source_job_id="A", url="https://jobs.example.com/vaga/123")
    conflicting = _record(source_job_id="B", url="https://jobs.example.com/vaga/123")

    result = deduplicate([first, conflicting])

    assert result.unique == ()
    assert result.duplicate_count == 0
    assert result.ambiguous == (first, conflicting)
