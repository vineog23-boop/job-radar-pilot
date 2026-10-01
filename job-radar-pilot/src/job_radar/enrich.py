"""Enriquecimento opcional pela página de detalhe das vagas candidatas."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import json
import re
from typing import Any, Callable, Iterator, Sequence

from job_radar.dates import parse_published_at
from job_radar.fetching import FetchPolicy, _visible_response_text, page_html
from job_radar.fit import fit_state
from job_radar.sources.base import VISIBLE_TEXT_XPATH
from job_radar.text_cleaning import clean_description
from job_radar.models import (
    CollectionStatus,
    SourceConfig,
    SourceKind,
    VacancyRecord,
)

MAX_DETAIL_CHARS = 3000
DEFAULT_ENRICH_LIMIT = 120
_SKIP_SOURCES = {"indeed"}

_JSON_LD = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
_META_PUBLISHED = re.compile(
    r"<meta[^>]+(?:property|name|itemprop)=[\"'](?:article:published_time|"
    r"og:published_time|datePublished|datePosted)[\"'][^>]*?content=[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_TIME_TAG = re.compile(r"<time[^>]+datetime=[\"']([^\"']+)[\"']", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class DetailMetadata:
    published_at: str | None = None
    company: str | None = None


def _main_text(response: object) -> str:
    """Prefere o miolo da página (main/article) para evitar menu e rodapé."""

    try:
        parts = response.xpath(  # type: ignore[attr-defined]
            f"//main{VISIBLE_TEXT_XPATH[1:]} | //article{VISIBLE_TEXT_XPATH[1:]}"
        ).getall()
        focused = clean_description(" ".join(parts)) or ""
        if len(focused) >= 200:
            return focused
    except Exception:
        pass
    return clean_description(_visible_response_text(response)) or ""


def _walk_json_ld(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, list):
        for item in node:
            yield from _walk_json_ld(item)
    elif isinstance(node, dict):
        kind = node.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if "JobPosting" in kinds:
            yield node
        yield from _walk_json_ld(node.get("@graph"))


def extract_detail_metadata(html: str, *, now: datetime | None = None) -> DetailMetadata:
    """Lê data de publicação e empresa da página de detalhe.

    Ordem de confiança: JSON-LD ``JobPosting`` (``datePosted`` e
    ``hiringOrganization``), meta tags de publicação e, por último, ``<time>``.
    Sem evidência clara devolve ``None`` no campo.
    """

    published: str | None = None
    company: str | None = None
    for block in _JSON_LD.findall(html):
        try:
            data = json.loads(block.strip())
        except (ValueError, TypeError):
            continue
        for posting in _walk_json_ld(data):
            if published is None:
                raw_date = posting.get("datePosted")
                if isinstance(raw_date, str):
                    published = parse_published_at(raw_date, now=now)
            if company is None:
                organization = posting.get("hiringOrganization")
                name = (
                    organization.get("name")
                    if isinstance(organization, dict)
                    else organization
                )
                if isinstance(name, str) and name.strip():
                    company = " ".join(name.split())[:120]
    if published is None:
        for pattern in (_META_PUBLISHED, _TIME_TAG):
            match = pattern.search(html)
            if match:
                published = parse_published_at(match.group(1), now=now)
                if published:
                    break
    return DetailMetadata(published_at=published, company=company)


def _priority(classified: VacancyRecord) -> int | None:
    """Ordem de visita: mais compatíveis primeiro, depois as duvidosas com stack."""

    labels = classified.match_labels
    if "RELEVANCE:OFF_TOPIC" in labels:
        return None
    state = fit_state(labels)
    if state == "READY":
        return 0
    if state == "CONDITIONAL":
        return 1
    if state == "AMBIGUOUS" and any(
        label.startswith("TECH_MATCH:") for label in labels
    ):
        return 2
    return None


def _needs_detail(record: VacancyRecord) -> bool:
    long_text = len(record.description_summary or "") >= MAX_DETAIL_CHARS // 2
    return not long_text or not record.published_at or not record.company


def enrich_records(
    raw_records: Sequence[VacancyRecord],
    classify_fn: Callable[[VacancyRecord], VacancyRecord],
    sources: Sequence[SourceConfig],
    *,
    limit: int,
    fetcher_factory: Callable[[], FetchPolicy] = FetchPolicy,
) -> tuple[tuple[VacancyRecord, ...], int]:
    """Busca a página de detalhe de até ``limit`` vagas candidatas.

    Candidatas: READY, CONDITIONAL e AMBIGUOUS com alguma tecnologia do perfil,
    nessa ordem. Além do texto, completa data de publicação e empresa quando o
    portal as expõe (JSON-LD/meta). Retorna os registros (ainda não
    classificados) e quantos foram enriquecidos. Só usa HTTP estático,
    respeitando robots.txt e limites do FetchPolicy; falhas são ignoradas e o
    registro original é mantido.
    """

    if limit <= 0:
        return tuple(raw_records), 0
    by_code = {source.code: source for source in sources}
    ranked: list[tuple[int, int, SourceConfig]] = []
    for index, record in enumerate(raw_records):
        source = by_code.get(record.source)
        if (
            source is None
            or record.source in _SKIP_SOURCES
            or source.requires_auth
            or not record.canonical_url.startswith("https://")
            or not _needs_detail(record)
        ):
            continue
        priority = _priority(classify_fn(record))
        if priority is not None:
            ranked.append((priority, index, source))
    picked = sorted(ranked, key=lambda item: (item[0], item[1]))[:limit]
    if not picked:
        return tuple(raw_records), 0

    updated = list(raw_records)
    enriched = 0
    with fetcher_factory() as fetcher:
        for _, index, source in picked:
            record = raw_records[index]
            static_source = replace(source, kind=SourceKind.GENERIC, adaptive=False)
            try:
                fetched = fetcher.fetch(record.canonical_url, static_source)
            except Exception:
                continue
            if fetched.status is not CollectionStatus.SUCCESS or fetched.response is None:
                continue
            text = _main_text(fetched.response)
            metadata = extract_detail_metadata(page_html(fetched.response))
            new_fields: dict[str, Any] = {}
            if not record.published_at and metadata.published_at:
                new_fields["published_at"] = metadata.published_at
            if not record.company and metadata.company:
                new_fields["company"] = metadata.company
            if len(text) < 80 and not new_fields:
                continue
            if len(text) >= 80:
                base = record.description_summary or ""
                new_fields["description_summary"] = f"{base} {text}".strip()[
                    :MAX_DETAIL_CHARS
                ]
            updated[index] = replace(
                record,
                match_labels=tuple(
                    dict.fromkeys((*record.match_labels, "ENRICHED:DETAIL"))
                ),
                **new_fields,
            )
            enriched += 1
    return tuple(updated), enriched
