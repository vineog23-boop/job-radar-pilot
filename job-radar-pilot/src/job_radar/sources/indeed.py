from __future__ import annotations

from dataclasses import replace
from urllib.parse import urlsplit, urlunsplit

from job_radar.models import SourceConfig
from job_radar.sources.base import PaginatedAdapter, ParsedPage, make_record


class IndeedAdapter(PaginatedAdapter):
    def parse_page(self, page: object, config: SourceConfig) -> ParsedPage:
        cards = page.css(".job_seen_beacon")  # type: ignore[attr-defined]
        records = []
        for card in cards:
            record = make_record(
                config=config,
                page=page,
                card=card,
                id_selector="a::attr(data-jk)",
                title_selector="h2",
                url_selector="a::attr(href)",
                company_selector="[data-testid='company-name']",
                location_selector="[data-testid='text-location']",
            )
            if record and record.source_job_id:
                parsed = urlsplit(record.canonical_url)
                record = replace(
                    record,
                    canonical_url=urlunsplit(
                        (
                            parsed.scheme,
                            parsed.netloc,
                            "/viewjob",
                            f"jk={record.source_job_id}",
                            "",
                        )
                    ),
                )
            if record:
                records.append(record)
        next_value = page.css("a[data-testid='pagination-page-next']::attr(href)").get()  # type: ignore[attr-defined]
        next_url = page.urljoin(next_value) if next_value else None  # type: ignore[attr-defined]
        return ParsedPage(tuple(records), len(cards), next_url)
