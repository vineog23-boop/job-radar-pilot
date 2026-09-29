from __future__ import annotations

from dataclasses import replace

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


def test_canonicalize_url_removes_gupy_job_board_source() -> None:
    raw = "https://acme.gupy.io/job/TOKEN-123?jobBoardSource=gupy_portal"

    assert canonicalize_url(raw) == "https://acme.gupy.io/job/TOKEN-123"


def test_canonicalize_url_orders_equivalent_query_parameters() -> None:
    first = "https://jobs.example.com/vaga?a=1&b=2"
    second = "https://jobs.example.com/vaga?b=2&a=1"

    assert canonicalize_url(first) == canonicalize_url(second)


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


def test_deduplicate_collapses_urls_with_reordered_query_parameters() -> None:
    first = _record(url="https://jobs.example.com/vaga?a=1&b=2")
    duplicate = _record(url="https://jobs.example.com/vaga?b=2&a=1")

    result = deduplicate([first, duplicate])

    assert result.unique == (first,)
    assert result.duplicate_count == 1


def test_deduplicate_merges_only_orthogonal_extraction_provenance() -> None:
    first = replace(
        _record(),
        match_labels=(
            "FIT:READY",
            "FIT_SCORE:4",
            "LOCATION_MATCH:sao-carlos-sp",
            "TECH_MATCH:java",
        ),
    )
    duplicate = replace(
        _record(url="https://jobs.example.com/vaga/123#apply"),
        match_labels=(
            "EXTRACTION:ADAPTIVE",
            "FIT:EXCLUDE",
            "FIT_SCORE:-2",
            "LOCATION_MISMATCH:outside_scope",
            "TECH_MATCH:go",
        ),
    )

    result = deduplicate([first, duplicate])

    assert result.unique[0].match_labels == (
        "FIT:READY",
        "FIT_SCORE:4",
        "LOCATION_MATCH:sao-carlos-sp",
        "TECH_MATCH:java",
        "EXTRACTION:ADAPTIVE",
    )
    assert result.duplicate_count == 1


def test_deduplicate_preserves_conflicting_job_ids_as_ambiguous() -> None:
    first = _record(source_job_id="A", url="https://jobs.example.com/vaga/123")
    conflicting = _record(source_job_id="B", url="https://jobs.example.com/vaga/123")

    result = deduplicate([first, conflicting])

    assert result.unique == ()
    assert result.duplicate_count == 0
    assert result.ambiguous == (first, conflicting)


def test_deduplicate_preserves_exact_semantic_match_across_sources_as_possible_duplicate() -> None:
    aggregator = replace(
        _record(
            url="https://br.indeed.com/viewjob?jk=valid123",
            title="Desenvolvedor Java Júnior",
            company="Minsait",
            location="São Paulo, SP",
        ),
        source="indeed",
    )
    ats = replace(
        _record(
            url="https://minsait.gupy.io/jobs/123",
            title="Desenvolvedor Java Junior",
            company="Minsait",
            location="Sao Paulo - SP",
        ),
        source="gupy",
    )

    result = deduplicate([aggregator, ats])

    assert len(result.unique) == 2
    assert {record.source for record in result.unique} == {"gupy", "indeed"}
    assert "POSSIBLE_DUPLICATE:gupy" in result.unique[0].match_labels
    assert "POSSIBLE_DUPLICATE:indeed" in result.unique[1].match_labels
    assert result.duplicate_count == 0


def test_deduplicate_keeps_generic_titles_and_same_source_positions() -> None:
    first = replace(
        _record(source_job_id="A", url="https://ciee.example.com/vaga/A", title="Estágio", company="CIEE", location="São Paulo, SP"),
        source="ciee",
    )
    second = replace(
        _record(source_job_id="B", url="https://ciee.example.com/vaga/B", title="Estágio", company="CIEE", location="São Paulo, SP"),
        source="ciee",
    )

    result = deduplicate([first, second])

    assert result.unique == (first, second)
    assert result.duplicate_count == 0
