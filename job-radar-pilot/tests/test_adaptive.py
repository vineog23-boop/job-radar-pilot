from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest
from scrapling.parser import Adaptor

from job_radar.adaptive import AdaptiveCardLocator, adaptive_db_path, select_cards
from job_radar.fetching import FetchResult
from job_radar.models import CollectionStatus, SourceConfig, SourceKind
from job_radar.sources.generic import GenericListAdapter
from job_radar.sources.dynamic import DynamicAdapter
from job_radar.sources.gupy import GupyAdapter
from job_radar.sources.indeed import IndeedAdapter


FIXTURES = Path(__file__).resolve().parent / "fixtures"
URL = "https://jobs.example.com/search?page=1&session=signed"
SELECTOR = "article.job-card"


def _page(fixture: str) -> Adaptor:
    return Adaptor((FIXTURES / fixture).read_bytes(), url=URL)


class _Fetcher:
    def __init__(self, page: object) -> None:
        self.page = page

    def fetch(self, url: str, source: SourceConfig) -> FetchResult:
        return FetchResult(CollectionStatus.SUCCESS, response=self.page, attempts=1)  # type: ignore[arg-type]


def _config(*, adaptive: bool = True, code: str = "example") -> SourceConfig:
    return SourceConfig(
        code=code,
        kind=SourceKind.GENERIC,
        start_url=URL,
        enabled=True,
        max_pages=1,
        min_interval_seconds=1,
        requires_auth=False,
        selectors={
            "card": SELECTOR,
            "title": ".title-v1::all-text",
            "url": ".title-v1 a::attr(href)",
            "declared_count": ".declared-count::all-text",
        },
        adaptive=adaptive,
    )


def test_adaptive_db_path_uses_local_app_data_and_safe_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = tmp_path / "Local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    assert adaptive_db_path() == local / "JobRadar" / "adaptive" / "adaptive.db"

    monkeypatch.delenv("LOCALAPPDATA")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    assert adaptive_db_path() == (
        tmp_path / "home" / "AppData" / "Local" / "JobRadar" / "adaptive" / "adaptive.db"
    )


def test_select_cards_without_fingerprint_keeps_none_and_does_not_create_db(
    tmp_path: Path,
) -> None:
    database = tmp_path / "adaptive.db"
    selection = select_cards(
        _page("adaptive-v2.html"),
        source_code="example",
        selector=SELECTOR,
        locator=AdaptiveCardLocator(database),
    )

    assert selection.method == "NONE"
    assert selection.cards == ()
    assert database.exists() is False


def test_invalid_stored_fingerprint_fails_closed_as_layout_changed(
    tmp_path: Path,
) -> None:
    database = tmp_path / "adaptive.db"
    locator = AdaptiveCardLocator(database)
    locator.remember(_page("adaptive-v1.html"), "example", SELECTOR)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE adaptive_fingerprints SET fingerprint = ?",
            ("{invalid-json",),
        )
        connection.commit()

    result = GenericListAdapter(locator=AdaptiveCardLocator(database)).collect(
        _config(),
        _Fetcher(_page("adaptive-v2.html")),
    )

    assert result.status is CollectionStatus.ERROR
    assert result.stop_reason == "LAYOUT_CHANGED"
    assert result.warnings == ()


def test_corrupted_sqlite_file_fails_closed_as_layout_changed(
    tmp_path: Path,
) -> None:
    database = tmp_path / "adaptive.db"
    corrupt_bytes = b"not-a-sqlite-database"
    database.write_bytes(corrupt_bytes)

    result = GenericListAdapter(locator=AdaptiveCardLocator(database)).collect(
        _config(),
        _Fetcher(_page("adaptive-v2.html")),
    )

    assert result.status is CollectionStatus.ERROR
    assert result.stop_reason == "LAYOUT_CHANGED"
    assert result.warnings == ()
    assert database.read_bytes() == corrupt_bytes


