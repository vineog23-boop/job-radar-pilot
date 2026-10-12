"""Qualidade da coleta (10/10/2026): data, empresa, prazo e modalidade que os portais
expõem mas o Radar não aproveitava, e prioridade do enriquecimento para vagas sem data."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from job_radar.config import ConfigError, load_sources
from job_radar.enrich import enrich_records, extract_detail_metadata
from job_radar.fetching import FetchResult
from job_radar.models import CollectionStatus, SourceConfig, SourceKind, VacancyRecord, WorkplaceModel
from job_radar.sources.base import apply_source_defaults


def _source(code: str = "portal", **extra) -> SourceConfig:
    return SourceConfig(
        code=code, kind=SourceKind.GENERIC, start_url="https://x.com.br/v",
        enabled=True, max_pages=1, min_interval_seconds=1, requires_auth=False, **extra,
    )


def _record(code: str = "portal", n: int = 1, **extra) -> VacancyRecord:
    base = VacancyRecord(
        source=code, source_job_id=str(n), canonical_url=f"https://x.com.br/{code}/{n}",
        title="duvidosa", company=None, observed_at="2026-10-10T00:00:00+00:00",
    )
    return replace(base, **extra)


def _classify(record: VacancyRecord) -> VacancyRecord:
    return replace(record, match_labels=("FIT:CONDITIONAL", "TECH_MATCH:java"))


class _Fetcher:
    def __init__(self, html: str = "") -> None:
        self.urls: list[str] = []
        self.html = html or "<html><body><p>" + "Java Spring Boot junior. " * 10 + "</p></body></html>"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def fetch(self, url, source):
        self.urls.append(url)
        return FetchResult(
            status=CollectionStatus.SUCCESS,
            response=SimpleNamespace(body=self.html.encode(), status=200, url=url),
        )


# --- Remotar: dados da vaga no __NEXT_DATA__ (jobData) ----------------------------


REMOTAR = (
    '<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"jobData":'
    '{"title":"Junior Java Developer","createdAt":"2026-10-02T11:34:22.023-03:00",'
    '"expiresAt":%s,"expired":false,"company":{"name":"BairesDev"}}}}}</script>'
)


def test_remotar_next_data_fills_published_and_company() -> None:
    meta = extract_detail_metadata(REMOTAR % "null")
    assert meta.published_at is not None and meta.published_at.startswith("2026-10-02T14:34:22")
    assert meta.company == "BairesDev"
    assert meta.application_deadline is None


def test_remotar_next_data_reads_expiry() -> None:
    meta = extract_detail_metadata(REMOTAR % '"2026-10-30"')
    assert meta.application_deadline is not None and meta.application_deadline.startswith("2026-10-31")


# --- Modalidade a partir da página de detalhe --------------------------------------


def test_gupy_workplace_type_is_read_from_detail() -> None:
    html = ('<script id="__NEXT_DATA__">{"props":{"pageProps":{"job":{"publishedAt":"2026-10-01T00:00:00Z",'
            '"expiresAt":null,"workplaceType":"hybrid"}}}}</script>')
    assert extract_detail_metadata(html).workplace is WorkplaceModel.HYBRID


def test_json_ld_telecommute_means_remote() -> None:
    html = ('<script type="application/ld+json">{"@type":"JobPosting","datePosted":"2026-10-01",'
            '"jobLocationType":"TELECOMMUTE"}</script>')
    assert extract_detail_metadata(html).workplace is WorkplaceModel.REMOTE


def test_unknown_workplace_is_filled_by_enrichment_but_known_is_kept() -> None:
    html = ('<script type="application/ld+json">{"@type":"JobPosting","datePosted":"2026-10-01",'
            '"jobLocationType":"TELECOMMUTE"}</script><p>' + "Java junior. " * 20 + "</p>")
    unknown = _record(n=1)
    known = _record(n=2, workplace_model=WorkplaceModel.ONSITE)
    result, _ = enrich_records([unknown, known], _classify, [_source()], limit=5,
                               fetcher_factory=lambda: _Fetcher(html))
    assert result[0].workplace_model is WorkplaceModel.REMOTE
    assert result[1].workplace_model is WorkplaceModel.ONSITE


# --- Prioridade do enriquecimento ------------------------------------------------


def test_records_without_date_are_enriched_before_records_with_date() -> None:
    fetcher = _Fetcher()
    dated = _record(n=1, published_at="2026-10-09T00:00:00+00:00")
    undated = _record(n=2)
    enrich_records([dated, undated], _classify, [_source()], limit=1, fetcher_factory=lambda: fetcher)
    assert fetcher.urls == [undated.canonical_url]


def test_enrichment_budget_is_shared_between_sources() -> None:
    fetcher = _Fetcher()
    records = [_record("grande", n) for n in range(1, 6)] + [_record("pequeno", 1)]
    enrich_records(records, _classify, [_source("grande"), _source("pequeno")], limit=2,
                   fetcher_factory=lambda: fetcher)
    assert sorted(url.split("/")[3] for url in fetcher.urls) == ["grande", "pequeno"]


# --- Padrões por fonte: modalidade e empresa pela URL ------------------------------


def test_default_workplace_applies_only_when_unknown() -> None:
    source = _source(default_workplace=WorkplaceModel.REMOTE)
    assert apply_source_defaults(_record(), source).workplace_model is WorkplaceModel.REMOTE
    onsite = _record(workplace_model=WorkplaceModel.HYBRID)
    assert apply_source_defaults(onsite, source).workplace_model is WorkplaceModel.HYBRID


def test_company_from_url_slug() -> None:
    source = _source(selectors={"company_from_url": r"/pt/([^/]+)/jobs/"})
    record = _record(canonical_url="https://www.geekhunter.com/pt/nava-technology-for-business-1/jobs/dev-java-1")
    assert apply_source_defaults(record, source).company == "Nava Technology For Business"
    named = replace(record, company="Nava")
    assert apply_source_defaults(named, source).company == "Nava"


def _yaml(tmp_path: Path, extra: str) -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text(
        "sources:\n  - code: portal\n    kind: rss\n    start_url: https://x.com.br/feed\n"
        "    enabled: true\n    max_pages: 1\n    min_interval_seconds: 1\n    requires_auth: false\n"
        + extra,
        encoding="utf-8",
    )
    return path


def test_config_reads_default_workplace(tmp_path: Path) -> None:
    (source,) = load_sources(_yaml(tmp_path, "    default_workplace: REMOTE\n"))
    assert source.default_workplace is WorkplaceModel.REMOTE


def test_config_rejects_invalid_default_workplace(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="default_workplace"):
        load_sources(_yaml(tmp_path, "    default_workplace: LUA\n"))
