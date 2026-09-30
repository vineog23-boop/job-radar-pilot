from __future__ import annotations

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import Lock
from typing import Callable, Sequence
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from job_radar.adaptive import AdaptiveCardLocator
from job_radar.classifier import classify
from job_radar.fetching import FetchPolicy
from job_radar.enrich import enrich_records
from job_radar.history import SeenHistory
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


def _supports_queries(source: SourceConfig) -> bool:
    return (
        source.kind in {SourceKind.GUPY, SourceKind.INDEED}
        or source.code == "casado-dev"
        or source.query_path is not None
        or source.query_param is not None
    )


def _slugify(query: str) -> str:
    decomposed = unicodedata.normalize("NFKD", query.casefold())
    ascii_text = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")


def _search_urls(source: SourceConfig) -> tuple[str, ...]:
    supports_queries = _supports_queries(source)
    if not source.queries or not supports_queries:
        return (source.start_url,)

    parsed = urlsplit(source.start_url)
    urls: list[str] = []
    for query in source.queries:
        if source.query_path is not None:
            slug = _slugify(query)
            if not slug:
                continue
            url = urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc,
                    source.query_path.replace("{query}", slug),
                    "",
                    "",
                )
            )
        elif source.kind is SourceKind.GUPY:
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
            query_key = source.query_param or (
                "search" if source.code == "casado-dev" else "q"
            )
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
    warnings = tuple(
        dict.fromkeys(
            warning for result in results for warning in result.warnings
        )
    )
    statuses = {result.status for result in results}
    complete = {CollectionStatus.SUCCESS, CollectionStatus.EMPTY}
    if statuses <= complete:
        status = (
            CollectionStatus.PARTIAL
            if warnings
            else CollectionStatus.SUCCESS
            if records
            else CollectionStatus.EMPTY
        )
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
        stop_reason=(
            None
            if status in complete
            else "SELECTOR_RELOCATED"
            if statuses <= complete and warnings
            else "QUERY_SWEEP_PARTIAL"
        ),
        errors=tuple(error for result in results for error in result.errors),
        visited_urls=tuple(url for result in results for url in result.visited_urls),
        warnings=warnings,
    )