def test_corrupted_sqlite_file_does_not_discard_configured_records(
    tmp_path: Path,
) -> None:
    database = tmp_path / "adaptive.db"
    corrupt_bytes = b"not-a-sqlite-database"
    database.write_bytes(corrupt_bytes)

    result = GenericListAdapter(locator=AdaptiveCardLocator(database)).collect(
        _config(),
        _Fetcher(_page("adaptive-v1.html")),
    )

    assert result.status is CollectionStatus.SUCCESS
    assert [record.title for record in result.records] == [
        "Java Júnior",
        "Estágio Backend",
    ]
    assert database.read_bytes() == corrupt_bytes


def test_remember_persists_only_sanitized_structure_and_relocates_job_cards(
    tmp_path: Path,
) -> None:
    database = tmp_path / "adaptive.db"
    locator = AdaptiveCardLocator(database)
    locator.remember(_page("adaptive-v1.html"), "example", SELECTOR)

    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT origin, source_code, selector, fingerprint "
            "FROM adaptive_fingerprints"
        ).fetchall()

    assert len(rows) == 1
    origin, source_code, selector, raw_fingerprint = rows[0]
    fingerprint = json.loads(raw_fingerprint)
    assert origin == "https://jobs.example.com"
    assert source_code == "example"
    assert selector == SELECTOR
    assert fingerprint["element"]["tag"] == "article"
    assert fingerprint["element"]["attributes"] == {"class": "job-card"}
    assert "text" not in json.dumps(fingerprint).casefold()
    assert "href" not in json.dumps(fingerprint).casefold()
    assert "secret-101" not in raw_fingerprint
    assert "Java Júnior" not in raw_fingerprint

    selection = select_cards(
        _page("adaptive-v2.html"),
        source_code="example",
        selector=SELECTOR,
        locator=locator,
    )

    assert selection.method == "ADAPTIVE"
    assert len(selection.cards) == 3
    assert {
        " ".join(card.css("h3")[0].css("::text").getall()).strip()
        for card in selection.cards
    } == {"Java Júnior", "Estágio Backend", "Card sem link"}


def test_remember_removes_origin_credentials_and_sensitive_class_tokens(
    tmp_path: Path,
) -> None:
    database = tmp_path / "adaptive.db"
    page = Adaptor(
        """
        <main class="jobs-list session-private-42">
          <article class="job-card layout-grid token-super-secret xQ9aB3cD7eF1gH5iJ8kL2mN6">
            <h2>Java Junior</h2><a href="/jobs/1">Detalhes</a>
          </article>
        </main>
        """,
        url="https://collector-user:collector-password@jobs.example.com/search",
    )

    AdaptiveCardLocator(database).remember(page, "example", "article")

    with sqlite3.connect(database) as connection:
        origin, raw_fingerprint = connection.execute(
            "SELECT origin, fingerprint FROM adaptive_fingerprints"
        ).fetchone()
    fingerprint = json.loads(raw_fingerprint)

    assert origin == "https://jobs.example.com"
    assert fingerprint["element"]["attributes"] == {
        "class": "job-card layout-grid"
    }
    assert fingerprint["scope"] == [{"tag": "main", "classes": ["jobs-list"]}]
    assert "collector-user" not in raw_fingerprint
    assert "collector-password" not in raw_fingerprint
    assert "private-42" not in raw_fingerprint
    assert "super-secret" not in raw_fingerprint
    assert "xQ9aB3cD7eF1gH5iJ8kL2mN6" not in raw_fingerprint


def test_remember_once_per_execution_and_keeps_only_latest_between_executions(
    tmp_path: Path,
) -> None:
    database = tmp_path / "adaptive.db"
    first = AdaptiveCardLocator(database)
    first.remember(_page("adaptive-v1.html"), "example", SELECTOR)
    changed_page = Adaptor(
        '<div class="other-list"><article class="job-card"><h2>Outra</h2><a href="/2">Detalhes</a></article></div>',
        url=URL,
    )
    first.remember(changed_page, "example", SELECTOR)

    with sqlite3.connect(database) as connection:
        first_payload = json.loads(
            connection.execute(
                "SELECT fingerprint FROM adaptive_fingerprints"
            ).fetchone()[0]
        )
    assert first_payload["scope"][0]["classes"] == ["jobs-list"]

    AdaptiveCardLocator(database).remember(changed_page, "example", SELECTOR)
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT fingerprint FROM adaptive_fingerprints"
        ).fetchall()

    assert len(rows) == 1
    assert json.loads(rows[0][0])["scope"][0]["classes"] == ["other-list"]


