from __future__ import annotations

from job_radar.models import SourceConfig
from job_radar.sources.base import (
    PaginatedAdapter,
    ParsedPage,
    absolute_url,
    extract_value,
    make_record,
)


class GenericListAdapter(PaginatedAdapter):
    def parse_page(self, page: object, config: SourceConfig) -> ParsedPage:
        cards = page.css(config.selectors["card"])  # type: ignore[attr-defined]
        records = tuple(
            record
            for card in cards
            if (
                record := make_record(
                    config=config,
                    page=page,
                    card=card,
                    id_selector=config.selectors.get("id"),
                    title_selector=config.selectors["title"],
                    url_selector=config.selectors["url"],
                    company_selector=config.selectors.get("company"),
                    location_selector=config.selectors.get("location"),
                )
            )
        )
        next_url = absolute_url(page, extract_value(page, config.selectors.get("next")))
        return ParsedPage(
            records,
            len(cards),
            next_url or None,
            pagination_observable="next" in config.selectors,
        )
