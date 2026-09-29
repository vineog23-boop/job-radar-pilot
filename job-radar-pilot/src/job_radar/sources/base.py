from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import re
from typing import Protocol
from urllib.parse import parse_qs, urlsplit

from job_radar.adaptive import AdaptiveCardLocator, CardSelection, select_cards
from job_radar.fetching import BlockReason, FetchPolicy, _visible_response_text
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
    card_method: str = "CONFIGURED"


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


def _clean_source_location(config: SourceConfig, location: str | None) -> str | None:
    if config.code != "infojobs" or location is None:
        return location
    cleaned = re.sub(
        r"\s*,?\s*\d+(?:[.,]\d+)?\s+Km de você\.\s*$",
        "",
        location,
    ).rstrip(" ,")
    return cleaned or None


class PaginatedAdapter:
    empty_markers = (
        "nenhuma vaga encontrada",
        "nenhuma oportunidade encontrada",
        "no jobs found",
        "no opportunities found",
    )

    def __init__(self, locator: AdaptiveCardLocator | None = None) -> None:
        self._locator = locator

    def select_cards(
        self,
        page: object,
        config: SourceConfig,
        selector: str,
    ) -> CardSelection:
        if config.adaptive and self._locator is not None:
            return select_cards(
                page,
                source_code=config.code,
                selector=selector,
                locator=self._locator,
            )
        cards = tuple(page.css(selector))  # type: ignore[attr-defined]
        return CardSelection(cards, "CONFIGURED" if cards else "NONE")

    def remember_cards(
        self,
        page: object,
        config: SourceConfig,
        selector: str,
        selection: CardSelection,
        records: tuple[VacancyRecord, ...],
    ) -> None:
        if (
            config.adaptive
            and self._locator is not None
            and selection.method == "CONFIGURED"
            and records
        ):
            self._locator.remember(page, config.code, selector)

    def parse_page(self, page: object, config: SourceConfig) -> ParsedPage:
        raise NotImplementedError

    def collect(self, config: SourceConfig, fetcher: FetchPolicy) -> SourceRunResult:
        records: list[VacancyRecord] = []
        visited: list[str] = []
        cards_observed = 0
        current_url: str | None = config.start_url
        warnings: list[str] = []

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
                    warnings=tuple(warnings),
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
                    warnings=tuple(warnings),
                )

            parsed = self.parse_page(fetched.response, config)
            if (
                parsed.card_method == "ADAPTIVE"
                and "SELECTOR_RELOCATED:card" not in warnings
            ):
                warnings.append("SELECTOR_RELOCATED:card")
            parsed_records = (
                tuple(
                    replace(
                        record,
                        match_labels=tuple(
                            dict.fromkeys(
                                (*record.match_labels, "EXTRACTION:ADAPTIVE")
                            )
                        ),
                    )
                    for record in parsed.records
                )
                if parsed.card_method == "ADAPTIVE"
                else parsed.records
            )
            cards_observed += parsed.cards_observed
            records.extend(parsed_records)
            if parsed.cards_observed > 0 and not parsed_records:
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
                    warnings=tuple(warnings),
                )
            if parsed.cards_observed == 0 and not records:
                text = " ".join(_visible_response_text(fetched.response).casefold().split())
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
                    warnings=tuple(warnings),
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
                    warnings=tuple(warnings),
                )
            if (
                parsed_records
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
                    warnings=tuple(warnings),
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
                warnings=tuple(warnings),
            )
        if warnings and records:
            return SourceRunResult(
                source_code=config.code,
                status=CollectionStatus.PARTIAL,
                records=tuple(records),
                pages_observed=len(visited),
                cards_observed=cards_observed,
                stop_reason="SELECTOR_RELOCATED",
                visited_urls=tuple(visited),
                warnings=tuple(warnings),
            )
        return SourceRunResult(
            source_code=config.code,
            status=CollectionStatus.SUCCESS if records else CollectionStatus.EMPTY,
            records=tuple(records),
            pages_observed=len(visited),
            cards_observed=cards_observed,
            visited_urls=tuple(visited),
            warnings=tuple(warnings),
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
        location=_clean_source_location(
            config,
            extract_value(card, location_selector),
        ),
        observed_at=datetime.now(timezone.utc).isoformat(),
        evidence_snippets=(title,),
    )


def make_record_with_fallback(
    *,
    card_method: str,
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
    record = make_record(
        config=config,
        page=page,
        card=card,
        id_selector=id_selector,
        title_selector=title_selector,
        url_selector=url_selector,
        company_selector=company_selector,
        location_selector=location_selector,
        description_selector=description_selector,
    )
    if record is not None and card_method == "ADAPTIVE":
        parsed = urlsplit(record.canonical_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            record = None
    if record is not None or card_method != "ADAPTIVE":
        return record

    fallback_title = next(
        (
            selector
            for selector in (
                "h1::all-text",
                "h2::all-text",
                "h3::all-text",
                "h4::all-text",
                "a::all-text",
                "::all-text",
            )
            if extract_value(card, selector)
        ),
        None,
    )
    card_tag = str(getattr(card, "tag", "")).casefold()
    url_candidates = (
        ("::attr(href)", "a[href]::attr(href)")
        if card_tag == "a"
        else ("a[href]::attr(href)", "::attr(href)")
    )
    fallback_url = next(
        (selector for selector in url_candidates if extract_value(card, selector)),
        None,
    )
    if fallback_title is None or fallback_url is None:
        return None
    record = make_record(
        config=config,
        page=page,
        card=card,
        id_selector=id_selector,
        title_selector=fallback_title,
        url_selector=fallback_url,
        company_selector=company_selector,
        location_selector=location_selector,
        description_selector=description_selector,
    )
    if record is None:
        return None
    parsed = urlsplit(record.canonical_url)
    return record if parsed.scheme in {"http", "https"} and parsed.netloc else None


def adaptive_card_allowed(config: SourceConfig, card: object) -> bool:
    excluded_class = {
        "programathor": "opacity-60p",
        "companhia-de-estagios": "--expired",
    }.get(config.code)
    if excluded_class is None:
        return True
    current = getattr(card, "_root", card)
    for _ in range(5):
        if current is None:
            break
        classes = str(getattr(current, "attrib", {}).get("class", "")).split()
        if excluded_class in classes:
            return False
        current = current.getparent()
    return True