def test_select_cards_deduplicates_different_wrappers_for_same_node(
    tmp_path: Path,
) -> None:
    page = Adaptor("<main><article class='job'><h2>Java</h2></article></main>", url=URL)

    class DuplicateLocator:
        def relocate(self, page: object, source_code: str, selector: str):
            return (page.css("article")[0], page.css("article")[0])

    selection = select_cards(
        page,
        source_code="example",
        selector="article.missing",
        locator=DuplicateLocator(),  # type: ignore[arg-type]
    )

    assert selection.method == "ADAPTIVE"
    assert len(selection.cards) == 1


def test_generic_adapter_remembers_only_valid_page_and_recovers_safe_records(
    tmp_path: Path,
) -> None:
    locator = AdaptiveCardLocator(tmp_path / "adaptive.db")
    adapter = GenericListAdapter(locator=locator)

    learned = adapter.collect(_config(), _Fetcher(_page("adaptive-v1.html")))
    recovered = adapter.collect(_config(), _Fetcher(_page("adaptive-v2.html")))

    assert learned.status is CollectionStatus.SUCCESS
    assert recovered.status is CollectionStatus.PARTIAL
    assert recovered.stop_reason == "SELECTOR_RELOCATED"
    assert recovered.warnings == ("SELECTOR_RELOCATED:card",)
    assert recovered.cards_observed == 3
    assert [record.title for record in recovered.records] == [
        "Java Júnior",
        "Estágio Backend",
    ]
    assert [record.canonical_url for record in recovered.records] == [
        "https://jobs.example.com/jobs/201",
        "https://jobs.example.com/jobs/202",
    ]
    assert all(
        "EXTRACTION:ADAPTIVE" in record.match_labels
        for record in recovered.records
    )


def test_adaptive_false_never_relocates_even_with_existing_fingerprint(
    tmp_path: Path,
) -> None:
    locator = AdaptiveCardLocator(tmp_path / "adaptive.db")
    GenericListAdapter(locator=locator).collect(
        _config(),
        _Fetcher(_page("adaptive-v1.html")),
    )

    result = GenericListAdapter(locator=locator).collect(
        _config(adaptive=False),
        _Fetcher(_page("adaptive-v2.html")),
    )

    assert result.status is CollectionStatus.ERROR
    assert result.stop_reason == "LAYOUT_CHANGED"
    assert result.warnings == ()


def test_configured_cards_without_valid_record_are_not_remembered(
    tmp_path: Path,
) -> None:
    locator = AdaptiveCardLocator(tmp_path / "adaptive.db")
    malformed = Adaptor(
        '<article class="job-card"><h2 class="title-v1">Sem link</h2></article>',
        url=URL,
    )

    result = GenericListAdapter(locator=locator).collect(
        _config(),
        _Fetcher(malformed),
    )
    selection = select_cards(
        _page("adaptive-v2.html"),
        source_code="example",
        selector=SELECTOR,
        locator=locator,
    )

    assert result.status is CollectionStatus.ERROR
    assert result.stop_reason == "PARSE_ZERO_RECORDS"
    assert selection.method == "NONE"
    assert locator.db_path.exists() is False


