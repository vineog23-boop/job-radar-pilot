from __future__ import annotations

from dataclasses import replace
from urllib.parse import urlsplit, urlunsplit

from job_radar.models import SourceConfig
from job_radar.sources.base import PaginatedAdapter, ParsedPage, make_record


_HEX_SEQUENCE = "0123456789abcdef"
_SYNTHETIC_JKS = {
    "a1b2c3d4e5f67890",
    "f1e2d3c4b5a67890",
    "0f1e2d3c4b5a6978",
}


def _is_synthetic_jk(value: str) -> bool:
    normalized = value.casefold()
    rotations = {
        sequence[index:] + sequence[:index]
        for sequence in (_HEX_SEQUENCE, _HEX_SEQUENCE[::-1])
        for index in range(len(sequence))
    }
    return normalized in rotations or normalized in _SYNTHETIC_JKS


class IndeedAdapter(PaginatedAdapter):
    def parse_page(self, page: object, config: SourceConfig) -> ParsedPage:
        cards = page.css(".job_seen_beacon")  # type: ignore[attr-defined]
        records = []
        for card in cards:
            has_current_title = bool(
                card.css("h3 a span::attr(title)").get()
            )
            record = make_record(
                config=config,
                page=page,
                card=card,
                id_selector="a::attr(data-jk)",
                title_selector=(
                    "h3 a span::attr(title)" if has_current_title else "h2"
                ),
                url_selector="a::attr(href)",
                company_selector="[data-testid='company-name']",
                location_selector="[data-testid='text-location']",
            )
            if (
                record
                and record.source_job_id
                and _is_synthetic_jk(record.source_job_id)
            ):
                record = None
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
