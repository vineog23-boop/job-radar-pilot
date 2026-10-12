from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from pathlib import Path

from job_radar.config import load_sources
from job_radar.fetching import BlockReason, FetchResult
from job_radar.geo import state_names_from_scopes, uf_from_scope
from job_radar.models import CollectionStatus, SourceConfig, SourceKind, WorkplaceModel
from job_radar.sources.json_api import (
    JsonApiAdapter,
    clean_text,
    get_path,
    page_url,
    record_from_item,
    to_iso_datetime,
)

FIELDS = {
    "id": "id",
    "title": "name",
    "company": "company.name",
    "city": "city",
    "state": "state",
    "country": "country",
    "published": "publishedDate",
    "description": "description",
    "workplace": "workplaceType",
    "url": "jobUrl",
    "skills": "skills",
}


def _source(page_size: int = 2, max_pages: int = 3, mode: str = "offset") -> SourceConfig:
    return SourceConfig(
        code="api-x",
        kind=SourceKind.JSON,
        start_url="https://api.example.com/jobs?limit=2",
        enabled=True,
        min_interval_seconds=0,
        requires_auth=False,
        max_pages=max_pages,
        api={
            "items": "data",
            "page_param": "offset",
            "page_mode": mode,
            "page_size": page_size,
            "size_param": "limit",
            "strip_levels": False,
            "fields": FIELDS,
        },
    )


def _item(number: int, **extra: object) -> dict[str, object]:
    item: dict[str, object] = {
        "id": number,
        "name": f"Dev Java {number}",
        "company": {"name": "Acme"},
        "city": "Curitiba",
        "state": "Paraná",
        "country": "Brasil",
        "publishedDate": "2026-09-28T10:00:00.000Z",
        "description": "<p>Vaga <b>Java</b> &amp; Spring</p>",
        "workplaceType": "hybrid",
        "jobUrl": f"https://acme.example.com/vaga/{number}",
        "skills": [{"name": "Java"}, {"name": "Spring"}, "Java"],
    }
    item.update(extra)
    return item


@dataclass
class _Response:
    body: bytes
    status: int = 200


class _Fetcher:
    def __init__(self, pages: list[object]) -> None:
        self.pages = pages
        self.urls: list[str] = []

    def fetch(self, url: str, source: SourceConfig) -> FetchResult:
        self.urls.append(url)
        page = self.pages[len(self.urls) - 1]
        if isinstance(page, FetchResult):
            return page
        return FetchResult(
            CollectionStatus.SUCCESS,
            response=_Response(json.dumps(page).encode()),  # type: ignore[arg-type]
            attempts=1,
        )


def test_helpers_read_nested_values_and_normalize_dates_and_text() -> None:
    assert get_path({"a": {"b": 3}}, "a.b") == 3
    assert get_path({"a": 1}, "a.b") is None
    assert clean_text("<p>Ol&aacute;  <b>mundo</b></p>") == "Olá mundo"
    assert clean_text("   ") is None
    assert to_iso_datetime("2026-09-28T10:00:00.000Z") == "2026-09-28T10:00:00+00:00"
    assert to_iso_datetime("09/28/2026 09:16:18") == "2026-09-28T09:16:18+00:00"
    assert to_iso_datetime("lixo") is None


def test_record_maps_fields_workplace_and_skills() -> None:
    record = record_from_item(_item(7), _source(), "2026-09-29T00:00:00+00:00")
    assert record is not None
    assert record.title == "Dev Java 7"
    assert record.company == "Acme"
    assert record.workplace_model is WorkplaceModel.HYBRID
    assert record.location == "Curitiba, Paraná"
    assert record.description_summary == "Vaga Java & Spring"
    assert record.technologies == ("Java", "Spring")
    assert record.published_at == "2026-09-28T10:00:00+00:00"


def test_record_rejects_items_without_title_or_https_url() -> None:
    assert record_from_item(_item(1, name=""), _source(), "x") is None
    assert record_from_item(_item(1, jobUrl="http://insecure.example"), _source(), "x") is None


def test_page_url_supports_offset_and_page_modes() -> None:
    assert page_url(_source(), 0).endswith("limit=2&offset=0")
    assert page_url(_source(), 2).endswith("limit=2&offset=4")
    assert "offset=1" in page_url(_source(mode="page0"), 1)
    assert "offset=2" in page_url(_source(mode="page1"), 1)


