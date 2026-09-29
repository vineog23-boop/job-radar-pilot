from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
        next_buttons = page.css("button[aria-label='Próxima página']")  # type: ignore[attr-defined]
        page_buttons = page.css("button[aria-label^='Página ']")  # type: ignore[attr-defined]
        next_enabled = bool(next_buttons) and all(
            "disabled" not in getattr(button, "attrib", {})
            and getattr(button, "attrib", {}).get("aria-disabled") != "true"
            for button in next_buttons
        )
        next_url = self._next_page_url(str(page.url)) if next_enabled else None
        return ParsedPage(
            records,
            len(cards),
            next_url=next_url,
            pagination_observable=bool(next_buttons or page_buttons),
        )

    @staticmethod
    def _next_page_url(url: str) -> str:
        parsed = urlsplit(url)
        parameters = dict(parse_qsl(parsed.query, keep_blank_values=True))
        try:
            current_page = int(parameters.get("page", "1"))
        except ValueError:
            current_page = 1
        parameters["page"] = str(current_page + 1)
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(parameters),
                "",
            )
        )
