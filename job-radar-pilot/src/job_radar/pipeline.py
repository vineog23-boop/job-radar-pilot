from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence

from job_radar.classifier import classify
from job_radar.fetching import FetchPolicy
from job_radar.identity import deduplicate
from job_radar.models import (
    CollectionStatus,
    SearchProfile,
    SourceConfig,
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
            try:
                result = self._adapter_factory(source).collect(source, self._fetcher)
            except Exception:
                result = SourceRunResult(
                    source_code=source.code,
                    status=CollectionStatus.ERROR,
                    stop_reason="ADAPTER_ERROR",
                    errors=(f"Falha interna no adaptador {source.code}",),
                )
            source_results.append(result)
            raw_records.extend(result.records)

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
