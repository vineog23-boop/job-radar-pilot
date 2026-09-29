from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from scrapling.parser import Adaptor

from job_radar.adaptive import AdaptiveCardLocator
from job_radar.fetching import FetchResult
from job_radar.models import (
    CollectionStatus,
    SearchProfile,
    SourceConfig,
    SourceKind,
    SourceRunResult,
    VacancyRecord,
    WorkplaceModel,
)
from job_radar.pipeline import JobRadarPipeline, _combine_query_results


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


def test_pipeline_retries_dynamic_layout_once_for_transient_rendering() -> None:
    source = replace(_source("dynamic"), kind=SourceKind.DYNAMIC)
    calls = 0

    class TransientDynamicAdapter:
        def collect(self, config: SourceConfig, fetcher: object) -> SourceRunResult:
            nonlocal calls
            calls += 1
            if calls == 1:
                return SourceRunResult(
                    config.code,
                    CollectionStatus.ERROR,
                    stop_reason="LAYOUT_CHANGED",
                )
            return SourceRunResult(
                config.code,
                CollectionStatus.PARTIAL,
                (_record(config.code, "https://ats.example.com/recovered"),),
                stop_reason="PAGINATION_UNVERIFIED",
            )

    result = JobRadarPipeline(
        (source,),
        PROFILE,
        fetcher=object(),
        adapter_factory=lambda config: TransientDynamicAdapter(),
    ).run()

    assert calls == 2
    assert result.source_results[0].status is CollectionStatus.PARTIAL
    assert len(result.records) == 1


def test_pipeline_sweeps_supported_search_queries_and_combines_one_source_result() -> None:
    source = replace(
        _source("indeed"),
        kind=SourceKind.INDEED,
        start_url="https://br.indeed.com/jobs?q=java+junior",
        queries=("java junior", "estagio desenvolvimento"),
    )
    calls: list[str] = []

    class QueryAdapter:
        def collect(self, config: SourceConfig, fetcher: object) -> SourceRunResult:
            calls.append(config.start_url)
            suffix = str(len(calls))
            return SourceRunResult(
                config.code,
                CollectionStatus.SUCCESS,
                (_record(config.code, f"https://ats.example.com/{suffix}"),),
                pages_observed=1,
                cards_observed=1,
                visited_urls=(config.start_url,),
            )

    result = JobRadarPipeline(
        (source,),
        PROFILE,
        fetcher=object(),
        adapter_factory=lambda config: QueryAdapter(),
    ).run()

    assert calls == [
        "https://br.indeed.com/jobs?q=java+junior",
        "https://br.indeed.com/jobs?q=estagio+desenvolvimento",
    ]
    assert len(result.source_results) == 1
    assert result.source_results[0].status is CollectionStatus.SUCCESS
    assert result.source_results[0].pages_observed == 2
    assert len(result.source_results[0].records) == 2


@pytest.mark.parametrize(
    "stop_reason",
    [
        "LOGIN_REQUIRED",
        "TWO_FACTOR",
        "CAPTCHA",
        "ACTIVITY_ALERT",
        "RATE_LIMITED",
        "ACCESS_DENIED",
    ],
)
def test_indeed_query_sweep_stops_after_interactive_block(stop_reason: str) -> None:
    source = replace(
        _source("indeed"),
        kind=SourceKind.INDEED,
        start_url="https://br.indeed.com/jobs?q=java",
        queries=("java", "spring", "backend"),
    )
    profile = replace(PROFILE, search_terms=("java", "spring", "backend"))
    calls: list[str] = []

    class BlockedAdapter:
        def collect(self, config: SourceConfig, fetcher: object) -> SourceRunResult:
            calls.append(config.start_url)
            return SourceRunResult(
                config.code,
                CollectionStatus.BLOCKED,
                stop_reason=stop_reason,
                visited_urls=(config.start_url,),
            )

    result = JobRadarPipeline(
        (source,),
        profile,
        fetcher=object(),
        adapter_factory=lambda config: BlockedAdapter(),
    ).run()

    assert calls == ["https://br.indeed.com/jobs?q=java"]
    assert result.source_results[0].stop_reason == stop_reason


