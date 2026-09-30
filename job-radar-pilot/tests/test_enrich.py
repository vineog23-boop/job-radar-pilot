from __future__ import annotations

from types import SimpleNamespace

from job_radar.enrich import enrich_records
from job_radar.fetching import FetchResult
from job_radar.models import CollectionStatus, SourceConfig, SourceKind, VacancyRecord


def _source(code="gupy", auth=False):
    return SourceConfig(
        code=code, kind=SourceKind.GENERIC, start_url="https://x.com.br/v",
        enabled=True, max_pages=1, min_interval_seconds=1, requires_auth=auth,
    )


def _record(code="gupy", title="Vaga"):
    return VacancyRecord(
        source=code, source_job_id="1", canonical_url=f"https://x.com.br/{code}/1",
        title=title, company=None, description_summary=None, location=None,
        observed_at="2026-09-29T00:00:00+00:00", evidence_snippets=(),
    )


class _Fetcher:
    def __init__(self):
        self.urls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def fetch(self, url, source):
        self.urls.append(url)
        html = "<html><body><p>" + "Requisitos Java Spring Boot junior remoto Brasil. " * 5 + "</p></body></html>"
        return FetchResult(status=CollectionStatus.SUCCESS, response=SimpleNamespace(body=html.encode(), status=200, url=url))


def _classify(record):
    labels = ("FIT:CONDITIONAL", "TECH_MATCH:java") if record.title == "duvidosa" else ("FIT:EXCLUDE",)
    return record.__class__(**{**record.__dict__, "match_labels": labels}) if False else _with(record, labels)


def _with(record, labels):
    from dataclasses import replace
    return replace(record, match_labels=labels)


def test_only_doubtful_records_are_fetched_and_limited() -> None:
    fetcher = _Fetcher()
    records = [_record(title="duvidosa"), _record(title="outra")]
    result, count = enrich_records(records, _classify, [_source()], limit=5, fetcher_factory=lambda: fetcher)
    assert count == 1 and len(fetcher.urls) == 1
    assert "ENRICHED:DETAIL" in result[0].match_labels
    assert "Requisitos Java" in (result[0].description_summary or "")
    assert result[1].description_summary is None


def test_limit_zero_and_indeed_and_auth_are_skipped() -> None:
    fetcher = _Fetcher()
    rec = [_record(code="indeed", title="duvidosa")]
    assert enrich_records(rec, _classify, [_source("indeed")], limit=5, fetcher_factory=lambda: fetcher)[1] == 0
    assert enrich_records([_record(title="duvidosa")], _classify, [_source()], limit=0, fetcher_factory=lambda: fetcher)[1] == 0
    assert enrich_records([_record(title="duvidosa")], _classify, [_source(auth=True)], limit=5, fetcher_factory=lambda: fetcher)[1] == 0
    assert fetcher.urls == []


# --- Revisão 29/09/2026: metadados da página de detalhe ---------------------


def test_extract_detail_metadata_reads_json_ld_date_and_company() -> None:
    from job_radar.enrich import extract_detail_metadata

    html = (
        '<html><head><script type="application/ld+json">'
        '{"@type":"JobPosting","datePosted":"2026-09-20",'
        '"hiringOrganization":{"@type":"Organization","name":"Acme Ltda"}}'
        "</script></head><body></body></html>"
    )

    metadata = extract_detail_metadata(html)

    assert metadata.company == "Acme Ltda"
    assert metadata.published_at is not None
    assert metadata.published_at.startswith("2026-09-20")


def test_extract_detail_metadata_without_signals_returns_empty() -> None:
    from job_radar.enrich import extract_detail_metadata

    metadata = extract_detail_metadata("<html><body><p>Sem dados</p></body></html>")

    assert metadata.company is None
    assert metadata.published_at is None


def test_off_topic_records_are_never_fetched() -> None:
    fetcher = _Fetcher()

    def classify_off_topic(record):
        return _with(record, ("FIT:AMBIGUOUS", "RELEVANCE:OFF_TOPIC"))

    result, count = enrich_records(
        [_record(title="Auxiliar")],
        classify_off_topic,
        [_source()],
        limit=5,
        fetcher_factory=lambda: fetcher,
    )

    assert count == 0
    assert fetcher.urls == []
