from __future__ import annotations

import re

from job_radar.models import SourceConfig
from job_radar.sources.base import (
    PaginatedAdapter,
    ParsedPage,
    absolute_url,
    adaptive_card_allowed,
    extract_value,
    make_record_with_fallback,
)


class GenericListAdapter(PaginatedAdapter):
    def parse_page(self, page: object, config: SourceConfig) -> ParsedPage:
        card_selector = config.selectors["card"]
        selection = self.select_cards(page, config, card_selector)
        cards = tuple(
            card
            for card in selection.cards
            if selection.method != "ADAPTIVE" or adaptive_card_allowed(config, card)
        )
        records = tuple(
            record
            for card in cards
            if (
                record := make_record_with_fallback(
                    card_method=selection.method,
                    config=config,
                    page=page,
                    card=card,
                    id_selector=config.selectors.get("id"),
                    title_selector=config.selectors["title"],
                    url_selector=config.selectors["url"],
                    company_selector=config.selectors.get("company"),
                    location_selector=config.selectors.get("location"),
                    description_selector=config.selectors.get("summary"),
                )
            )
        )
        self.remember_cards(page, config, card_selector, selection, records)
        next_url = absolute_url(page, extract_value(page, config.selectors.get("next")))
        declared_text = extract_value(page, config.selectors.get("declared_count"))
        declared_match = re.search(r"\d[\d.,\s]*", declared_text or "")
        declared_count = (
            int("".join(character for character in declared_match.group() if character.isdigit()))
            if declared_match
            else None
        )
        declared_complete = (
            declared_count is not None and declared_count <= len(records)
        )
        return ParsedPage(
            records,
            len(cards),
            next_url or None,
            pagination_observable=(
                "next" in config.selectors or declared_complete
            ),
            card_method=selection.method,
        )