def test_remember_uses_first_card_that_produced_a_valid_record(
    tmp_path: Path,
) -> None:
    database = tmp_path / "adaptive.db"
    locator = AdaptiveCardLocator(database)
    config = SourceConfig(
        code="example",
        kind=SourceKind.GENERIC,
        start_url=URL,
        enabled=True,
        max_pages=1,
        min_interval_seconds=1,
        requires_auth=False,
        selectors={
            "card": ".jobs-list > aside, .jobs-list > article",
            "title": ".job-title::all-text",
            "url": ".job-link::attr(href)",
        },
    )
    original = Adaptor(
        """
        <main>
          <div class="jobs-list">
            <aside class="editorial-card">
              <h2 class="blog-title"><a class="blog-link" href="/blog/carreira">Guia de carreira</a></h2>
            </aside>
            <article class="job-card">
              <h2 class="job-title"><a class="job-link" href="/jobs/valid-1">Java Junior</a></h2>
            </article>
          </div>
        </main>
        """,
        url=URL,
    )
    changed = Adaptor(
        """
        <main>
          <div class="jobs-list">
            <section class="job-entry"><h3><a href="/jobs/valid-2">Estágio Java</a></h3></section>
          </div>
          <aside class="editorial-list">
            <section class="job-entry"><h3><a href="/blog/carreira">Guia de carreira</a></h3></section>
          </aside>
        </main>
        """,
        url=URL,
    )
    adapter = GenericListAdapter(locator=locator)

    learned = adapter.parse_page(original, config)
    with closing(sqlite3.connect(database)) as connection:
        raw_fingerprint = connection.execute(
            "SELECT fingerprint FROM adaptive_fingerprints"
        ).fetchone()[0]
    recovered = adapter.parse_page(changed, config)

    assert [record.title for record in learned.records] == ["Java Junior"]
    assert json.loads(raw_fingerprint)["element"]["tag"] == "article"
    assert recovered.card_method == "ADAPTIVE"
    assert [record.title for record in recovered.records] == ["Estágio Java"]
    assert [record.canonical_url for record in recovered.records] == [
        "https://jobs.example.com/jobs/valid-2"
    ]


def test_relocated_card_with_non_http_link_is_not_promoted(
    tmp_path: Path,
) -> None:
    locator = AdaptiveCardLocator(tmp_path / "adaptive.db")
    adapter = GenericListAdapter(locator=locator)
    adapter.parse_page(_page("adaptive-v1.html"), _config())
    changed = Adaptor(
        '<main><div class="jobs-list"><article class="job-entry"><h2 class="title-v1"><a href="javascript:alert(1)">Java suspeita</a></h2></article></div></main>',
        url=URL,
    )

    parsed = adapter.parse_page(changed, _config())

    assert parsed.card_method == "ADAPTIVE"
    assert parsed.cards_observed == 1
    assert parsed.records == ()


@pytest.mark.parametrize(
    "malicious_url",
    (
        "https://attacker.example/jobs/999",
        "http://jobs.example.com/jobs/999",
    ),
)
def test_relocated_card_outside_source_origin_is_not_promoted(
    tmp_path: Path,
    malicious_url: str,
) -> None:
    locator = AdaptiveCardLocator(tmp_path / "adaptive.db")
    adapter = GenericListAdapter(locator=locator)
    adapter.parse_page(_page("adaptive-v1.html"), _config())
    changed = Adaptor(
        f'<main><div class="jobs-list"><article class="job-entry"><h2 class="title-v1"><a href="{malicious_url}">Java suspeita</a></h2></article></div></main>',
        url=URL,
    )

    parsed = adapter.parse_page(changed, _config())

    assert parsed.card_method == "ADAPTIVE"
    assert parsed.cards_observed == 1
    assert parsed.records == ()


