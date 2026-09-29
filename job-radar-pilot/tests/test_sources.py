from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scrapling.parser import Adaptor

from job_radar.config import load_sources
from job_radar.fetching import BlockReason, FetchResult
from job_radar.models import CollectionStatus, SourceConfig, SourceKind
from job_radar.sources import adapter_for
from job_radar.sources.dynamic import DynamicAdapter
from job_radar.sources.generic import GenericListAdapter
from job_radar.sources.gupy import GupyAdapter
from job_radar.sources.indeed import IndeedAdapter


PROJECT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _page(name: str, url: str) -> SimpleNamespace:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    adaptor = Adaptor(html, url=url)
    return SimpleNamespace(
        status=200,
        text=html,
        url=url,
        css=adaptor.css,
        urljoin=adaptor.urljoin,
    )


class FixtureFetcher:
    def __init__(self, pages: dict[str, object]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def fetch(self, url: str, source: SourceConfig) -> FetchResult:
        self.calls.append(url)
        value = self.pages[url]
        if isinstance(value, FetchResult):
            return value
        return FetchResult(CollectionStatus.SUCCESS, response=value, attempts=1)  # type: ignore[arg-type]


def _config(
    kind: SourceKind,
    *,
    code: str = "example",
    url: str = "https://example.com/jobs",
    selectors: dict[str, str] | None = None,
    requires_auth: bool = False,
) -> SourceConfig:
    return SourceConfig(
        code=code,
        kind=kind,
        start_url=url,
        enabled=True,
        max_pages=3,
        min_interval_seconds=1,
        requires_auth=requires_auth,
        selectors=selectors or {},
    )


def test_generic_extracts_relative_links_partial_fields_and_pagination() -> None:
    first_url = "https://example.com/jobs"
    second_url = "https://example.com/jobs?page=2"
    fetcher = FixtureFetcher(
        {
            first_url: _page("generic-page-1.html", first_url),
            second_url: _page("generic-page-2.html", second_url),
        }
    )
    config = _config(
        SourceKind.GENERIC,
        selectors={
            "card": "article.job",
            "id": "::attr(data-job-id)",
            "title": "h2",
            "url": "a::attr(href)",
            "company": ".company",
            "location": ".location",
            "next": "a.next::attr(href)",
        },
    )

    result = GenericListAdapter().collect(config, fetcher)  # type: ignore[arg-type]

    assert result.status is CollectionStatus.SUCCESS
    assert result.pages_observed == 2
    assert result.cards_observed == 2
    assert result.records[0].source_job_id == "GEN-1"
    assert result.records[0].canonical_url == "https://example.com/jobs/gen-1"
    assert result.records[0].company == "Acme"
    assert result.records[1].company is None
    assert result.records[1].location is None


def test_gupy_extracts_strong_identity() -> None:
    url = "https://portal.gupy.io/"
    result = GupyAdapter().collect(
        _config(SourceKind.GUPY, code="gupy", url=url),
        FixtureFetcher({url: _page("gupy.html", url)}),  # type: ignore[arg-type]
    )

    record = result.records[0]
    assert record.source_job_id == "a1b2-c3d4"
    assert record.title == "Analista Desenvolvedor Java"
    assert record.company == "Empresa Gupy"
    assert record.location == "Remoto - Brasil"


def test_indeed_extracts_jk_and_removes_session_parameters() -> None:
    url = "https://br.indeed.com/jobs"
    result = IndeedAdapter().collect(
        _config(SourceKind.INDEED, code="indeed", url=url),
        FixtureFetcher({url: _page("indeed.html", url)}),  # type: ignore[arg-type]
    )

    record = result.records[0]
    assert record.source_job_id == "indeed123"
    assert record.canonical_url == "https://br.indeed.com/viewjob?jk=indeed123"
    assert record.company == "Empresa Indeed"


def test_dynamic_extracts_visible_cards() -> None:
    url = "https://app.example.com/opportunities"
    result = DynamicAdapter().collect(
        _config(SourceKind.DYNAMIC, code="eureca", url=url),
        FixtureFetcher({url: _page("dynamic.html", url)}),  # type: ignore[arg-type]
    )

    assert result.records[0].source_job_id == "DYN-42"
    assert result.records[0].canonical_url == "https://app.example.com/opportunities/DYN-42"


def test_login_block_becomes_auth_handoff() -> None:
    url = "https://example.com/jobs"
    blocked = FetchResult(
        CollectionStatus.BLOCKED,
        block_reason=BlockReason.LOGIN_REQUIRED,
        error="LOGIN_REQUIRED em https://example.com/jobs",
        attempts=1,
    )
    result = DynamicAdapter().collect(
        _config(SourceKind.DYNAMIC, requires_auth=True),
        FixtureFetcher({url: blocked}),  # type: ignore[arg-type]
    )

    assert result.status is CollectionStatus.AUTH_REQUIRED
    assert result.stop_reason == "LOGIN_REQUIRED"
    assert result.visited_urls == (url,)


def test_missing_expected_cards_is_explicit_layout_error() -> None:
    url = "https://example.com/jobs"
    config = _config(
        SourceKind.GENERIC,
        selectors={"card": "article.job", "title": "h2", "url": "a::attr(href)"},
    )

    result = GenericListAdapter().collect(
        config,
        FixtureFetcher({url: _page("empty.html", url)}),  # type: ignore[arg-type]
    )

    assert result.status is CollectionStatus.ERROR
    assert result.stop_reason == "LAYOUT_CHANGED"
    assert result.records == ()


def test_factory_supports_every_configured_source() -> None:
    sources = load_sources(PROJECT / "config" / "sources.yaml")

    adapters = {source.code: adapter_for(source) for source in sources}

    assert set(adapters) == {source.code for source in sources}
    assert isinstance(adapters["gupy"], GupyAdapter)
    assert isinstance(adapters["indeed"], IndeedAdapter)
    assert isinstance(adapters["programathor"], GenericListAdapter)
    assert isinstance(adapters["eureca"], DynamicAdapter)
