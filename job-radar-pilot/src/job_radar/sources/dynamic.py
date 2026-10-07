from __future__ import annotations

from job_radar.models import SourceConfig
from job_radar.sources.base import (
    PaginatedAdapter,
    ParsedPage,
    absolute_url,
    extract_value,
    make_record_with_fallback,
    public_list_has_more,
)


class DynamicAdapter(PaginatedAdapter):
    def parse_page(self, page: object, config: SourceConfig) -> ParsedPage:
        configured = bool(config.selectors.get("card"))
        card_selector = (
            config.selectors["card"]
            if configured
            else "article[data-job-id], [data-job-id]"
        )

        def record_for(card: object, card_method: str):
            return make_record_with_fallback(
                card_method=card_method,
                config=config,
                page=page,
                card=card,
                id_selector=(
                    config.selectors.get("id")
                    if configured
                    else "::attr(data-job-id)"
                ),
                title_selector=(config.selectors["title"] if configured else "h2"),
                url_selector=(
                    config.selectors["url"] if configured else "a::attr(href)"
                ),
                company_selector=(
                    config.selectors.get("company") if configured else ".company"
                ),
                location_selector=(
                    config.selectors.get("location") if configured else ".location"
                ),
                description_selector=(
                    config.selectors.get("summary") if configured else None
                ),
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
        return ParsedPage(
            records,
            len(cards),
            next_url or None,
            pagination_observable=not public_list_has_more(page, config) and (
                "next" in config.selectors or config.single_page
            ),
            card_method=selection.method,
        )