@pytest.mark.parametrize(
    ("code", "selector", "valid_html", "expired_html"),
    (
        (
            "programathor",
            ".cell-list:not(.opacity-60p) > a[href^='/jobs/']",
            '<div class="cell-list"><a href="/jobs/1"><div class="cell-list-content"><h3>Java Junior</h3></div></a></div>',
            '<div class="cell-list opacity-60p"><article><h3>Java encerrada</h3><a href="/jobs/2">Detalhes</a></article></div>',
        ),
        (
            "companhia-de-estagios",
            ".vagas__card:not([class~='--expired'])",
            '<div class="vagas"><article class="vagas__card"><h2>Estágio Java</h2><a href="/vagas/1">Detalhes</a></article></div>',
            '<div class="vagas"><section class="opportunity-card --expired"><h2>Estágio encerrado</h2><a href="/vagas/2">Detalhes</a></section></div>',
        ),
    ),
)
def test_adaptive_fallback_does_not_reintroduce_expired_cards(
    tmp_path: Path,
    code: str,
    selector: str,
    valid_html: str,
    expired_html: str,
) -> None:
    locator = AdaptiveCardLocator(tmp_path / f"{code}.db")
    config = SourceConfig(
        code=code,
        kind=SourceKind.GENERIC,
        start_url=URL,
        enabled=True,
        max_pages=1,
        min_interval_seconds=1,
        requires_auth=False,
        selectors={"card": selector, "title": "h2, h3", "url": "a::attr(href)"},
    )
    adapter = GenericListAdapter(locator=locator)
    adapter.parse_page(Adaptor(valid_html, url=URL), config)

    parsed = adapter.parse_page(Adaptor(expired_html, url=URL), config)

    assert parsed.cards_observed == 0
    assert parsed.records == ()


def test_dynamic_adapter_uses_adaptive_cards_and_validated_field_fallbacks(
    tmp_path: Path,
) -> None:
    locator = AdaptiveCardLocator(tmp_path / "dynamic.db")
    config = SourceConfig(
        code="eureca",
        kind=SourceKind.DYNAMIC,
        start_url=URL,
        enabled=True,
        max_pages=1,
        min_interval_seconds=1,
        requires_auth=False,
        selectors={
            "card": SELECTOR,
            "title": ".title-v1::all-text",
            "url": ".title-v1 a::attr(href)",
            "next": "a.next::attr(href)",
        },
    )
    adapter = DynamicAdapter(locator=locator)

    adapter.collect(config, _Fetcher(_page("adaptive-v1.html")))
    recovered = adapter.collect(config, _Fetcher(_page("adaptive-v2.html")))

    assert recovered.status is CollectionStatus.PARTIAL
    assert recovered.stop_reason == "SELECTOR_RELOCATED"
    assert [record.title for record in recovered.records] == [
        "Java Júnior",
        "Estágio Backend",
    ]


def test_dynamic_adaptive_fallback_reuses_infojobs_location_cleaning(
    tmp_path: Path,
) -> None:
    locator = AdaptiveCardLocator(tmp_path / "infojobs.db")
    config = SourceConfig(
        code="infojobs",
        kind=SourceKind.DYNAMIC,
        start_url=URL,
        enabled=True,
        max_pages=1,
        min_interval_seconds=1,
        requires_auth=False,
        selectors={
            "card": "article.job-card",
            "title": ".old-title::all-text",
            "url": ".old-title::attr(href)",
            "location": ".location::all-text",
        },
    )
    original = Adaptor(
        '<div class="jobs-list"><article class="job-card"><a class="old-title" href="/vaga-de-java__1.aspx">Java Junior</a><span class="location">São Paulo - SP, 0 Km de você.</span></article></div>',
        url=URL,
    )
    changed = Adaptor(
        '<div class="jobs-list"><section class="job-entry"><h3>Java Junior</h3><a href="/vaga-de-java__2.aspx">Detalhes</a><span class="location">São Paulo - SP, 0 Km de você.</span></section></div>',
        url=URL,
    )
    adapter = DynamicAdapter(locator=locator)
    adapter.parse_page(original, config)

    parsed = adapter.parse_page(changed, config)

    assert parsed.card_method == "ADAPTIVE"
    assert parsed.records[0].location == "São Paulo - SP"


