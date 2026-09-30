"""Fontes com feed RSS público (kind: rss), como o Empregos Tech.

O feed já traz título, empresa, tipo de contrato e data. Portais de vagas 100%
remotas marcam todas as vagas como remotas; isso vem do ``sources.yaml``
(``default_country`` + ``remote_only``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
from typing import Any
from xml.etree import ElementTree

from job_radar.adaptive import AdaptiveCardLocator
from job_radar.fetching import BlockReason, FetchPolicy
from job_radar.identity import canonicalize_url
from job_radar.models import (
    CollectionStatus,
    SourceConfig,
    SourceRunResult,
    VacancyRecord,
    WorkplaceModel,
)
from job_radar.sources.json_api import clean_text

_MAX_DESCRIPTION = 3000
_TITLE_PREFIX = re.compile(r"^\s*vaga\s+(home\s*office|remota|remoto)\s*:\s*", re.IGNORECASE)
_TITLE_COMPANY = re.compile(r"^(?P<title>.+?)\s+na\s+empresa\s+(?P<company>.+)$", re.IGNORECASE)
_EMPRESA = re.compile(r"<strong>\s*Empresa:\s*</strong>\s*([^<]+)", re.IGNORECASE)
_TIPO = re.compile(r"<strong>\s*Tipo:\s*</strong>\s*([^<]+)", re.IGNORECASE)
_CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"


def _parse_feed(body: bytes) -> list[ElementTree.Element] | None:
    # Entidades/DOCTYPE não fazem parte de um feed de vagas; recusar evita
    # expansão de entidades maliciosa sem depender de biblioteca extra.
    head = body[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in head:
        return None
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return None
    items = root.findall("./channel/item")
    return items if root.tag == "rss" else None


def _published(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value.strip())
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def record_from_item(
    item: ElementTree.Element, config: SourceConfig, observed_at: str
) -> VacancyRecord | None:
    def text(tag: str) -> str | None:
        node = item.find(tag)
        return node.text.strip() if node is not None and node.text else None

    link = text("link")
    raw_title = text("title")
    if not raw_title or not link or not link.startswith("https://"):
        return None
    content = text(_CONTENT) or ""
    title = _TITLE_PREFIX.sub("", raw_title)
    company_match = _EMPRESA.search(content)
    company = clean_text(company_match.group(1)) if company_match else None
    title_match = _TITLE_COMPANY.match(title)
    if title_match:
        title = title_match.group("title")
        company = company or clean_text(title_match.group("company"))
    employment = _TIPO.search(content)
    description = clean_text(text("description"))
    category = text("category")
    return VacancyRecord(
        source=config.code,
        source_job_id=None,
        canonical_url=canonicalize_url(link),
        title=clean_text(title),
        company=company,
        description_summary=description[:_MAX_DESCRIPTION] if description else None,
        employment_type=clean_text(employment.group(1)) if employment else None,
        location="Remoto",
        workplace_model=WorkplaceModel.REMOTE,
        remote_scope=config.default_country,
        published_at=_published(text("pubDate")),
        observed_at=observed_at,
        evidence_snippets=tuple(v for v in (clean_text(title), clean_text(category)) if v),
    )


class RssAdapter:
    def __init__(self, locator: AdaptiveCardLocator | None = None) -> None:
        self._locator = locator

    def collect(self, config: SourceConfig, fetcher: FetchPolicy) -> SourceRunResult:
        observed_at = datetime.now(timezone.utc).isoformat()
        fetched = fetcher.fetch(config.start_url, config)

        def result(status: CollectionStatus, stop: str | None = None, **extra: Any) -> SourceRunResult:
            return SourceRunResult(
                source_code=config.code,
                status=status,
                pages_observed=1,
                stop_reason=stop,
                visited_urls=(config.start_url,),
                **extra,
            )

        if fetched.status is not CollectionStatus.SUCCESS or fetched.response is None:
            auth = {BlockReason.LOGIN_REQUIRED, BlockReason.TWO_FACTOR}
            return result(
                CollectionStatus.AUTH_REQUIRED
                if fetched.block_reason in auth
                else fetched.status,
                fetched.block_reason.value if fetched.block_reason else "FETCH_ERROR",
                errors=(fetched.error,) if fetched.error else (),
            )
        items = _parse_feed(fetched.response.body)
        if items is None:
            return result(CollectionStatus.ERROR, "LAYOUT_CHANGED")
        records: list[VacancyRecord] = []
        seen: set[str] = set()
        for item in items:
            record = record_from_item(item, config, observed_at)
            if record is None or record.canonical_url in seen:
                continue
            seen.add(record.canonical_url)
            records.append(record)
        status = CollectionStatus.SUCCESS if records else CollectionStatus.EMPTY
        return result(
            status,
            None if records else "NO_RESULTS",
            records=tuple(records),
            cards_observed=len(items),
        )
