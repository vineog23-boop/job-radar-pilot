from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Sequence
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from job_radar.classifier import classify
from job_radar.fetching import FetchPolicy
from job_radar.identity import deduplicate
from job_radar.models import (
    CollectionStatus,
    SearchProfile,
    SourceConfig,
    SourceKind,
    SourceRunResult,
    VacancyRecord,
)
from job_radar.sources import SourceAdapter, adapter_for


@dataclass(frozen=True, slots=True)
class PipelineResult:
    started_at: str
    finished_at: str
    records: tuple[VacancyRecord, ...]
    ambiguous: tuple[VacancyRecord, ...]
    source_results: tuple[SourceRunResult, ...]
    raw_record_count: int
    duplicate_count: int


def _search_urls(source: SourceConfig) -> tuple[str, ...]:
    supports_queries = source.kind in {SourceKind.GUPY, SourceKind.INDEED} or (
        source.code == "casado-dev"
    )
    if not source.queries or not supports_queries:
        return (source.start_url,)

    parsed = urlsplit(source.start_url)
    urls: list[str] = []
    for query in source.queries:
        if source.kind is SourceKind.GUPY:
            url = urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc,
                    f"/job-search/term%3D{quote(query, safe='')}",
                    "",
                    "",
                )
            )
        else:
            query_key = "search" if source.code == "casado-dev" else "q"
            parameters = [
                (key, value)
                for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                if key not in {query_key, "start", "page"}
            ]
            parameters.append((query_key, query))
            url = urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    urlencode(parameters),
                    "",
                )
            )
        if url not in urls:
            urls.append(url)
    return tuple(urls) or (source.start_url,)


def _combine_query_results(
    source: SourceConfig, results: Sequence[SourceRunResult]
) -> SourceRunResult:
    if len(results) == 1:
        return results[0]

    records = tuple(record for result in results for record in result.records)
    statuses = {result.status for result in results}
    complete = {CollectionStatus.SUCCESS, CollectionStatus.EMPTY}
    if statuses <= complete:
        status = CollectionStatus.SUCCESS if records else CollectionStatus.EMPTY
    elif records:
        status = CollectionStatus.PARTIAL
    elif CollectionStatus.AUTH_REQUIRED in statuses:
        status = CollectionStatus.AUTH_REQUIRED
    elif CollectionStatus.BLOCKED in statuses:
        status = CollectionStatus.BLOCKED
    else:
        status = CollectionStatus.ERROR

    return SourceRunResult(
        source_code=source.code,
        status=status,
        records=records,
        pages_observed=sum(result.pages_observed for result in results),
        cards_observed=sum(result.cards_observed for result in results),
        has_more=any(result.has_more for result in results),
        stop_reason=(None if status in complete else "QUERY_SWEEP_PARTIAL"),
        errors=tuple(error for result in results for error in result.errors),
        visited_urls=tuple(url for result in results for url in result.visited_urls),
    )


class JobRadarPipeline:
    def __init__(
        self,
        sources: Sequence[SourceConfig],
        profile: SearchProfile,
        *,
        fetcher: FetchPolicy,
        adapter_factory: Callable[[SourceConfig], SourceAdapter] = adapter_for,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._sources = tuple(sources)
        self._profile = profile
        self._fetcher = fetcher
        self._adapter_factory = adapter_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def run(self, source_codes: Sequence[str] | None = None) -> PipelineResult:
        started_at = self._now().isoformat()
        configured_codes = {source.code for source in self._sources}
        requested_codes = set(source_codes) if source_codes is not None else None
        if requested_codes is not None:
            unknown = requested_codes - configured_codes
            if unknown:
                raise ValueError(f"Codigos de fonte desconhecidos: {sorted(unknown)}")

        selected = tuple(
            source
            for source in self._sources
            if source.enabled
            and (requested_codes is None or source.code in requested_codes)
        )
        source_results: list[SourceRunResult] = []
        raw_records: list[VacancyRecord] = []

        for source in selected:
            query_results: list[SourceRunResult] = []
            supports_editable_terms = source.kind in {
                SourceKind.GUPY,
                SourceKind.INDEED,
            } or source.code == "casado-dev"
            search_source = (
                replace(source, queries=self._profile.search_terms)
                if self._profile.search_terms and supports_editable_terms
                else source
            )
            adapter = self._adapter_factory(search_source)
            for search_url in _search_urls(search_source):
                query_source = replace(source, start_url=search_url, queries=())
                try:
                    query_result = adapter.collect(query_source, self._fetcher)
                    if (
                        source.kind is SourceKind.DYNAMIC
                        and query_result.status is CollectionStatus.ERROR
                        and query_result.stop_reason == "LAYOUT_CHANGED"
                    ):
                        query_result = adapter.collect(query_source, self._fetcher)
                except Exception:
                    query_result = SourceRunResult(
                        source_code=source.code,
                        status=CollectionStatus.ERROR,
                        stop_reason="ADAPTER_ERROR",
                        errors=(f"Falha interna no adaptador {source.code}",),
                    )
                query_results.append(query_result)
            result = _combine_query_results(source, query_results)
            source_results.append(result)
            raw_records.extend(
                replace(record, collection_status=result.status)
                for record in result.records
            )

        classified = tuple(classify(record, self._profile) for record in raw_records)
        deduplicated = deduplicate(classified)
        return PipelineResult(
            started_at=started_at,
            finished_at=self._now().isoformat(),
            records=deduplicated.unique,
            ambiguous=deduplicated.ambiguous,
            source_results=tuple(source_results),
            raw_record_count=len(raw_records),
            duplicate_count=deduplicated.duplicate_count,
        )
