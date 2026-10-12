from __future__ import annotations

import re
from dataclasses import replace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from job_radar.adaptive import CardSelection
from job_radar.dates import parse_published_at
from job_radar.models import SourceConfig, VacancyRecord
from job_radar.sources.base import (
    PaginatedAdapter,
    ParsedPage,
    load_complete_state,
    make_record_with_fallback,
)


_LEGACY_CARD_SELECTOR = "[data-testid='job-card']"
_CURRENT_CARD_SELECTOR = "#job-listing-results li"
# Quadros públicos por empresa (<empresa>.gupy.io): markup próprio, paginação
# só via clique (sem URL por página) — a coleta usa browser.paginate_next.
_BOARD_CARD_SELECTOR = "[data-testid='job-list__listitem']"
_BOARD_LINK_SELECTOR = "a[data-testid='job-list__listitem-href']"
_BOARD_NEXT_SELECTOR = "[data-testid='pagination-next-button']"
_PUBLISHED_TEXT = re.compile(
    r"publicad[ao]\s+em\s*:?\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE
)


def _card_published_at(card: object) -> str | None:
    """Data do texto "Publicada em dd/mm/aaaa" do cartão; sem o texto, None."""

    try:
        text = str(card.get_all_text())  # type: ignore[attr-defined]
    except Exception:
        return None
    match = _PUBLISHED_TEXT.search(text)
    return parse_published_at(match.group(1)) if match else None


