"""Testes da fonte LinkedIn (guest API anônima, kind: linkedin)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scrapling.parser import Adaptor

from job_radar.config import load_sources
from job_radar.fetching import BlockReason, FetchPolicy, FetchResult
from job_radar.models import CollectionStatus, SourceConfig, SourceKind
from job_radar.sources import adapter_for
from job_radar.sources.linkedin import (
    LinkedinAdapter,
    job_url_from_path,
    normalize_job_url,
)

PROJECT_CONFIG = (
    Path(__file__).resolve().parents[1] / "config" / "sources.yaml"
)

_PAGE_1 = """
<ul class="jobs-search__results-list">
  <li>
    <div class="base-card">
      <h3 class="base-search-card__title">Desenvolvedor Java Júnior</h3>
      <h4 class="base-search-card__subtitle"><a>Acme Tecnologia</a></h4>
      <span class="job-search-card__location">São Paulo, SP</span>
      <time datetime="2026-10-09">há 2 dias</time>
      <a class="base-card__full-link"
         href="https://www.linkedin.com/jobs/view/100001?trackingId=abc&refId=xyz">
        &nbsp;</a>
    </div>
  </li>
  <li>
    <div class="base-card">
      <h3 class="base-search-card__title">Estágio Full Stack</h3>
      <h4 class="base-search-card__subtitle"><a>StartupSC</a></h4>
      <span class="job-search-card__location">Florianópolis, SC</span>
      <time datetime="2026-10-10">há 1 dia</time>
      <a class="base-card__full-link"
         href="https://br.linkedin.com/jobs/view/100002?trackingId=def">
        &nbsp;</a>
    </div>
  </li>
