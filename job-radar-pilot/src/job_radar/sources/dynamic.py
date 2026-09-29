from __future__ import annotations

from job_radar.models import SourceConfig
from job_radar.sources.base import (
    PaginatedAdapter,
    ParsedPage,
    absolute_url,
    extract_value,
    make_record_with_fallback,
)


class DynamicAdapter(PaginatedAdapter):
    def parse_page(self, page: object, config: SourceConfig) -> ParsedPage:
        configured = bool(config.selectors.get("card"))
        card_selector = (
            config.selectors["card"]
            if configured
            else "article[data-job-id], [data-job-id]"
        )
        selection = self.select_cards(page, config, card_selector)
        cards = selection.cards
        records = tuple(
            record
            for card in cards
            if (
                record := make_record_with_fallback(
                    card_method=selection.method,
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
            )
        )
        self.remember_cards(page, config, card_selector, selection, records)
        next_url = absolute_url(page, extract_value(page, config.selectors.get("next")))
        return ParsedPage(
            records,
            len(cards),
            next_url or None,
            pagination_observable="next" in config.selectors,
            card_method=selection.method,
        )