def test_indeed_adapter_recovers_changed_card_container(
    tmp_path: Path,
) -> None:
    locator = AdaptiveCardLocator(tmp_path / "indeed.db")
    config = SourceConfig(
        code="indeed",
        kind=SourceKind.INDEED,
        start_url=URL,
        enabled=True,
        max_pages=1,
        min_interval_seconds=1,
        requires_auth=False,
    )
    original = Adaptor(
        '<main class="results"><div class="job_seen_beacon"><h3><a data-jk="indeed-1" href="/rc/clk?jk=indeed-1"><span title="Java Junior">Java Junior</span></a></h3></div></main>',
        url=URL,
    )
    changed = Adaptor(
        '<main class="results"><section class="job-result"><h3><a data-jk="indeed-2" href="/rc/clk?jk=indeed-2"><span title="Estágio Java">Estágio Java</span></a></h3></section></main>',
        url=URL,
    )
    adapter = IndeedAdapter(locator=locator)
    adapter.parse_page(original, config)

    parsed = adapter.parse_page(changed, config)

    assert parsed.card_method == "ADAPTIVE"
    assert parsed.records[0].source_job_id == "indeed-2"
    assert parsed.records[0].canonical_url == "https://jobs.example.com/viewjob?jk=indeed-2"


def test_gupy_checks_current_configured_layout_before_legacy_fingerprint(
    tmp_path: Path,
) -> None:
    locator = AdaptiveCardLocator(tmp_path / "gupy.db")
    config = SourceConfig(
        code="gupy",
        kind=SourceKind.GUPY,
        start_url=URL,
        enabled=True,
        max_pages=1,
        min_interval_seconds=1,
        requires_auth=False,
    )
    legacy = Adaptor(
        '<main class="results"><article data-testid="job-card" data-job-id="legacy-1"><h2>Java Junior</h2><a href="/job/legacy-1">Detalhes</a></article></main>',
        url=URL,
    )
    current = Adaptor(
        '<main class="results"><ul id="job-listing-results"><li><a href="/job/current-1"><p>Acme</p><h3>Estágio Java</h3></a></li></ul></main>',
        url=URL,
    )
    adapter = GupyAdapter(locator=locator)
    adapter.parse_page(legacy, config)

    parsed = adapter.parse_page(current, config)

    assert parsed.card_method == "CONFIGURED"
    assert parsed.records[0].source_job_id == "current-1"


def test_gupy_tries_current_layout_when_legacy_cards_produce_no_records() -> None:
    config = SourceConfig(
        code="gupy",
        kind=SourceKind.GUPY,
        start_url=URL,
        enabled=True,
        max_pages=1,
        min_interval_seconds=1,
        requires_auth=False,
    )
    page = Adaptor(
        """
        <main class="results">
          <article data-testid="job-card" data-job-id="stale">
            <h2>Componente legado sem link</h2>
          </article>
          <ul id="job-listing-results">
            <li><a href="/job/current-1"><p>Acme</p><h2>Estágio Java</h2></a></li>
          </ul>
        </main>
        """,
        url=URL,
    )

    parsed = GupyAdapter().parse_page(page, config)

    assert parsed.card_method == "CONFIGURED"
    assert parsed.cards_observed == 1
    assert [record.title for record in parsed.records] == ["Estágio Java"]
    assert [record.source_job_id for record in parsed.records] == ["current-1"]


def test_gupy_keeps_separate_legacy_and_current_fingerprints(
    tmp_path: Path,
) -> None:
    database = tmp_path / "gupy.db"
    locator = AdaptiveCardLocator(database)
    config = SourceConfig(
        code="gupy",
        kind=SourceKind.GUPY,
        start_url=URL,
        enabled=True,
        max_pages=1,
        min_interval_seconds=1,
        requires_auth=False,
    )
    adapter = GupyAdapter(locator=locator)
    adapter.parse_page(
        Adaptor(
            '<main class="results"><article data-testid="job-card" data-job-id="legacy-1"><h2>Java Junior</h2><a href="/job/legacy-1">Detalhes</a></article></main>',
            url=URL,
        ),
        config,
    )
    adapter.parse_page(
        Adaptor(
            '<main class="results"><ul id="job-listing-results"><li><a href="/job/current-1"><p>Acme</p><h3>Estágio Java</h3></a></li></ul></main>',
            url=URL,
        ),
        config,
    )

    with sqlite3.connect(database) as connection:
        selectors = {
            row[0]
            for row in connection.execute(
                "SELECT selector FROM adaptive_fingerprints WHERE source_code = 'gupy'"
            )
        }

    assert selectors == {"[data-testid='job-card']", "#job-listing-results li"}