</ul>
"""

_PAGE_EMPTY = "<ul class=\"jobs-search__results-list\"></ul>"


def _html_page(html: str, url: str) -> SimpleNamespace:
    adaptor = Adaptor(html, url=url)
    return SimpleNamespace(
        status=200,
        text=html,
        url=url,
        css=adaptor.css,
        urljoin=adaptor.urljoin,
    )

def _source(max_pages: int = 2) -> SourceConfig:
    return SourceConfig(
        code="linkedin",
        kind=SourceKind.LINKEDIN,
        start_url=(
            "https://www.linkedin.com/jobs-guest/jobs/api/"
            "seeMoreJobPostings/search"
        ),
        enabled=True,
        max_pages=max_pages,
        min_interval_seconds=0,
        requires_auth=False,
        adaptive=False,
        fetch_details=False,
        queries=(),
        api={
            "locations": ("Brasil", "São Paulo, São Paulo, Brasil"),
            "queries": ("java",),
        },
    )


class _FakeFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def fetch(self, url: str, source: SourceConfig) -> FetchResult:
        self.calls.append(url)
        html = self.pages.get(url)
        if html is None:
            return FetchResult(
                CollectionStatus.BLOCKED,
                block_reason=BlockReason.ACCESS_DENIED,
                error="http:403",
            )
        return FetchResult(
            CollectionStatus.SUCCESS,
            response=_html_page(html, url),
            attempts=1,
        )


class TestNormalizeUrl:
    def test_remove_query_de_tracking(self) -> None:
        url = normalize_job_url(
            "https://www.linkedin.com/jobs/view/100001?trackingId=abc&refId=xyz"
        )
        assert url == "https://www.linkedin.com/jobs/view/100001"

    def test_host_br_normalizado(self) -> None:
        url = normalize_job_url("https://br.linkedin.com/jobs/view/100002?x=1")
        assert url == "https://www.linkedin.com/jobs/view/100002"

    def test_job_id_numerico(self) -> None:
        assert job_url_from_path("/jobs/view/100001") == "100001"
        assert job_url_from_path("/jobs/view/dev-java-100001") == "100001"
        assert job_url_from_path("/jobs/view/sem-id") is None


class TestParsePage:
    def test_extrai_campos_dos_cartoes(self) -> None:
        adapter = LinkedinAdapter()
        page = _html_page(_PAGE_1, "https://www.linkedin.com/jobs-guest/x?start=0")
        parsed = adapter.parse_page(page, _source())
        assert parsed.cards_observed == 2
        first, second = parsed.records
        assert first.title == "Desenvolvedor Java Júnior"
        assert first.company == "Acme Tecnologia"
        assert first.location == "São Paulo, SP"
        assert first.source_job_id == "100001"
        assert first.published_at is not None
        assert second.source_job_id == "100002"
        assert all("EXTRACTION:GUEST_API" in r.match_labels for r in parsed.records)

    def test_pagina_sem_cartoes(self) -> None:
        adapter = LinkedinAdapter()
        page = _html_page(_PAGE_EMPTY, "https://www.linkedin.com/jobs-guest/x?start=25")
        parsed = adapter.parse_page(page, _source())
        assert parsed.records == ()


class TestCollect:
    def test_pagina_por_offset_e_para_sem_cartoes(self) -> None:
        from urllib.parse import urlencode

        def _url(location: str, start: int) -> str:
            query = urlencode(
                {"keywords": "java", "location": location, "start": start}
            )
            return (
                "https://www.linkedin.com/jobs-guest/jobs/api/"
                f"seeMoreJobPostings/search?{query}"
            )

        pages = {
            _url("Brasil", 0): _PAGE_1,
            _url("Brasil", 25): _PAGE_EMPTY,
            _url("São Paulo, São Paulo, Brasil", 0): _PAGE_1,
            _url("São Paulo, São Paulo, Brasil", 25): _PAGE_EMPTY,
        }
        fetcher = _FakeFetcher(pages)
        result = LinkedinAdapter().collect(_source(max_pages=3), fetcher)
        assert result.status is CollectionStatus.SUCCESS
        # Duas páginas com os mesmos 2 cartões: dedupe por URL.
        assert len(result.records) == 2
        assert result.cards_observed == 4
        assert len(fetcher.calls) == 4

    def test_respeita_max_pages(self) -> None:
        base = (
            "https://www.linkedin.com/jobs-guest/jobs/api/"
            "seeMoreJobPostings/search?keywords=java&location=Brasil&start={start}"
        )
        pages = {
            base.format(start=0): _PAGE_1,
            base.format(start=25): _PAGE_1,
        }
        fetcher = _FakeFetcher(pages)
        result = LinkedinAdapter().collect(_source(max_pages=1), fetcher)
        assert len(fetcher.calls) == 2  # Brasil + São Paulo, 1 página cada
        assert len(result.records) == 2

    def test_bloqueio_sem_registros_retorna_bloqueado(self) -> None:
        fetcher = _FakeFetcher({})
        result = LinkedinAdapter().collect(_source(), fetcher)
        assert result.status is CollectionStatus.BLOCKED
        assert result.stop_reason == BlockReason.ACCESS_DENIED.value


class TestFetchPolicyLinkedin:
    def _policy(self, body: str) -> FetchPolicy:
        def http_get(url: str):  # type: ignore[no-untyped-def]
            return SimpleNamespace(status=200, text=body, headers={}, url=url)

        # robots_allowed=False prova que o bypass do LinkedIn ignora robots.
        return FetchPolicy(
            http_get=http_get,
            robots_allowed=lambda url: False,
            max_attempts=1,
        )

    def test_fonte_dedicada_passa_apesar_de_robots(self) -> None:
        policy = self._policy(_PAGE_1)
        result = policy.fetch(
            "https://www.linkedin.com/jobs-guest/jobs/api/"
            "seeMoreJobPostings/search?keywords=java&location=Brasil&start=0",
            _source(),
        )
        assert result.status is CollectionStatus.SUCCESS
        assert result.response is not None

    def test_outro_kind_continua_bloqueado(self) -> None:
        policy = self._policy(_PAGE_1)
        outra = SourceConfig(
            code="example",
            kind=SourceKind.GENERIC,
            start_url="https://www.linkedin.com/jobs/search",
            enabled=True,
            max_pages=1,
            min_interval_seconds=0,
            requires_auth=False,
            selectors={},
        )
        result = policy.fetch("https://www.linkedin.com/jobs/search", outra)
        assert result.status is CollectionStatus.BLOCKED
        assert result.block_reason is BlockReason.ROBOTS_DENIED


class TestConfig:
    def test_fonte_linkedin_no_sources_yaml(self) -> None:
        from pathlib import Path

        sources = load_sources(Path(PROJECT_CONFIG))
        linkedin = [s for s in sources if s.code == "linkedin"]
        assert len(linkedin) == 1
        config = linkedin[0]
        assert config.kind is SourceKind.LINKEDIN
        assert config.enabled
        assert config.fetch_details is False
        assert config.min_interval_seconds >= 4
        assert config.queries == ()
        assert config.api["queries"]
        assert "Brasil" in config.api["locations"]
        assert isinstance(adapter_for(config), LinkedinAdapter)

    def test_api_invalida_rejeitada(self, tmp_path) -> None:
        import yaml
        from job_radar.config import ConfigError

        raw = {
            "sources": [
                {
                    "code": "linkedin",
                    "kind": "linkedin",
                    "start_url": "https://www.linkedin.com/jobs-guest/x",
                    "enabled": True,
                    "max_pages": 1,
                    "min_interval_seconds": 1,
                    "requires_auth": False,
                    "api": {"locations": ["Brasil"], "extra": 1},
                }
            ]
        }
        path = tmp_path / "sources.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        with pytest.raises(ConfigError):
            load_sources(path)