class JobRadarPipeline:
    def __init__(
        self,
        sources: Sequence[SourceConfig],
        profile: SearchProfile,
        *,
        fetcher: FetchPolicy | None = None,
        fetcher_factory: Callable[[], FetchPolicy] | None = None,
        workers: int = 1,
        on_source_done: Callable[[SourceRunResult], None] | None = None,
        adapter_factory: Callable[[SourceConfig], SourceAdapter] = adapter_for,
        adaptive_locator: AdaptiveCardLocator | None = None,
        now: Callable[[], datetime] | None = None,
        history: SeenHistory | None = None,
        enrich_limit: int = 0,
        enrich_fetcher_factory: Callable[[], FetchPolicy] | None = None,
    ) -> None:
        if workers < 1 or workers > 4:
            raise ValueError("workers deve estar entre 1 e 4")
        if fetcher is not None and fetcher_factory is not None:
            raise ValueError("fetcher e fetcher_factory sao mutuamente exclusivos")
        if workers > 1 and fetcher is not None:
            raise ValueError("fetcher compartilhado nao e permitido com workers > 1")
        if workers > 1 and fetcher_factory is None:
            raise ValueError("workers > 1 exige fetcher_factory")
        self._history = history
        self._enrich_limit = enrich_limit
        self._enrich_fetcher_factory = enrich_fetcher_factory or FetchPolicy
        self.enriched_count = 0
        self._sources = tuple(sources)
        self._profile = profile
        self._fetcher = fetcher
        self._fetcher_factory = fetcher_factory
        self._workers = workers
        self._on_source_done = on_source_done
        self._callback_lock = Lock()
        self._adapter_factory = adapter_factory
        self._adaptive_locator = adaptive_locator
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _notify_source_done(self, result: SourceRunResult) -> None:
        if self._on_source_done is None:
            return
        with self._callback_lock:
            try:
                self._on_source_done(result)
            except Exception:
                return

    def _collect_source(
        self,
        source: SourceConfig,
        fetcher: FetchPolicy,
        adaptive_locator: AdaptiveCardLocator,
    ) -> SourceRunResult:
        query_results: list[SourceRunResult] = []
        supports_editable_terms = _supports_queries(source)
        search_source = (
            replace(source, queries=self._profile.search_terms)
            if self._profile.search_terms
            and supports_editable_terms
            and not source.fixed_queries
            else source
        )
        try:
            adapter = (
                adapter_for(search_source, locator=adaptive_locator)
                if self._adapter_factory is adapter_for
                else self._adapter_factory(search_source)
            )
        except Exception:
            return SourceRunResult(
                source_code=source.code,
                status=CollectionStatus.ERROR,
                stop_reason="ADAPTER_ERROR",
                errors=(f"Falha interna no adaptador {source.code}",),
            )
        for search_url in _search_urls(search_source):
            query_source = replace(source, start_url=search_url, queries=())
            try:
                query_result = adapter.collect(query_source, fetcher)
                if (
                    source.kind is SourceKind.DYNAMIC
                    and query_result.status is CollectionStatus.ERROR
                    and query_result.stop_reason == "LAYOUT_CHANGED"
                ):
                    query_result = adapter.collect(query_source, fetcher)
            except Exception:
                query_result = SourceRunResult(
                    source_code=source.code,
                    status=CollectionStatus.ERROR,
                    stop_reason="ADAPTER_ERROR",
                    errors=(f"Falha interna no adaptador {source.code}",),
                )
            query_results.append(query_result)
            if source.code == "indeed" and query_result.stop_reason in {
                "LOGIN_REQUIRED",
                "TWO_FACTOR",
                "CAPTCHA",
                "ACTIVITY_ALERT",
                "RATE_LIMITED",
                "ACCESS_DENIED",
            }:
                break
        return _combine_query_results(source, query_results)

    @staticmethod
    def _worker_error(source: SourceConfig) -> SourceRunResult:
        return SourceRunResult(
            source_code=source.code,
            status=CollectionStatus.ERROR,
            stop_reason="WORKER_ERROR",
            errors=("Falha interna no worker",),
        )

    @staticmethod
    def _with_worker_error(result: SourceRunResult) -> SourceRunResult:
        return replace(
            result,
            status=(
                CollectionStatus.PARTIAL
                if result.records
                else CollectionStatus.ERROR
            ),
            stop_reason="WORKER_ERROR",
            errors=(*result.errors, "Falha interna no worker"),
        )

    @staticmethod
    def _claim_fetcher(
        fetcher: FetchPolicy,
        claimed_fetchers: list[FetchPolicy],
        claim_lock: Lock,
    ) -> bool:
        with claim_lock:
            if any(existing is fetcher for existing in claimed_fetchers):
                return False
            claimed_fetchers.append(fetcher)
            return True

    def _collect_batch(
        self,
        sources: Sequence[SourceConfig],
        adaptive_locator: AdaptiveCardLocator,
        claimed_fetchers: list[FetchPolicy] | None = None,
        claim_lock: Lock | None = None,
    ) -> tuple[SourceRunResult, ...]:
        results: list[SourceRunResult] = []
        try:
            factory = self._fetcher_factory or FetchPolicy
            fetcher_candidate = factory()
            if (
                claimed_fetchers is not None
                and claim_lock is not None
                and not self._claim_fetcher(
                    fetcher_candidate,
                    claimed_fetchers,
                    claim_lock,
                )
            ):
                raise RuntimeError("fetcher reutilizado entre workers")
            with fetcher_candidate as fetcher:
                for source in sources:
                    results.append(
                        self._collect_source(source, fetcher, adaptive_locator)
                    )
        except Exception:
            results = [self._with_worker_error(result) for result in results]
            completed_codes = {result.source_code for result in results}
            results.extend(
                self._worker_error(source)
                for source in sources
                if source.code not in completed_codes
            )
        for result in results:
            self._notify_source_done(result)
        return tuple(results)

    @staticmethod
    def _parallel_batches(
        sources: Sequence[SourceConfig], workers: int
    ) -> tuple[tuple[SourceConfig, ...], ...]:
        browser_kinds = {SourceKind.DYNAMIC, SourceKind.GUPY}
        scheduled = sorted(
            sources,
            key=lambda source: source.kind not in browser_kinds
            and not source.requires_auth,
        )
        batches: list[list[SourceConfig]] = [
            [] for _ in range(min(workers, len(scheduled)))
        ]
        for index, source in enumerate(scheduled):
            batches[index % len(batches)].append(source)
        return tuple(tuple(batch) for batch in batches if batch)

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
        adaptive_locator = self._adaptive_locator or AdaptiveCardLocator()
        unordered_results: list[SourceRunResult] = []
        if not selected:
            source_results: list[SourceRunResult] = []
        elif self._workers == 1 and self._fetcher is not None:
            source_results = []
            for source in selected:
                result = self._collect_source(source, self._fetcher, adaptive_locator)
                source_results.append(result)
                self._notify_source_done(result)
        elif self._workers == 1:
            source_results = list(self._collect_batch(selected, adaptive_locator))
        else:
            batches = self._parallel_batches(selected, self._workers)
            claimed_fetchers: list[FetchPolicy] = []
            claim_lock = Lock()
            with ThreadPoolExecutor(
                max_workers=len(batches),
                thread_name_prefix="job-radar-source",
            ) as executor:
                futures = {
                    executor.submit(
                        self._collect_batch,
                        batch,
                        adaptive_locator,
                        claimed_fetchers,
                        claim_lock,
                    ): batch
                    for batch in batches
                }
                for future in as_completed(futures):
                    batch = futures[future]
                    try:
                        batch_results = future.result()
                    except Exception:
                        batch_results = tuple(
                            self._worker_error(source) for source in batch
                        )
                        for result in batch_results:
                            self._notify_source_done(result)
                    unordered_results.extend(batch_results)
            by_code = {result.source_code: result for result in unordered_results}
            source_results = [by_code[source.code] for source in selected]

        if self._history is not None:
            count_warnings = self._history.check_source_counts(source_results)
            source_results = [
                replace(result, warnings=(*result.warnings, count_warnings[result.source_code]))
                if result.source_code in count_warnings
                else result
                for result in source_results
            ]

        raw_records = [
            replace(record, collection_status=result.status)
            for result in source_results
            for record in result.records
        ]

        default_countries = {
            source.code: source.default_country for source in selected
        }
        def classify_one(record: VacancyRecord) -> VacancyRecord:
            return classify(
                record,
                self._profile,
                default_country=default_countries.get(record.source),
            )

        if self._enrich_limit > 0:
            enriched_records, self.enriched_count = enrich_records(
                raw_records,
                classify_one,
                selected,
                limit=self._enrich_limit,
                fetcher_factory=self._enrich_fetcher_factory,
            )
            raw_records = list(enriched_records)
        classified = tuple(classify_one(record) for record in raw_records)
        deduplicated = deduplicate(classified)
        unique = deduplicated.unique
        if self._history is not None:
            unique = self._history.annotate(unique, self._now())
        return PipelineResult(
            started_at=started_at,
            finished_at=self._now().isoformat(),
            records=unique,
            ambiguous=deduplicated.ambiguous,
            source_results=tuple(source_results),
            raw_record_count=len(raw_records),
            duplicate_count=deduplicated.duplicate_count,
        )
