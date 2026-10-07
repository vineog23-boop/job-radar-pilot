from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import re
from typing import Callable, Protocol
from urllib.parse import parse_qs, urlsplit

from job_radar.adaptive import AdaptiveCardLocator, CardSelection, select_cards
from job_radar.fetching import BlockReason, FetchPolicy, _visible_response_text
from job_radar.identity import canonicalize_url
from job_radar.dates import parse_published_at
from job_radar.text_cleaning import clean_description, clean_title
from job_radar.models import (
    CollectionStatus,
    SourceConfig,
    SourceRunResult,
    VacancyRecord,
)


_ALTERNATE_ADAPTIVE_HOST_SUFFIXES = {
    "gupy": (".gupy.io",),
}


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


# Texto visível do nó: ignora <script>, <style>, <noscript> e <template> internos
# (alguns portais põem anúncio e JavaScript dentro do cartão da vaga).
VISIBLE_TEXT_XPATH = (
    ".//text()[not(ancestor::script) and not(ancestor::style)"
    " and not(ancestor::noscript) and not(ancestor::template)]"
)


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
        if hasattr(selected, "xpath"):
            parts = selected.xpath(VISIBLE_TEXT_XPATH).getall()  # type: ignore[attr-defined]
        else:  # nós simplificados (testes) só têm css
            parts = selected.css("::text").getall()  # type: ignore[attr-defined]
        value = " ".join(parts)
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
    if (parsed.hostname or "").endswith(".inhire.app"):
        match = re.match(r"/vagas/([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})(?:/|$)", parsed.path)
        if match:
            return match.group(1).lower()
    if parsed.hostname == "ciandt.com":
        opportunity = query.get("opportunity", [""])[0]
        if re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", opportunity):
            return opportunity.lower()
    for key in ("jk", "jobId", "job_id"):
        values = query.get(key)
        if values and values[0]:
            return values[0]
    last_segment = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    return last_segment or None


def _adaptive_url_allowed(config: SourceConfig, url: str) -> bool:
    parsed = urlsplit(url)
    source = urlsplit(config.start_url)
    candidate_scheme = parsed.scheme.casefold()
    source_scheme = source.scheme.casefold()
    candidate_host = (parsed.hostname or "").casefold()
    source_host = (source.hostname or "").casefold()
    if candidate_scheme not in {"http", "https"} or not candidate_host:
        return False
    default_ports = {"http": 80, "https": 443}
    try:
        candidate_port = parsed.port or default_ports[candidate_scheme]
        source_port = source.port or default_ports.get(source_scheme)
    except ValueError:
        return False
    same_origin = (
        candidate_scheme == source_scheme
        and candidate_host == source_host
        and candidate_port == source_port
    )
    allowed_suffixes = _ALTERNATE_ADAPTIVE_HOST_SUFFIXES.get(
        config.code,
        (),
    )
    return same_origin or (
        candidate_scheme == "https"
        and any(candidate_host.endswith(suffix) for suffix in allowed_suffixes)
    )


def _clean_source_location(config: SourceConfig, location: str | None) -> str | None:
    if config.code != "infojobs" or location is None:
        return location
    cleaned = re.sub(
        r"\s*,?\s*\d+(?:[.,]\d+)?\s+Km de você\.\s*$",
        "",
        location,
    ).rstrip(" ,")
    return cleaned or None


_LOGIN_PATH_RE = re.compile(
    r"/(?:login|entrar|signin|sign-in|signup|cadastro|auth)(?:/|$|\?)",
    re.IGNORECASE,
)
_MIN_ADAPTIVE_TITLE = 8
_MIN_ADAPTIVE_RECORDS = 2


def _adaptive_result_plausible(
    config: SourceConfig,
    parsed: ParsedPage,
    current_url: str,
    *,
    first_page: bool,
    page_text: str,
    empty_markers: tuple[str, ...],
) -> bool:
    """Rejeita relocalizações que provavelmente são falsos positivos.

    Só vale relocalizar na primeira página, sem marcador de resultado vazio,
    com pelo menos duas vagas cujo link não seja login nem a própria listagem.
    """
    if not first_page:
        return False
    if any(marker in page_text for marker in empty_markers):
        return False
    listing = urlsplit(current_url)
    valid = 0
    for record in parsed.records:
        target = urlsplit(record.canonical_url)
        if _LOGIN_PATH_RE.search(target.path + "/"):
            continue
        if (
            target.netloc.casefold() == listing.netloc.casefold()
            and target.path.rstrip("/") == listing.path.rstrip("/")
        ):
            continue
        if len(record.title.strip()) < _MIN_ADAPTIVE_TITLE:
            continue
        valid += 1
    return valid >= _MIN_ADAPTIVE_RECORDS


