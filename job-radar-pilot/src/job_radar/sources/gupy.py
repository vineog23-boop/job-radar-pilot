from __future__ import annotations

from job_radar.models import SourceConfig
from job_radar.sources.base import PaginatedAdapter, ParsedPage, make_record


class GupyAdapter(PaginatedAdapter):
    def parse_page(self, page: object, config: SourceConfig) -> ParsedPage:
        legacy_cards = page.css("[data-testid='job-card']")  # type: ignore[attr-defined]
        current_cards = page.css("a[href*='/job/']") if not legacy_cards else ()  # type: ignore[attr-defined]
        cards = legacy_cards or current_cards
        records = tuple(
            record
            for card in cards
            if (
                record := make_record(
                    config=config,
                    page=page,
                    card=card,
                    id_selector=(None if current_cards else "::attr(data-job-id)"),
                    title_selector=("h3" if current_cards else "h2"),
                    url_selector=("::attr(href)" if current_cards else "a::attr(href)"),
                    company_selector=("p" if current_cards else "[data-testid='company-name']"),
                    location_selector="[data-testid='job-location']",
                )
            )
        )
        return ParsedPage(records, len(cards), pagination_observable=False)
