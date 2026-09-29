"""Enriquecimento opcional pela página de detalhe das vagas duvidosas."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Sequence

from job_radar.fetching import FetchPolicy, _visible_response_text
from job_radar.models import (
    CollectionStatus,
    SearchProfile,
    SourceConfig,
    SourceKind,
    VacancyRecord,
)

MAX_DETAIL_CHARS = 3000
_SKIP_SOURCES = {"indeed"}


def _main_text(response: object) -> str:
    """Prefere o miolo da página (main/article) para evitar menu e rodapé."""

    try:
        parts = response.css("main ::text, article ::text").getall()  # type: ignore[attr-defined]
        focused = " ".join(" ".join(parts).split())
        if len(focused) >= 200:
            return focused
    except Exception:
        pass
    return " ".join(_visible_response_text(response).split())


def _is_candidate(classified: VacancyRecord) -> bool:
    labels = classified.match_labels
    doubtful = "FIT:CONDITIONAL" in labels or "FIT:AMBIGUOUS" in labels
    has_tech = any(label.startswith("TECH_MATCH:") for label in labels)
    return doubtful and has_tech


def enrich_records(
    raw_records: Sequence[VacancyRecord],
    classify_fn: Callable[[VacancyRecord], VacancyRecord],
    sources: Sequence[SourceConfig],
    *,
    limit: int,
    fetcher_factory: Callable[[], FetchPolicy] = FetchPolicy,
) -> tuple[tuple[VacancyRecord, ...], int]:
    """Busca o texto da página de detalhe de até ``limit`` vagas duvidosas.

    Retorna os registros (ainda não classificados) e quantos foram enriquecidos.
    Só usa HTTP estático, respeitando robots.txt e limites do FetchPolicy; falhas
    são ignoradas e o registro original é mantido.
    """

    if limit <= 0:
        return tuple(raw_records), 0
    by_code = {source.code: source for source in sources}
    picked: dict[int, SourceConfig] = {}
    for index, record in enumerate(raw_records):
        if len(picked) >= limit:
            break
        source = by_code.get(record.source)
        if (
            source is None
            or record.source in _SKIP_SOURCES
            or source.requires_auth
            or not record.canonical_url.startswith("https://")
            or len(record.description_summary or "") >= MAX_DETAIL_CHARS // 2
        ):
            continue
        if _is_candidate(classify_fn(record)):
            picked[index] = source
    if not picked:
        return tuple(raw_records), 0

    updated = list(raw_records)
    enriched = 0
    with fetcher_factory() as fetcher:
        for index, source in picked.items():
            record = raw_records[index]
            static_source = replace(source, kind=SourceKind.GENERIC, adaptive=False)
            try:
                fetched = fetcher.fetch(record.canonical_url, static_source)
            except Exception:
                continue
            if fetched.status is not CollectionStatus.SUCCESS or fetched.response is None:
                continue
            text = _main_text(fetched.response)
            if len(text) < 80:
                continue
            base = record.description_summary or ""
            merged = f"{base} {text}".strip()[:MAX_DETAIL_CHARS]
            updated[index] = replace(
                record,
                description_summary=merged,
                match_labels=tuple(
                    dict.fromkeys((*record.match_labels, "ENRICHED:DETAIL"))
                ),
            )
            enriched += 1
    return tuple(updated), enriched