def test_indeed_block_mid_sweep_preserves_records_and_stays_partial() -> None:
    source = replace(
        _source("indeed"),
        kind=SourceKind.INDEED,
        start_url="https://br.indeed.com/jobs?q=java",
        queries=("java", "spring", "backend"),
    )
    profile = replace(PROFILE, search_terms=("java", "spring", "backend"))
    calls: list[str] = []

    class MixedAdapter:
        def collect(self, config: SourceConfig, fetcher: object) -> SourceRunResult:
            calls.append(config.start_url)
            if len(calls) == 1:
                return SourceRunResult(
                    config.code,
                    CollectionStatus.SUCCESS,
                    (_record(config.code, "https://ats.example.com/java-1"),),
                    pages_observed=1,
                    cards_observed=1,
                    visited_urls=(config.start_url,),
                )
            return SourceRunResult(
                config.code,
                CollectionStatus.BLOCKED,
                stop_reason="LOGIN_REQUIRED",
                visited_urls=(config.start_url,),
            )

    result = JobRadarPipeline(
        (source,),
        profile,
        fetcher=object(),
        adapter_factory=lambda config: MixedAdapter(),
    ).run()

    source_result = result.source_results[0]
    assert calls == [
        "https://br.indeed.com/jobs?q=java",
        "https://br.indeed.com/jobs?q=spring",
    ]
    assert source_result.status is CollectionStatus.PARTIAL
    assert source_result.stop_reason == "QUERY_SWEEP_PARTIAL"
    assert len(source_result.records) == 1


def test_pipeline_prefers_editable_search_terms_for_supported_search_sources() -> None:
    sources = (
        replace(
            _source("gupy"),
            kind=SourceKind.GUPY,
            start_url="https://portal.gupy.io/job-search/term%3Dconfig-antiga",
            queries=("config antiga",),
        ),
        replace(
            _source("indeed"),
            kind=SourceKind.INDEED,
            start_url="https://br.indeed.com/jobs?q=config+antiga",
            queries=("config antiga",),
        ),
        replace(
            _source("casado-dev"),
            start_url="https://casado.dev/vagas?search=config+antiga",
            queries=("config antiga",),
        ),
    )
    profile = replace(PROFILE, search_terms=("java remoto junior", "estagio backend"))
    calls: list[str] = []

    class QueryAdapter:
        def collect(self, config: SourceConfig, fetcher: object) -> SourceRunResult:
            calls.append(config.start_url)
            return SourceRunResult(config.code, CollectionStatus.EMPTY)

    JobRadarPipeline(
        sources,
        profile,
        fetcher=object(),
        adapter_factory=lambda config: QueryAdapter(),
    ).run()

    assert calls == [
        "https://portal.gupy.io/job-search/term%3Djava%20remoto%20junior",
        "https://portal.gupy.io/job-search/term%3Destagio%20backend",
        "https://br.indeed.com/jobs?q=java+remoto+junior",
        "https://br.indeed.com/jobs?q=estagio+backend",
        "https://casado.dev/vagas?search=java+remoto+junior",
        "https://casado.dev/vagas?search=estagio+backend",
    ]


def test_pipeline_builds_casado_dev_search_urls() -> None:
    source = replace(
        _source("casado-dev"),
        start_url="https://casado.dev/vagas",
        queries=("java", "spring boot"),
    )
    calls: list[str] = []

    class EmptyAdapter:
        def collect(self, config: SourceConfig, fetcher: object) -> SourceRunResult:
            calls.append(config.start_url)
            return SourceRunResult(config.code, CollectionStatus.EMPTY)

    JobRadarPipeline(
        (source,),
        PROFILE,
        fetcher=object(),
        adapter_factory=lambda config: EmptyAdapter(),
    ).run()

    assert calls == [
        "https://casado.dev/vagas?search=java",
        "https://casado.dev/vagas?search=spring+boot",
    ]


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


