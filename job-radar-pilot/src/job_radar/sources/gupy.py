from __future__ import annotations

from job_radar.models import SourceConfig
from job_radar.sources.base import PaginatedAdapter, ParsedPage, make_record


class GupyAdapter(PaginatedAdapter):
    def parse_page(self, page: object, config: SourceConfig) -> ParsedPage:
        cards = page.css("[data-testid='job-card']")  # type: ignore[attr-defined]
        records = tuple(
            record
            for card in cards
            if (
                record := make_record(
                    config=config,
                    page=page,
                    card=card,
                    id_selector="::attr(data-job-id)",
                    title_selector="h2",
                    url_selector="a::attr(href)",
                    company_selector="[data-testid='company-name']",
                    location_selector="[data-testid='job-location']",
                )
            )
        )
        return ParsedPage(records, len(cards), pagination_observable=False)