class PaginatedAdapter:
    empty_markers = (
        "nenhuma vaga encontrada",
        "nenhuma oportunidade encontrada",
        "no jobs found",
        "no opportunities found",
        "nao encontramos resultados",
        "não encontramos resultados",
        "nenhuma vaga foi encontrada",
    )

    def __init__(self, locator: AdaptiveCardLocator | None = None) -> None:
        self._locator = locator

    def select_cards(
        self,
        page: object,
        config: SourceConfig,
        selector: str,
        *,
        validator: Callable[[object], bool] | None = None,
    ) -> CardSelection:
        if config.adaptive and self._locator is not None:
            return select_cards(
                page,
                source_code=config.code,
                selector=selector,
                locator=self._locator,
                validator=validator,
            )
        cards = tuple(page.css(selector))  # type: ignore[attr-defined]
        return CardSelection(cards, "CONFIGURED" if cards else "NONE")

    def remember_cards(
        self,
        page: object,
        config: SourceConfig,
        selector: str,
        selection: CardSelection,
        valid_card: object | None,
    ) -> None:
        if (
            config.adaptive
            and self._locator is not None
            and selection.method == "CONFIGURED"
            and valid_card is not None
        ):
            self._locator.remember(
                page,
                config.code,
                selector,
                card=valid_card,
            )

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
            if parsed.card_method == "ADAPTIVE" and not _adaptive_result_plausible(
                config,
                parsed,
                current_url,
                first_page=len(visited) == 1,
                page_text=" ".join(
                    _visible_response_text(fetched.response).casefold().split()
                ),
                empty_markers=self.empty_markers,
            ):
                parsed = ParsedPage((), 0, None, card_method="NONE")
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
    title = clean_title(extract_value(card, title_selector))
    title_extra = clean_title(extract_value(card, config.selectors.get("title_extra")))
    if title and title_extra and title_extra.casefold() not in title.casefold():
        title = f"{title} - {title_extra}"
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
        company=extract_value(card, company_selector) or config.default_company,
        description_summary=clean_description(extract_value(card, description_selector)),
        location=_clean_source_location(
            config,
            extract_value(card, location_selector),
        ),
        published_at=parse_published_at(
            extract_value(card, config.selectors.get("published"))
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
    validated_fallback: bool = False,
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
    fallback_enabled = card_method == "ADAPTIVE" or validated_fallback
    if (
        record is not None
        and fallback_enabled
        and not _adaptive_url_allowed(config, record.canonical_url)
    ):
        record = None
    if record is not None or not fallback_enabled:
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
    return record if _adaptive_url_allowed(config, record.canonical_url) else None


def _is_excluded_card(config: SourceConfig, card: object) -> bool:
    excluded_class = {
        "programathor": "opacity-60p",
        "companhia-de-estagios": "--expired",
    }.get(config.code)
    if excluded_class is None:
        return False
    current = getattr(card, "_root", card)
    for _ in range(5):
        if current is None:
            break
        classes = str(getattr(current, "attrib", {}).get("class", "")).split()
        if excluded_class in classes:
            return True
        current = current.getparent()
    return False


def adaptive_card_allowed(config: SourceConfig, card: object) -> bool:
    return not _is_excluded_card(config, card)


def public_list_has_more(page: object, config: SourceConfig) -> bool:
    """Sinaliza novos controles de limite nas listagens públicas pesquisadas."""
    if config.code not in {"inhire-programmers", "inhire-bionexo", "ciandt"}:
        return False
    for control in page.css("button, a, [role='button']"):
        attributes = getattr(control, "attrib", {})
        if "disabled" in attributes or attributes.get("aria-disabled") == "true":
            continue
        text = extract_value(control, "::all-text") or ""
        label = f"{text} {attributes.get('aria-label', '')}".casefold()
        if attributes.get("rel") == "next" or re.search(
            r"carregar mais|mostrar mais|ver mais vagas|load more|show more|próxima página|next page", label
        ):
            return True
    return False