def test_gupy_recovers_legacy_layout_with_legacy_field_contract(
    tmp_path: Path,
) -> None:
    locator = AdaptiveCardLocator(tmp_path / "gupy-legacy.db")
    config = SourceConfig(
        code="gupy",
        kind=SourceKind.GUPY,
        start_url=URL,
        enabled=True,
        max_pages=1,
        min_interval_seconds=1,
        requires_auth=False,
    )
    adapter = GupyAdapter(locator=locator)
    adapter.parse_page(
        Adaptor(
            '<main class="results"><article data-testid="job-card" data-job-id="legacy-1"><h2>Java Junior</h2><a href="/job/legacy-1">Detalhes</a></article></main>',
            url=URL,
        ),
        config,
    )

    parsed = adapter.parse_page(
        Adaptor(
            '<main class="results"><section class="legacy-entry"><h2>Estágio Backend</h2><a href="/job/legacy-2">Detalhes</a></section></main>',
            url=URL,
        ),
        config,
    )

    assert parsed.card_method == "ADAPTIVE"
    assert parsed.records[0].title == "Estágio Backend"
    assert parsed.records[0].source_job_id == "legacy-2"


def test_gupy_recovers_current_layout_with_current_field_contract(
    tmp_path: Path,
) -> None:
    locator = AdaptiveCardLocator(tmp_path / "gupy-current.db")
    config = SourceConfig(
        code="gupy",
        kind=SourceKind.GUPY,
        start_url=URL,
        enabled=True,
        max_pages=1,
        min_interval_seconds=1,
        requires_auth=False,
    )
    adapter = GupyAdapter(locator=locator)
    adapter.parse_page(
        Adaptor(
            '<main class="results"><ul id="job-listing-results"><li><a href="/job/current-1"><p>Acme</p><h3>Java Junior</h3></a></li></ul></main>',
            url=URL,
        ),
        config,
    )

    parsed = adapter.parse_page(
        Adaptor(
            '<main class="results"><ul class="new-results"><li><a href="/job/current-2"><p>Beta</p><h3>Estágio Java</h3></a></li></ul></main>',
            url=URL,
        ),
        config,
    )

    assert parsed.card_method == "ADAPTIVE"
    assert parsed.records[0].title == "Estágio Java"
    assert parsed.records[0].company == "Beta"
    assert parsed.records[0].source_job_id == "current-2"


def test_gupy_adaptive_allows_declared_tenant_host_suffix(
    tmp_path: Path,
) -> None:
    locator = AdaptiveCardLocator(tmp_path / "gupy-current.db")
    config = SourceConfig(
        code="gupy",
        kind=SourceKind.GUPY,
        start_url="https://portal.gupy.io/job-search/term%3Djava",
        enabled=True,
        max_pages=1,
        min_interval_seconds=1,
        requires_auth=False,
    )
    adapter = GupyAdapter(locator=locator)
    adapter.parse_page(
        Adaptor(
            '<main><ul id="job-listing-results"><li><a href="https://acme.gupy.io/job/current-1"><p>Acme</p><h3>Java Junior</h3></a></li></ul></main>',
            url=config.start_url,
        ),
        config,
    )

    parsed = adapter.parse_page(
        Adaptor(
            '<main><ul class="new-results"><li><a href="https://beta.gupy.io/job/current-2"><p>Beta</p><h3>Estágio Java</h3></a></li></ul></main>',
            url=config.start_url,
        ),
        config,
    )

    assert parsed.card_method == "ADAPTIVE"
    assert [record.canonical_url for record in parsed.records] == [
        "https://beta.gupy.io/job/current-2"
    ]
