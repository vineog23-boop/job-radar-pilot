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
    return _html_page(html, url)


def _html_page(html: str, url: str) -> SimpleNamespace:
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
    max_pages: int = 3,
) -> SourceConfig:
    return SourceConfig(
        code=code,
        kind=kind,
        start_url=url,
        enabled=True,
        max_pages=max_pages,
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


def test_pagination_stops_at_empty_page_after_valid_records() -> None:
    first_url = "https://example.com/jobs"
    second_url = "https://example.com/jobs?page=2"
    third_url = "https://example.com/jobs?page=3"
    fetcher = FixtureFetcher(
        {
            first_url: _html_page(
                """
                <article class="job"><a href="/jobs/1"><h2>Java Junior</h2></a></article>
                <a class="next" href="/jobs?page=2">Proxima</a>
                """,
                first_url,
            ),
            second_url: _html_page(
                '<p>Nenhuma vaga nesta pagina.</p><a class="next" href="/jobs?page=3">Proxima</a>',
                second_url,
            ),
            third_url: _html_page(
                '<a class="next" href="/jobs?page=4">Proxima</a>',
                third_url,
            ),
        }
    )
    config = _config(
        SourceKind.GENERIC,
        selectors={
            "card": "article.job",
            "title": "h2",
            "url": "a::attr(href)",
            "next": "a.next::attr(href)",
        },
    )

    result = GenericListAdapter().collect(config, fetcher)  # type: ignore[arg-type]

    assert result.status is CollectionStatus.PARTIAL
    assert result.stop_reason == "EMPTY_PAGE_AFTER_RECORDS"
    assert result.has_more is True
    assert result.pages_observed == 2
    assert len(result.records) == 1
    assert fetcher.calls == [first_url, second_url]


def test_single_page_limit_does_not_prove_unobservable_pagination_exhausted() -> None:
    url = "https://example.com/jobs"
    config = _config(
        SourceKind.GENERIC,
        max_pages=1,
        selectors={
            "card": "article.job",
            "title": "h2",
            "url": "a::attr(href)",
        },
    )
    page = _html_page(
        '<article class="job"><a href="/jobs/1"><h2>Java Junior</h2></a></article>',
        url,
    )

    result = GenericListAdapter().collect(
        config,
        FixtureFetcher({url: page}),  # type: ignore[arg-type]
    )

    assert result.status is CollectionStatus.PARTIAL
    assert result.stop_reason == "PAGINATION_UNVERIFIED"
    assert result.has_more is True
    assert len(result.records) == 1


def test_generic_can_join_descendant_text_and_capture_summary() -> None:
    url = "https://example.com/jobs"
    page = _html_page(
        """
        <article class="job">
          <a class="title" href="/1">Desenvolvedor <mark>Java</mark> Jr</a>
          <span class="location"><i></i>100% <strong>Remoto</strong></span>
          <p class="summary">APIs <em>Spring Boot</em></p>
        </article>
        """,
        url,
    )
    config = _config(
        SourceKind.GENERIC,
        selectors={
            "card": "article.job",
            "title": ".title::all-text",
            "url": ".title::attr(href)",
            "location": ".location::all-text",
            "summary": ".summary::all-text",
        },
    )

    parsed = GenericListAdapter().parse_page(page, config)

    assert parsed.records[0].title == "Desenvolvedor Java Jr"
    assert parsed.records[0].location == "100% Remoto"
    assert parsed.records[0].description_summary == "APIs Spring Boot"


def test_generic_declared_count_proves_single_page_exhausted() -> None:
    url = "https://example.com/collection"
    cards = "".join(
        f'<article class="job"><a href="/jobs/{index}"><h2>Vaga {index}</h2></a></article>'
        for index in range(4)
    )
    page = _html_page(
        f'<p class="count">4 oportunidades nesta coleção</p>{cards}',
        url,
    )
    config = _config(
        SourceKind.GENERIC,
        selectors={
            "card": "article.job",
            "title": "h2",
            "url": "a::attr(href)",
            "declared_count": ".count::all-text",
        },
    )

    parsed = GenericListAdapter().parse_page(page, config)

    assert parsed.pagination_observable is True
    assert len(parsed.records) == 4


def test_generic_declared_count_keeps_incomplete_page_partial() -> None:
    url = "https://example.com/collection"
    page = _html_page(
        '<p class="count">33 oportunidades</p><article class="job"><a href="/jobs/1"><h2>Vaga 1</h2></a></article>',
        url,
    )
    config = _config(
        SourceKind.GENERIC,
        selectors={
            "card": "article.job",
            "title": "h2",
            "url": "a::attr(href)",
            "declared_count": ".count::all-text",
        },
    )

    parsed = GenericListAdapter().parse_page(page, config)

    assert parsed.pagination_observable is False


def test_gupy_exposes_numeric_next_page_url() -> None:
    url = "https://portal.gupy.io/job-search/term%3Destagio%20tecnologia"
    page = _html_page(
        """
        <div id="job-listing-results">
          <li><a href="https://acme.gupy.io/job/TOKEN-1"><h3>Estágio Java</h3></a></li>
        </div>
        <button aria-current="page" aria-label="Página 1">1</button>
        <button aria-label="Próxima página">Próxima</button>
        """,
        url,
    )

    parsed = GupyAdapter().parse_page(
        page,
        _config(SourceKind.GUPY, code="gupy", url=url),
    )

    assert parsed.next_url == f"{url}?page=2"
    assert parsed.pagination_observable is True


def test_gupy_disabled_next_button_proves_last_page() -> None:
    url = "https://portal.gupy.io/job-search/term%3Destagio%20tecnologia?page=2"
    page = _html_page(
        """
        <div id="job-listing-results">
          <li><a href="https://acme.gupy.io/job/TOKEN-2"><h3>Estágio Backend</h3></a></li>
        </div>
        <button aria-current="page" aria-label="Página 2">2</button>
        <button aria-label="Próxima página" disabled>Próxima</button>
        """,
        url,
    )

    parsed = GupyAdapter().parse_page(
        page,
        _config(SourceKind.GUPY, code="gupy", url=url),
    )

    assert parsed.next_url is None
    assert parsed.pagination_observable is True


def test_gupy_uses_enabled_next_when_responsive_controls_are_duplicated() -> None:
    url = "https://portal.gupy.io/job-search/term%3Destagio%20tecnologia"
    page = _html_page(
        """
        <div id="job-listing-results">
          <li><a href="https://acme.gupy.io/job/TOKEN-1"><h3>Estágio Java</h3></a></li>
        </div>
        <button aria-current="page" aria-label="Página 1">1</button>
        <button aria-label="Próxima página" disabled>Próxima</button>
        <button aria-label="Próxima página">Próxima</button>
        """,
        url,
    )

    parsed = GupyAdapter().parse_page(
        page,
        _config(SourceKind.GUPY, code="gupy", url=url),
    )

    assert parsed.next_url == f"{url}?page=2"
    assert parsed.pagination_observable is True


def test_gupy_uses_future_numeric_page_when_next_control_is_absent() -> None:
    url = "https://portal.gupy.io/job-search/term%3Destagio%20tecnologia"
    page = _html_page(
        """
        <div id="job-listing-results">
          <li><a href="https://acme.gupy.io/job/TOKEN-1"><h3>Estágio Java</h3></a></li>
        </div>
        <button aria-current="page" aria-label="Página 1">1</button>
        <button aria-label="Página 2">2</button>
        """,
        url,
    )

    parsed = GupyAdapter().parse_page(
        page,
        _config(SourceKind.GUPY, code="gupy", url=url),
    )

    assert parsed.next_url == f"{url}?page=2"
    assert parsed.pagination_observable is True


def test_gupy_ignores_job_links_outside_listing() -> None:
    url = "https://portal.gupy.io/job-search/term%3Djava"
    page = _html_page(
        """
        <aside><a href="https://other.gupy.io/job/RECOMMENDED"><h3>Recomendada</h3></a></aside>
        <div id="job-listing-results">
          <li><a href="https://acme.gupy.io/job/REAL"><h3>Java Júnior</h3></a></li>
        </div>
        """,
        url,
    )

    parsed = GupyAdapter().parse_page(
        page,
        _config(SourceKind.GUPY, code="gupy", url=url),
    )

    assert parsed.cards_observed == 1
    assert [record.source_job_id for record in parsed.records] == ["REAL"]


def test_gupy_without_pagination_evidence_stays_partial() -> None:
    url = "https://portal.gupy.io/job-search/term%3Djava"
    page = _html_page(
        """
        <div id="job-listing-results">
          <li><a href="https://acme.gupy.io/job/REAL"><h3>Java Júnior</h3></a></li>
        </div>
        """,
        url,
    )

    result = GupyAdapter().collect(
        _config(SourceKind.GUPY, code="gupy", url=url),
        FixtureFetcher({url: page}),  # type: ignore[arg-type]
    )

    assert result.status is CollectionStatus.PARTIAL
    assert result.stop_reason == "PAGINATION_UNVERIFIED"
    assert result.has_more is True


def test_gupy_page_limit_with_continuation_stays_partial() -> None:
    url = "https://portal.gupy.io/job-search/term%3Djava"
    page = _html_page(
        """
        <div id="job-listing-results">
          <li><a href="https://acme.gupy.io/job/REAL"><h3>Java Júnior</h3></a></li>
        </div>
        <button aria-current="page" aria-label="Página 1">1</button>
        <button aria-label="Próxima página">Próxima</button>
        """,
        url,
    )

    result = GupyAdapter().collect(
        _config(SourceKind.GUPY, code="gupy", url=url, max_pages=1),
        FixtureFetcher({url: page}),  # type: ignore[arg-type]
    )

    assert result.status is CollectionStatus.PARTIAL
    assert result.stop_reason == "PAGE_LIMIT"
    assert result.has_more is True


def test_99jobs_declared_total_proves_collection_exhausted() -> None:
    url = "https://99jobs.com/collections/example"
    cards = "".join(
        f'<section class="fr_opportunity opportunity-collections"><h3>Vaga {index}</h3>'
        f'<a class="btn btn-block btn-sort" href="https://99jobs.com/vagas/{index}">Ver vaga</a></section>'
        for index in range(4)
    )
    page = _html_page(
        f'<div id="opportunities"><p class="text-center qtd">4 oportunidades</p>{cards}</div>',
        url,
    )
    config = _config(
        SourceKind.GENERIC,
        code="99jobs",
        url=url,
        max_pages=1,
        selectors={
            "card": "#opportunities section.fr_opportunity.opportunity-collections",
            "title": "h3::all-text",
            "url": "a.btn.btn-block.btn-sort::attr(href)",
            "declared_count": "#opportunities > p.text-center.qtd::all-text",
        },
    )

    result = GenericListAdapter().collect(
        config,
        FixtureFetcher({url: page}),  # type: ignore[arg-type]
    )

    assert result.status is CollectionStatus.SUCCESS
    assert result.has_more is False
    assert result.stop_reason is None
    assert len(result.records) == 4


def test_99jobs_incomplete_declared_total_stays_partial() -> None:
    url = "https://99jobs.com/collections/example"
    page = _html_page(
        """
        <div id="opportunities">
          <p class="text-center qtd">4 oportunidades</p>
          <section class="fr_opportunity opportunity-collections">
            <h3>Vaga 1</h3>
            <a class="btn btn-block btn-sort" href="https://99jobs.com/vagas/1">Ver vaga</a>
          </section>
        </div>
        """,
        url,
    )
    config = _config(
        SourceKind.GENERIC,
        code="99jobs",
        url=url,
        max_pages=1,
        selectors={
            "card": "#opportunities section.fr_opportunity.opportunity-collections",
            "title": "h3::all-text",
            "url": "a.btn.btn-block.btn-sort::attr(href)",
            "declared_count": "#opportunities > p.text-center.qtd::all-text",
        },
    )

    result = GenericListAdapter().collect(
        config,
        FixtureFetcher({url: page}),  # type: ignore[arg-type]
    )

    assert result.status is CollectionStatus.PARTIAL
    assert result.stop_reason == "PAGINATION_UNVERIFIED"
    assert result.has_more is True


def test_gupy_extracts_strong_identity() -> None:
    url = "https://portal.gupy.io/"
    result = GupyAdapter().collect(
        _config(SourceKind.GUPY, code="gupy", url=url),
        FixtureFetcher({url: _page("gupy.html", url)}),  # type: ignore[arg-type]
    )

    record = result.records[0]
    assert result.status is CollectionStatus.PARTIAL
    assert result.stop_reason == "PAGINATION_UNVERIFIED"
    assert result.has_more is True
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


def test_indeed_extracts_current_h3_title_markup() -> None:
    url = "https://br.indeed.com/jobs?q=java+junior"
    page = _html_page(
        """
        <div class="job_seen_beacon">
          <h3 class="jobTitle">
            <a data-jk="current123" href="/rc/clk?jk=current123&amp;session=secret">
              <span title="Desenvolvedor BackEnd Java Jr">Desenvolvedor BackEnd Java Jr</span>
            </a>
          </h3>
          <span data-testid="company-name">Empresa Atual</span>
          <div data-testid="text-location">Remoto</div>
        </div>
        """,
        url,
    )

    parsed = IndeedAdapter().parse_page(
        page,
        _config(SourceKind.INDEED, code="indeed", url=url),
    )

    assert len(parsed.records) == 1
    assert parsed.records[0].title == "Desenvolvedor BackEnd Java Jr"
    assert parsed.records[0].source_job_id == "current123"
    assert parsed.records[0].canonical_url == "https://br.indeed.com/viewjob?jk=current123"


def test_indeed_discards_obvious_synthetic_job_keys() -> None:
    url = "https://br.indeed.com/jobs?q=java+junior"
    page = _html_page(
        """
        <div class="job_seen_beacon">
          <h3><a data-jk="123456789abcdef0" href="/rc/clk?jk=123456789abcdef0"><span title="Vaga armadilha">Vaga armadilha</span></a></h3>
        </div>
        <div class="job_seen_beacon">
          <h3><a data-jk="a1b2c3d4e5f67890" href="/rc/clk?jk=a1b2c3d4e5f67890"><span title="Vaga sintética">Vaga sintética</span></a></h3>
        </div>
        <div class="job_seen_beacon">
          <h3><a data-jk="4e69f254a676b746" href="/rc/clk?jk=4e69f254a676b746"><span title="Java Junior real">Java Junior real</span></a></h3>
        </div>
        """,
        url,
    )

    parsed = IndeedAdapter().parse_page(
        page,
        _config(SourceKind.INDEED, code="indeed", url=url),
    )

    assert parsed.cards_observed == 3
    assert [record.source_job_id for record in parsed.records] == ["4e69f254a676b746"]


def test_dynamic_extracts_visible_cards() -> None:
    url = "https://app.example.com/opportunities"
    result = DynamicAdapter().collect(
        _config(SourceKind.DYNAMIC, code="eureca", url=url),
        FixtureFetcher({url: _page("dynamic.html", url)}),  # type: ignore[arg-type]
    )

    assert result.records[0].source_job_id == "DYN-42"
    assert result.records[0].canonical_url == "https://app.example.com/opportunities/DYN-42"


def test_dynamic_uses_portal_specific_selectors_when_configured() -> None:
    url = "https://app.example.com/opportunities"
    page = _html_page(
        """
        <div data-testid="opportunities-list-card-42">
          <a href="/vagas/42" aria-label="Estágio em Desenvolvimento Java">
            <h3>Estágio em <mark>Desenvolvimento Java</mark></h3>
          </a>
          <span class="local">Remoto - Brasil</span>
        </div>
        """,
        url,
    )
    config = _config(
        SourceKind.DYNAMIC,
        code="eureca",
        url=url,
        selectors={
            "card": "[data-testid^='opportunities-list-card-']",
            "title": "h3::all-text",
            "url": "a[href^='/vagas/']::attr(href)",
            "location": ".local::all-text",
        },
    )

    parsed = DynamicAdapter().parse_page(page, config)

    assert parsed.cards_observed == 1
    assert parsed.records[0].title == "Estágio em Desenvolvimento Java"
    assert parsed.records[0].canonical_url == "https://app.example.com/vagas/42"
    assert parsed.records[0].location == "Remoto - Brasil"


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


def test_login_block_after_records_preserves_partial_coverage() -> None:
    first_url = "https://example.com/jobs"
    second_url = "https://example.com/jobs?page=2"
    blocked = FetchResult(
        CollectionStatus.BLOCKED,
        block_reason=BlockReason.LOGIN_REQUIRED,
        error="LOGIN_REQUIRED em https://example.com/jobs",
        attempts=1,
    )
    config = _config(
        SourceKind.GENERIC,
        selectors={
            "card": "article.job",
            "title": "h2",
            "url": "a::attr(href)",
            "next": "a.next::attr(href)",
        },
    )

    result = GenericListAdapter().collect(
        config,
        FixtureFetcher(
            {
                first_url: _page("generic-page-1.html", first_url),
                second_url: blocked,
            }
        ),  # type: ignore[arg-type]
    )

    assert result.status is CollectionStatus.PARTIAL
    assert result.stop_reason == "LOGIN_REQUIRED"
    assert len(result.records) == 1


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


def test_observed_cards_without_valid_records_is_parse_error() -> None:
    url = "https://example.com/jobs"
    malformed_page = _html_page(
        '<article class="job"><h2>Vaga sem link</h2></article>',
        url,
    )
    config = _config(
        SourceKind.GENERIC,
        selectors={"card": "article.job", "title": "h2", "url": "a::attr(href)"},
    )

    result = GenericListAdapter().collect(
        config,
        FixtureFetcher({url: malformed_page}),  # type: ignore[arg-type]
    )

    assert result.status is CollectionStatus.ERROR
    assert result.stop_reason == "PARSE_ZERO_RECORDS"
    assert result.cards_observed == 1
    assert result.records == ()


def test_observed_cards_without_records_after_valid_page_is_partial() -> None:
    first_url = "https://example.com/jobs"
    second_url = "https://example.com/jobs?page=2"
    malformed_page = _html_page(
        '<article class="job"><h2>Vaga sem link</h2></article>',
        second_url,
    )
    config = _config(
        SourceKind.GENERIC,
        selectors={
            "card": "article.job",
            "title": "h2",
            "url": "a::attr(href)",
            "next": "a.next::attr(href)",
        },
    )

    result = GenericListAdapter().collect(
        config,
        FixtureFetcher(
            {
                first_url: _page("generic-page-1.html", first_url),
                second_url: malformed_page,
            }
        ),  # type: ignore[arg-type]
    )

    assert result.status is CollectionStatus.PARTIAL
    assert result.stop_reason == "PARSE_ZERO_RECORDS"
    assert result.cards_observed == 2
    assert len(result.records) == 1


def test_explicit_empty_marker_remains_empty() -> None:
    url = "https://example.com/jobs"
    config = _config(
        SourceKind.GENERIC,
        selectors={"card": "article.job", "title": "h2", "url": "a::attr(href)"},
    )

    result = GenericListAdapter().collect(
        config,
        FixtureFetcher({url: _html_page("<p>No jobs found</p>", url)}),  # type: ignore[arg-type]
    )

    assert result.status is CollectionStatus.EMPTY
    assert result.stop_reason == "NO_RESULTS"
    assert result.cards_observed == 0
    assert result.records == ()


def test_factory_supports_every_configured_source() -> None:
    sources = load_sources(PROJECT / "config" / "sources.yaml")

    adapters = {source.code: adapter_for(source) for source in sources}

    assert set(adapters) == {source.code for source in sources}
    assert isinstance(adapters["gupy"], GupyAdapter)
    assert isinstance(adapters["indeed"], IndeedAdapter)
    assert isinstance(adapters["programathor"], GenericListAdapter)
    assert isinstance(adapters["eureca"], DynamicAdapter)
