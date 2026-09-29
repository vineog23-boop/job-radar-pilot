from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from job_radar.adaptive import CardSelection
from job_radar.models import SourceConfig
from job_radar.sources.base import (
    PaginatedAdapter,
    ParsedPage,
    make_record_with_fallback,
)


_LEGACY_CARD_SELECTOR = "[data-testid='job-card']"
_CURRENT_CARD_SELECTOR = "#job-listing-results li"


class GupyAdapter(PaginatedAdapter):
    def parse_page(self, page: object, config: SourceConfig) -> ParsedPage:
        legacy_configured = tuple(page.css(_LEGACY_CARD_SELECTOR))  # type: ignore[attr-defined]
        current_configured = tuple(page.css(_CURRENT_CARD_SELECTOR))  # type: ignore[attr-defined]
        if legacy_configured:
            selection = CardSelection(legacy_configured, "CONFIGURED")
            variant = "legacy"
            card_selector = _LEGACY_CARD_SELECTOR
        elif current_configured:
            selection = CardSelection(current_configured, "CONFIGURED")
            variant = "current"
            card_selector = _CURRENT_CARD_SELECTOR
        else:
            legacy_selection = self.select_cards(
                page,
                config,
                _LEGACY_CARD_SELECTOR,
            )
            if legacy_selection.method == "ADAPTIVE":
                selection = legacy_selection
                variant = "legacy"
                card_selector = _LEGACY_CARD_SELECTOR
            else:
                selection = self.select_cards(
                    page,
                    config,
                    _CURRENT_CARD_SELECTOR,
                )
                variant = "current"
                card_selector = _CURRENT_CARD_SELECTOR
        cards = selection.cards
        current_layout = variant == "current"
        records = tuple(
            record
            for card in cards
            if (
                record := make_record_with_fallback(
                    card_method=selection.method,
                    config=config,
                    page=page,
                    card=card,
                    id_selector=(None if current_layout else "::attr(data-job-id)"),
                    title_selector=("h3" if current_layout else "h2"),
                    url_selector=(
                        "a[href*='/job/']::attr(href)"
                        if current_layout
                        else "a::attr(href)"
                    ),
                    company_selector=("p" if current_layout else "[data-testid='company-name']"),
                    location_selector="[data-testid='job-location']",
                )
            )
        )
        self.remember_cards(
            page,
            config,
            card_selector,
            selection,
            records,
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
