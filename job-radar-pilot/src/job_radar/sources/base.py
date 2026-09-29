from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import parse_qs, urlsplit

from job_radar.fetching import BlockReason, FetchPolicy
from job_radar.identity import canonicalize_url
from job_radar.models import (
    CollectionStatus,
    SourceConfig,
    SourceRunResult,
    VacancyRecord,
)


class SourceAdapter(Protocol):
    def collect(
        self, config: SourceConfig, fetcher: FetchPolicy
    ) -> SourceRunResult: ...


@dataclass(frozen=True, slots=True)
class ParsedPage:
    records: tuple[VacancyRecord, ...]
    cards_observed: int
    next_url: str | None = None
    explicit_empty: bool = False
    pagination_observable: bool = True


def extract_value(node: object, selector: str | None) -> str | None:
    if not selector:
        return None
    if selector.endswith("::all-text"):
        element_selector = selector.removesuffix("::all-text")
        if element_selector:
            matches = node.css(element_selector)  # type: ignore[attr-defined]
            if not matches:
                return None
            selected = matches[0]
        else:
            selected = node
        value = " ".join(selected.css("::text").getall())  # type: ignore[attr-defined]
    elif selector.startswith("::attr(") and selector.endswith(")"):
        attribute = selector[7:-1]
        value = getattr(node, "attrib", {}).get(attribute)
    else:
        query = selector if "::" in selector else f"{selector}::text"
        value = node.css(query).get()  # type: ignore[attr-defined]
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def absolute_url(page: object, value: str | None) -> str:
    if not value:
        return ""
    return canonicalize_url(page.urljoin(value))  # type: ignore[attr-defined]


def job_id_from_url(url: str) -> str | None:
    if not url:
        return None
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    for key in ("jk", "jobId", "job_id"):
        values = query.get(key)
        if values and values[0]:
            return values[0]
    last_segment = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    return last_segment or None


class PaginatedAdapter:
    empty_markers = (
        "nenhuma vaga encontrada",
        "nenhuma oportunidade encontrada",
        "no jobs found",
        "no opportunities found",
    )

    def parse_page(self, page: object, config: SourceConfig) -> ParsedPage:
        raise NotImplementedError

    def collect(self, config: SourceConfig, fetcher: FetchPolicy) -> SourceRunResult:
        records: list[VacancyRecord] = []
        visited: list[str] = []
        cards_observed = 0
        current_url: str | None = config.start_url

        while current_url and len(visited) < config.max_pages:
            if current_url in visited:
                return SourceRunResult(
                    source_code=config.code,
                    status=CollectionStatus.PARTIAL,
                    records=tuple(records),
                    pages_observed=len(visited),
                    cards_observed=cards_observed,
                    has_more=True,
                    stop_reason="PAGINATION_LOOP",
                    visited_urls=tuple(visited),
                )
            visited.append(current_url)
            fetched = fetcher.fetch(current_url, config)
            if fetched.status is not CollectionStatus.SUCCESS or fetched.response is None:
                auth_reasons = {
                    BlockReason.LOGIN_REQUIRED,
                    BlockReason.TWO_FACTOR,
                }
                status = (
                    CollectionStatus.PARTIAL
                    if records
                    else CollectionStatus.AUTH_REQUIRED
                    if fetched.block_reason in auth_reasons
                    else fetched.status
                )
                return SourceRunResult(
                    source_code=config.code,
                    status=status,
                    records=tuple(records),
                    pages_observed=len(visited),
                    cards_observed=cards_observed,
                    has_more=bool(records),
                    stop_reason=(
                        fetched.block_reason.value
                        if fetched.block_reason is not None
                        else "FETCH_ERROR"
                    ),
                    errors=(fetched.error,) if fetched.error else (),
                    visited_urls=tuple(visited),
                )

            parsed = self.parse_page(fetched.response, config)
            cards_observed += parsed.cards_observed
            records.extend(parsed.records)
            if parsed.cards_observed > 0 and not parsed.records:
                return SourceRunResult(
                    source_code=config.code,
                    status=(
                        CollectionStatus.PARTIAL
                        if records
                        else CollectionStatus.ERROR
                    ),
                    records=tuple(records),
                    pages_observed=len(visited),
                    cards_observed=cards_observed,
                    has_more=bool(parsed.next_url),
                    stop_reason="PARSE_ZERO_RECORDS",
                    visited_urls=tuple(visited),
                )
            if parsed.cards_observed == 0 and not records:
                text = " ".join(str(fetched.response.text).casefold().split())
                status = (
                    CollectionStatus.EMPTY
                    if parsed.explicit_empty
                    or any(marker in text for marker in self.empty_markers)
                    else CollectionStatus.ERROR
                )
                return SourceRunResult(
                    source_code=config.code,
                    status=status,
                    pages_observed=len(visited),
                    cards_observed=0,
                    stop_reason=("NO_RESULTS" if status is CollectionStatus.EMPTY else "LAYOUT_CHANGED"),
                    visited_urls=tuple(visited),
                )
            if parsed.cards_observed == 0 and records:
                return SourceRunResult(
                    source_code=config.code,
                    status=CollectionStatus.PARTIAL,
                    records=tuple(records),
                    pages_observed=len(visited),
                    cards_observed=cards_observed,
                    has_more=bool(parsed.next_url),
                    stop_reason="EMPTY_PAGE_AFTER_RECORDS",
                    visited_urls=tuple(visited),
                )
            if (
                parsed.records
                and not parsed.next_url
                and not parsed.pagination_observable
            ):
                return SourceRunResult(
                    source_code=config.code,
                    status=CollectionStatus.PARTIAL,
                    records=tuple(records),
                    pages_observed=len(visited),
                    cards_observed=cards_observed,
                    has_more=True,
                    stop_reason="PAGINATION_UNVERIFIED",
                    visited_urls=tuple(visited),
                )
            current_url = parsed.next_url

        if current_url:
            return SourceRunResult(
                source_code=config.code,
                status=CollectionStatus.PARTIAL,
                records=tuple(records),
                pages_observed=len(visited),
                cards_observed=cards_observed,
                has_more=True,
                stop_reason="PAGE_LIMIT",
                visited_urls=tuple(visited),
            )
        return SourceRunResult(
            source_code=config.code,
            status=CollectionStatus.SUCCESS if records else CollectionStatus.EMPTY,
            records=tuple(records),
            pages_observed=len(visited),
            cards_observed=cards_observed,
            visited_urls=tuple(visited),
        )


def make_record(
    *,
    config: SourceConfig,
    page: object,
    card: object,
    id_selector: str | None,
    title_selector: str,
    url_selector: str,
    company_selector: str | None,
    location_selector: str | None,
    description_selector: str | None = None,
) -> VacancyRecord | None:
    title = extract_value(card, title_selector)
    raw_url = extract_value(card, url_selector)
    canonical_url = absolute_url(page, raw_url)
    if not title or not canonical_url:
        return None
    source_job_id = extract_value(card, id_selector) or job_id_from_url(canonical_url)
    return VacancyRecord(
        source=config.code,
        source_job_id=source_job_id,
        canonical_url=canonical_url,
        title=title,
        company=extract_value(card, company_selector),
        description_summary=extract_value(card, description_selector),
        location=extract_value(card, location_selector),
        observed_at=datetime.now(timezone.utc).isoformat(),
        evidence_snippets=(title,),
    )