def test_adapter_paginates_until_short_page() -> None:
    fetcher = _Fetcher([{"data": [_item(1), _item(2)]}, {"data": [_item(3)]}])
    result = JsonApiAdapter().collect(_source(), fetcher)  # type: ignore[arg-type]
    assert result.status is CollectionStatus.SUCCESS
    assert [r.source_job_id for r in result.records] == ["1", "2", "3"]
    assert result.pages_observed == 2


def test_adapter_stops_when_server_repeats_the_same_page() -> None:
    page = {"data": [_item(1), _item(2)]}
    result = JsonApiAdapter().collect(_source(), _Fetcher([page, page]))  # type: ignore[arg-type]
    assert result.status is CollectionStatus.PARTIAL
    assert result.stop_reason == "PAGINATION_LOOP"
    assert len(result.records) == 2


def test_adapter_reports_page_limit_layout_change_and_rate_limit() -> None:
    pages = [{"data": [_item(1), _item(2)]}, {"data": [_item(3), _item(4)]}]
    limited = JsonApiAdapter().collect(_source(max_pages=2), _Fetcher(pages))  # type: ignore[arg-type]
    assert limited.status is CollectionStatus.PARTIAL and limited.stop_reason == "PAGE_LIMIT"

    changed = JsonApiAdapter().collect(_source(), _Fetcher([{"other": []}]))  # type: ignore[arg-type]
    assert changed.status is CollectionStatus.ERROR and changed.stop_reason == "LAYOUT_CHANGED"

    blocked = FetchResult(
        CollectionStatus.BLOCKED, block_reason=BlockReason.RATE_LIMITED, attempts=1
    )
    result = JsonApiAdapter().collect(_source(), _Fetcher([blocked]))  # type: ignore[arg-type]
    assert result.status is CollectionStatus.BLOCKED
    assert result.stop_reason == BlockReason.RATE_LIMITED.value


def test_adapter_empty_result() -> None:
    result = JsonApiAdapter().collect(_source(), _Fetcher([{"data": []}]))  # type: ignore[arg-type]
    assert result.status is CollectionStatus.EMPTY


@pytest.mark.parametrize(
    ("scope", "uf"),
    [
        ("sao-carlos-sp", "SP"),
        ("SC", "SC"),
        ("santa-catarina", "SC"),
        ("curitiba-parana", "PR"),
        ("brasil", None),
        ("", None),
    ],
)
def test_uf_from_scope(scope: str, uf: str | None) -> None:
    assert uf_from_scope(scope) == uf


def test_state_names_from_scopes_dedupes_and_limits() -> None:
    assert state_names_from_scopes(["sao-paulo-sp", "campinas-sp", "rj", "brasil"]) == [
        "São Paulo",
        "Rio de Janeiro",
    ]
    assert len(state_names_from_scopes(["ac", "al", "ap", "am", "ba", "ce"], limit=3)) == 3


def test_shipped_config_declares_json_sources() -> None:
    sources = {s.code: s for s in load_sources(Path(__file__).resolve().parents[1] / "config" / "sources.yaml")}
    assert sources["gupy-api"].kind is SourceKind.JSON
    assert sources["primeiravagatech"].kind is SourceKind.JSON
    assert sources["gupy-api"].api["fields"]["url"] == "jobUrl"


# --- Quero Vagas Tech (10/10/2026): API JSON pública do agregador ------------------


def test_querovagastech_maps_api_item_to_record() -> None:
    sources = {s.code: s for s in load_sources(Path(__file__).resolve().parents[1] / "config" / "sources.yaml")}
    source = sources["querovagastech"]
    assert source.kind is SourceKind.JSON and source.tech_focus
    assert source.query_param == "q" and source.api["page_mode"] == "page1"
    item = {
        "id": "eb2daa8d-0000-0000-0000-000000000000",
        "title": "Desenvolvedor Java Júnior",
        "company": "Empresa Exemplo",
        "location": "Br",
        "workMode": "Remote",
        "seniority": "Junior",
        "employmentType": "CLT",
        "applyUrl": "https://exemplo.inhire.app/vagas/abc/desenvolvedor-java-junior",
        "sourceName": "Manual",
        "postedAt": "2026-09-24T23:13:56.0469385+00:00",
    }
    record = record_from_item(item, source, "2026-10-10T00:00:00+00:00")
    assert record is not None
    assert record.canonical_url == item["applyUrl"]
    assert record.company == "Empresa Exemplo"
    assert record.workplace_model is WorkplaceModel.REMOTE
    assert record.published_at is not None and record.published_at.startswith("2026-09-24T23:13:56")
    assert record.employment_type == "CLT"