class GupyAdapter(PaginatedAdapter):
    def parse_page(self, page: object, config: SourceConfig) -> ParsedPage:
        def record_for(
            card: object,
            variant: str,
            card_method: str,
        ) -> VacancyRecord | None:
            current_layout = variant == "current"
            board_layout = variant == "board"
            record = make_record_with_fallback(
                card_method=card_method,
                config=config,
                page=page,
                card=card,
                id_selector=(None if current_layout or board_layout else "::attr(data-job-id)"),
                title_selector=(
                    f"{_BOARD_LINK_SELECTOR} > div > div:nth-of-type(1)"
                    if board_layout
                    else ("h3" if current_layout else "h2")
                ),
                url_selector=(
                    f"{_BOARD_LINK_SELECTOR}::attr(href)"
                    if board_layout
                    else (
                        "a[href*='/job/']::attr(href)"
                        if current_layout
                        else "a::attr(href)"
                    )
                ),
                company_selector=(
                    None
                    if board_layout
                    else ("p" if current_layout else "[data-testid='company-name']")
                ),
                location_selector=(
                    f"{_BOARD_LINK_SELECTOR} > div > div:nth-of-type(2)"
                    if board_layout
                    else "[data-testid='job-location']"
                ),
                validated_fallback=True,
            )
            if record is not None and record.published_at is None:
                published = _card_published_at(card)
                if published:
                    record = replace(record, published_at=published)
            return record

        legacy_configured = tuple(page.css(_LEGACY_CARD_SELECTOR))  # type: ignore[attr-defined]
        current_configured = tuple(page.css(_CURRENT_CARD_SELECTOR))  # type: ignore[attr-defined]
        board_configured = tuple(page.css(_BOARD_CARD_SELECTOR))  # type: ignore[attr-defined]
        candidates: list[tuple[CardSelection, str, str]] = []
        if board_configured:
            # Quadro de empresa tem markup próprio e precede as heurísticas
            # adaptativas (que misturariam cargo, cidade e tipo no título).
            candidates.append(
                (
                    CardSelection(board_configured, "CONFIGURED"),
                    "board",
                    _BOARD_CARD_SELECTOR,
                )
            )
        if legacy_configured:
            candidates.append(
                (
                    CardSelection(legacy_configured, "CONFIGURED"),
                    "legacy",
                    _LEGACY_CARD_SELECTOR,
                )
            )
        if current_configured:
            candidates.append(
                (
                    CardSelection(current_configured, "CONFIGURED"),
                    "current",
                    _CURRENT_CARD_SELECTOR,
                )
            )
        if not legacy_configured and not board_configured:
            candidates.append(
                (
                    self.select_cards(
                        page,
                        config,
                        _LEGACY_CARD_SELECTOR,
                        validator=lambda card: record_for(
                            card, "legacy", "ADAPTIVE"
                        )
                        is not None,
                    ),
                    "legacy",
                    _LEGACY_CARD_SELECTOR,
                )
            )
        if not current_configured and not board_configured:
            candidates.append(
                (
                    self.select_cards(
                        page,
                        config,
                        _CURRENT_CARD_SELECTOR,
                        validator=lambda card: record_for(
                            card, "current", "ADAPTIVE"
                        )
                        is not None,
                    ),
                    "current",
                    _CURRENT_CARD_SELECTOR,
                )
            )

        selection = candidates[-1][0]
        card_selector = candidates[-1][2]
        used_variant: str | None = None
        card_records: tuple[tuple[object, VacancyRecord], ...] = ()
        first_nonempty: tuple[CardSelection, str] | None = None
        for candidate, variant, card_selector in candidates:
            if candidate.cards and first_nonempty is None:
                first_nonempty = (candidate, card_selector)
            candidate_records = tuple(
                (card, record)
                for card in candidate.cards
                if (record := record_for(card, variant, candidate.method))
            )
            if candidate_records:
                selection = candidate
                card_records = candidate_records
                used_variant = variant
                break
        else:
            if first_nonempty is not None:
                selection, card_selector = first_nonempty
        cards = selection.cards
        records = tuple(record for _, record in card_records)
        valid_card = card_records[0][0] if card_records else None
        self.remember_cards(
            page,
            config,
            card_selector,
            selection,
            valid_card,
        )
        load_state = load_complete_state(page)
        if used_variant == "board":
            # Quadro de empresa: a paginação é só por clique (SPA), sem URL por
            # página. A exaustão vem do botão "próxima" desabilitado após a
            # ação de paginação ou do marcador data-jr-load-complete.
            board_next = tuple(page.css(_BOARD_NEXT_SELECTOR))  # type: ignore[attr-defined]
            board_exhausted = bool(board_next) and not any(
                self._is_enabled(button) for button in board_next
            )
            return ParsedPage(
                records,
                len(cards),
                next_url=None,
                pagination_observable=board_exhausted or load_state == "1",
                card_method=selection.method,
                load_capped=load_state == "0",
            )
        next_buttons = page.css("button[aria-label='Próxima página']")  # type: ignore[attr-defined]
        page_buttons = page.css("button[aria-label^='Página ']")  # type: ignore[attr-defined]
        enabled_next_exists = any(self._is_enabled(button) for button in next_buttons)
        current_page = self._current_page(str(page.url), page_buttons)
        future_pages = sorted(
            number
            for button in page_buttons
            if (number := self._page_number(button)) is not None
            and number > current_page
        )
        next_page = current_page + 1 if enabled_next_exists else None
        if next_page is None and future_pages:
            next_page = future_pages[0]
        next_url = (
            self._page_url(str(page.url), next_page)
            if next_page is not None
            else None
        )
        explicit_exhaustion = bool(next_buttons) and not enabled_next_exists
        return ParsedPage(
            records,
            len(cards),
            next_url=next_url,
            pagination_observable=bool(next_url) or explicit_exhaustion,
            card_method=selection.method,
        )

    @staticmethod
    def _is_enabled(button: object) -> bool:
        attributes = getattr(button, "attrib", {})
        return (
            "disabled" not in attributes
            and str(attributes.get("aria-disabled", "")).casefold() != "true"
        )

    @staticmethod
    def _page_number(button: object) -> int | None:
        label = str(getattr(button, "attrib", {}).get("aria-label", ""))
        match = re.search(r"\b(\d+)\b", label)
        return int(match.group(1)) if match else None

    @classmethod
    def _current_page(cls, url: str, page_buttons: object) -> int:
        parsed = urlsplit(url)
        parameters = dict(parse_qsl(parsed.query, keep_blank_values=True))
        try:
            current_page = int(parameters.get("page", "1"))
        except ValueError:
            current_page = 1
        for button in page_buttons:
            attributes = getattr(button, "attrib", {})
            if str(attributes.get("aria-current", "")).casefold() != "page":
                continue
            number = cls._page_number(button)
            if number is not None:
                return number
        return current_page

    @staticmethod
    def _page_url(url: str, page_number: int) -> str:
        parsed = urlsplit(url)
        parameters = dict(parse_qsl(parsed.query, keep_blank_values=True))
        parameters["page"] = str(page_number)
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(parameters),
                "",
            )
        )
