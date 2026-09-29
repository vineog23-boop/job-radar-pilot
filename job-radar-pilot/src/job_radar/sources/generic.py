from __future__ import annotations

import re

from job_radar.adaptive import adaptive_card_is_safe
from job_radar.models import SourceConfig
from job_radar.sources.base import (
    PaginatedAdapter,
    ParsedPage,
    _is_excluded_card,
    absolute_url,
    extract_value,
    make_record_with_fallback,
)


class GenericListAdapter(PaginatedAdapter):
    def parse_page(self, page: object, config: SourceConfig) -> ParsedPage:
        card_selector = config.selectors["card"]

        def record_for(card: object, card_method: str):
            if card_method == "ADAPTIVE" and (
                _is_excluded_card(config, card)
                or not adaptive_card_is_safe(card)
            ):
                return None
            return make_record_with_fallback(
                card_method=card_method,
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

        selection = self.select_cards(
            page,
            config,
            card_selector,
            validator=lambda card: record_for(card, "ADAPTIVE") is not None,
        )
        cards = selection.cards
        card_records = tuple(
            (card, record)
            for card in cards
            if (record := record_for(card, selection.method))
        )
        records = tuple(record for _, record in card_records)
        valid_card = card_records[0][0] if card_records else None
        self.remember_cards(page, config, card_selector, selection, valid_card)
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
