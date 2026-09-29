from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from scrapling.parser import Adaptor

from job_radar.fetching import FetchResult
from job_radar.models import (
    CollectionStatus,
    SearchProfile,
    SourceConfig,
    SourceKind,
    SourceRunResult,
    VacancyRecord,
)
from job_radar.pipeline import JobRadarPipeline


PROFILE = SearchProfile(
    positive_keywords=("java", "spring boot"),
    seniority_levels=("junior", "estagio"),
    location_scopes=("sao-carlos-sp",),
    excluded_terms=("senior",),
)


def _source(code: str, *, max_pages: int = 3) -> SourceConfig:
    return SourceConfig(
        code=code,
        kind=SourceKind.GENERIC,
        start_url=f"https://{code}.example.com/jobs",
        enabled=True,
        max_pages=max_pages,
        min_interval_seconds=1,
        requires_auth=False,
        selectors={
            "card": "article",
            "title": "h2",
            "url": "a::attr(href)",
            "next": "a.next::attr(href)",
        },
    )


def _record(source: str, url: str, title: str = "Java Junior") -> VacancyRecord:
    return VacancyRecord(
        source=source,
        source_job_id=None,
        canonical_url=url,
        title=title,
        company="Acme",
        location="São Carlos, SP",
    )


class StaticAdapter:
    def __init__(self, result: SourceRunResult | Exception) -> None:
        self.result = result

    def collect(self, config: SourceConfig, fetcher: object) -> SourceRunResult:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_pipeline_isolates_success_block_empty_and_adapter_error() -> None:
    sources = tuple(_source(code) for code in ("ok", "blocked", "empty", "broken"))
    results = {
        "ok": SourceRunResult(
            "ok", CollectionStatus.SUCCESS, (_record("ok", "https://ats.test/1"),)
        ),
        "blocked": SourceRunResult(
            "blocked", CollectionStatus.BLOCKED, stop_reason="CAPTCHA"
        ),
        "empty": SourceRunResult("empty", CollectionStatus.EMPTY),
        "broken": RuntimeError("cookie=secret <html>full body</html>"),
    }
    pipeline = JobRadarPipeline(
        sources,
        PROFILE,
        fetcher=object(),
        adapter_factory=lambda config: StaticAdapter(results[config.code]),
    )

    result = pipeline.run()

    assert [item.status for item in result.source_results] == [
        CollectionStatus.SUCCESS,
        CollectionStatus.BLOCKED,
        CollectionStatus.EMPTY,
        CollectionStatus.ERROR,
    ]
    assert result.source_results[-1].errors == ("Falha interna no adaptador broken",)
    assert result.raw_record_count == 1
    assert len(result.records) == 1
    assert "TECH_MATCH:java" in result.records[0].match_labels


def test_pipeline_filters_sources_and_rejects_unknown_codes() -> None:
    sources = (_source("one"), _source("two"))
    calls: list[str] = []

    class RecordingAdapter:
        def collect(self, config: SourceConfig, fetcher: object) -> SourceRunResult:
            calls.append(config.code)
            return SourceRunResult(config.code, CollectionStatus.EMPTY)

    pipeline = JobRadarPipeline(
        sources,
        PROFILE,
        fetcher=object(),
        adapter_factory=lambda config: RecordingAdapter(),
    )

    result = pipeline.run(["two"])

    assert calls == ["two"]
    assert [item.source_code for item in result.source_results] == ["two"]
    with pytest.raises(ValueError, match="unknown"):
        pipeline.run(["unknown"])


def test_pipeline_deduplicates_across_sources_and_reconciles_counts() -> None:
    sources = (_source("one"), _source("two"))
    shared_url = "https://ats.example.com/jobs/42"
    results = {
        "one": SourceRunResult(
            "one", CollectionStatus.SUCCESS, (_record("one", shared_url),)
        ),
        "two": SourceRunResult(
            "two", CollectionStatus.SUCCESS, (_record("two", shared_url),)
        ),
    }
    pipeline = JobRadarPipeline(
        sources,
        PROFILE,
        fetcher=object(),
        adapter_factory=lambda config: StaticAdapter(results[config.code]),
    )

    result = pipeline.run()

    assert result.raw_record_count == 2
    assert len(result.records) == 1
    assert result.duplicate_count == 1
    assert len(result.ambiguous) == 0
    assert result.raw_record_count == (
        len(result.records) + result.duplicate_count + len(result.ambiguous)
    )


class HtmlFetcher:
    def __init__(self, documents: dict[str, str]) -> None:
        self.documents = documents

    def fetch(self, url: str, source: SourceConfig) -> FetchResult:
        html = self.documents[url]
        adaptor = Adaptor(html, url=url)
        page = SimpleNamespace(
            status=200,
            text=html,
            url=url,
            css=adaptor.css,
            urljoin=adaptor.urljoin,
        )
        return FetchResult(CollectionStatus.SUCCESS, response=page, attempts=1)


def test_pipeline_preserves_page_limit_and_pagination_loop() -> None:
    limited = _source("limited", max_pages=1)
    looped = _source("looped", max_pages=3)
    limited_url = limited.start_url
    looped_url = looped.start_url
    documents = {
        limited_url: "<article><a href='/1'><h2>Java Junior</h2></a></article><a class='next' href='/page-2'>Next</a>",
        looped_url: "<article><a href='/2'><h2>Estagio Java</h2></a></article><a class='next' href='/jobs'>Next</a>",
    }
    pipeline = JobRadarPipeline(
        (limited, looped),
        PROFILE,
        fetcher=HtmlFetcher(documents),
    )

    result = pipeline.run()

    assert [item.stop_reason for item in result.source_results] == [
        "PAGE_LIMIT",
        "PAGINATION_LOOP",
    ]
    assert all(item.status is CollectionStatus.PARTIAL for item in result.source_results)