def test_pipeline_propagates_partial_source_status_to_its_records() -> None:
    source = _source("partial")
    record = _record("partial", "https://ats.example.com/jobs/partial")
    pipeline = JobRadarPipeline(
        (source,),
        PROFILE,
        fetcher=object(),
        adapter_factory=lambda config: StaticAdapter(
            SourceRunResult(
                config.code,
                CollectionStatus.PARTIAL,
                (record,),
                stop_reason="PAGINATION_UNVERIFIED",
            )
        ),
    )

    result = pipeline.run()

    assert result.records[0].collection_status is CollectionStatus.PARTIAL


def test_pipeline_propagates_source_default_country_to_classifier() -> None:
    source = replace(_source("brazilian"), default_country="BR")
    record = replace(
        _record("brazilian", "https://ats.example.com/jobs/remote"),
        location="Remoto",
        workplace_model=WorkplaceModel.REMOTE,
    )
    pipeline = JobRadarPipeline(
        (source,),
        PROFILE,
        fetcher=object(),
        adapter_factory=lambda config: StaticAdapter(
            SourceRunResult(config.code, CollectionStatus.SUCCESS, (record,))
        ),
    )

    result = pipeline.run()

    assert "LOCATION_MATCH:remote_brazil" in result.records[0].match_labels
    assert "FIT:READY" in result.records[0].match_labels


def test_pipeline_preserves_adaptive_label_with_source_default_country() -> None:
    source = replace(_source("brazilian"), default_country="BR")
    record = replace(
        _record("brazilian", "https://ats.example.com/jobs/adaptive-remote"),
        location="Remoto",
        workplace_model=WorkplaceModel.REMOTE,
        match_labels=("EXTRACTION:ADAPTIVE",),
    )
    result = JobRadarPipeline(
        (source,),
        PROFILE,
        fetcher=object(),
        adapter_factory=lambda config: StaticAdapter(
            SourceRunResult(config.code, CollectionStatus.PARTIAL, (record,))
        ),
    ).run()

    assert "EXTRACTION:ADAPTIVE" in result.records[0].match_labels
    assert "LOCATION_MATCH:remote_brazil" in result.records[0].match_labels


def test_combine_query_results_stably_deduplicates_warnings_and_keeps_severity() -> None:
    source = replace(
        _source("indeed"),
        kind=SourceKind.INDEED,
        queries=("java", "spring"),
    )
    results = (
        SourceRunResult(
            "indeed",
            CollectionStatus.PARTIAL,
            (_record("indeed", "https://ats.example.com/jobs/1"),),
            stop_reason="SELECTOR_RELOCATED",
            warnings=("SELECTOR_RELOCATED:card",),
        ),
        SourceRunResult(
            "indeed",
            CollectionStatus.BLOCKED,
            stop_reason="LOGIN_REQUIRED",
            warnings=("SELECTOR_RELOCATED:card", "SECOND_WARNING"),
        ),
    )

    combined = _combine_query_results(source, results)

    assert combined.status is CollectionStatus.PARTIAL
    assert combined.stop_reason == "QUERY_SWEEP_PARTIAL"
    assert combined.warnings == ("SELECTOR_RELOCATED:card", "SECOND_WARNING")


def test_combine_complete_empty_queries_with_warning_is_partial() -> None:
    source = replace(
        _source("indeed"),
        kind=SourceKind.INDEED,
        queries=("java", "spring"),
    )
    results = (
        SourceRunResult(
            "indeed",
            CollectionStatus.SUCCESS,
            warnings=("SELECTOR_RELOCATED:card",),
        ),
        SourceRunResult("indeed", CollectionStatus.EMPTY),
    )

    combined = _combine_query_results(source, results)

    assert combined.status is CollectionStatus.PARTIAL
    assert combined.stop_reason == "SELECTOR_RELOCATED"
    assert combined.records == ()
    assert combined.warnings == ("SELECTOR_RELOCATED:card",)


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


def test_pipeline_preserves_page_limit_and_pagination_loop(tmp_path) -> None:
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
        adaptive_locator=AdaptiveCardLocator(tmp_path / "adaptive.db"),
    )

    result = pipeline.run()

    assert [item.stop_reason for item in result.source_results] == [
        "PAGE_LIMIT",
        "PAGINATION_LOOP",
    ]
    assert all(item.status is CollectionStatus.PARTIAL for item in result.source_results)
