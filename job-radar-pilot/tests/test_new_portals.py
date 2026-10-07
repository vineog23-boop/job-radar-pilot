from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from scrapling.parser import Adaptor

from job_radar.config import ConfigError, _load_source, load_sources
from job_radar.enrich import enrich_records
from job_radar.fetching import BlockReason, FetchResult
from job_radar.identity import identity_key
from job_radar.link_check import verify_records
from job_radar.models import CollectionStatus, SourceConfig, SourceKind
from job_radar.output import _record_payload
from job_radar.sources import adapter_for
from job_radar.sources.json_api import page_url

PROJECT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "new-portals"
CODES = ("inhire-programmers", "inhire-bionexo", "ciandt", "greenhouse-abinbev")


def source(code):
    return next(
        s for s in load_sources(PROJECT / "config/sources.yaml") if s.code == code
    )


def page(html, url):
    dom = Adaptor(html, url=url)
    return SimpleNamespace(
        text=html, css=dom.css, urljoin=dom.urljoin, status=200, url=url
    )


class Fetcher:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def fetch(self, url, config):
        self.calls.append(url)
        if isinstance(self.response, FetchResult):
            return self.response
        return FetchResult(CollectionStatus.SUCCESS, response=self.response, attempts=1)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def html_result(code, html=None):
    config = source(code)
    name = "ciandt-cards" if code == "ciandt" else code + "-rendered"
    html = (
        html
        if html is not None
        else (FIXTURES / (name + "-sanitized.html")).read_text(encoding="utf-8")
    )
    fetcher = Fetcher(page(html, config.start_url))
    return adapter_for(config).collect(config, fetcher)


def greenhouse(payload=None, config=None):
    config = config or source("greenhouse-abinbev")
    if payload is None:
        payload = json.loads(
            (FIXTURES / "greenhouse-abinbev-sanitized.json").read_text(encoding="utf-8")
        )
    fetcher = Fetcher(SimpleNamespace(body=json.dumps(payload).encode()))
    return adapter_for(config).collect(config, fetcher), fetcher


def test_four_public_company_sources():
    for code in CODES:
        config = source(code)
        assert (
            config.enabled
            and config.max_pages == 1
            and config.min_interval_seconds >= 3
        )
        assert not config.requires_auth and not config.queries
    for code in CODES[:2]:
        config = source(code)
        assert config.kind is SourceKind.DYNAMIC and not config.adaptive
        assert (
            config.start_url
            == f"https://{code.removeprefix('inhire-')}.inhire.app/vagas"
        )
    assert source("ciandt").default_country is None
    assert source("ciandt").fetch_details is False
    assert source("greenhouse-abinbev").default_country is None
    assert source("greenhouse-abinbev").tech_focus is False


@pytest.mark.parametrize(
    "code,company",
    [
        ("inhire-programmers", "Programmers"),
        ("inhire-bionexo", "Bionexo"),
        ("ciandt", "CI&T"),
    ],
)
def test_rendered_cards_have_stable_ids_and_explicit_company(code, company):
    result = html_result(code)
    assert result.status is CollectionStatus.SUCCESS
    assert len(result.records) == 2
    assert len({r.source_job_id for r in result.records}) == 2
    for record in result.records:
        assert len(record.source_job_id) == 36
        assert record.company == company and record.published_at is None
        assert record.canonical_url.startswith("https://")
        assert record.title


def test_inhire_slug_and_title_changes_keep_identity():
    first = html_result("inhire-bionexo").records[0]
    html = (FIXTURES / "inhire-bionexo-rendered-sanitized.html").read_text(encoding="utf-8")
    changed = html_result(
        "inhire-bionexo",
        html.replace("desenvolvedor-java-junior", "novo-slug").replace(
            "Desenvolvedor Java Junior", "Novo título"
        ),
    ).records[0]
    assert identity_key(first) == identity_key(changed)


@pytest.mark.parametrize("code", CODES[:2])
def test_inhire_shell_is_error_and_observed_load_more_is_partial(code):
    assert (
        html_result(code, '<main><div id="root"></div></main>').status
        is CollectionStatus.ERROR
    )
    html = (FIXTURES / (code + "-rendered-sanitized.html")).read_text(encoding="utf-8")
    result = html_result(code, html + "<button>Carregar mais vagas</button>")
    assert result.status is CollectionStatus.PARTIAL and result.has_more


@pytest.mark.parametrize(
    "reason,status",
    [
        (BlockReason.LOGIN_REQUIRED, CollectionStatus.AUTH_REQUIRED),
        (BlockReason.CAPTCHA, CollectionStatus.BLOCKED),
    ],
)
def test_inhire_does_not_hide_blocked_or_login(reason, status):
    config = source("inhire-bionexo")
    result = adapter_for(config).collect(
        config, Fetcher(FetchResult(CollectionStatus.BLOCKED, block_reason=reason))
    )
    assert result.status is status and not result.records


def test_ciandt_never_fetches_detail_and_preserves_manual_url():
    records = tuple(
        replace(r, match_labels=("FIT:READY", "TECH_MATCH:Java"))
        for r in html_result("ciandt").records
    )
    config = source("ciandt")
    fetcher = Fetcher(None)
    enriched, count = enrich_records(
        records, lambda r: r, [config], limit=100, fetcher_factory=lambda: fetcher
    )
    checked, counts = verify_records(
        records,
        [config],
        only_best_fit=False,
        limit=None,
        fetcher_factory=lambda: fetcher,
    )
    assert enriched == records and count == 0 and fetcher.calls == []
    assert counts["LINK:UNKNOWN"] == 2
    assert [r.canonical_url for r in checked] == [r.canonical_url for r in records]


def test_greenhouse_single_exact_request_fields_and_schema():
    config = replace(source("greenhouse-abinbev"), max_pages=10)
    assert page_url(config, 5) == config.start_url
    result, fetcher = greenhouse(config=config)
    assert result.status is CollectionStatus.SUCCESS
    assert fetcher.calls == [
        "https://boards-api.greenhouse.io/v1/boards/abinbev/jobs?content=true"
    ]
    record = result.records[0]
    assert record.source_job_id == "8647555002"
    assert record.company == "AB InBev | Growth Group"
    assert record.location == "São Paulo, Brazil"
    assert record.published_at == "2026-07-23T13:54:52-04:00"
    assert record.application_deadline is None
    validator = Draft202012Validator(
        json.loads((PROJECT / "schemas/vagas.schema.json").read_text(encoding="utf-8")),
        format_checker=FormatChecker(),
    )
    validator.validate(_record_payload(record))


@pytest.mark.parametrize(
    "payload,status,reason",
    [
        ({"jobs": [], "meta": {"total": 0}}, CollectionStatus.EMPTY, "NO_RESULTS"),
        ({"meta": {"total": 0}}, CollectionStatus.ERROR, "LAYOUT_CHANGED"),
        (
            {"jobs": [], "meta": {"total": 2}},
            CollectionStatus.PARTIAL,
            "TOTAL_MISMATCH",
        ),
        (
            {"jobs": [{}], "meta": {"total": 1}},
            CollectionStatus.ERROR,
            "PARSE_ZERO_RECORDS",
        ),
    ],
)
def test_single_api_truthful_status(payload, status, reason):
    result, fetcher = greenhouse(payload)
    assert result.status is status and result.stop_reason == reason
    assert len(fetcher.calls) == 1


@pytest.mark.parametrize("total", [0, 2, None, "1", True])
def test_single_api_inconsistent_total_is_partial(total):
    payload = json.loads((FIXTURES / "greenhouse-abinbev-sanitized.json").read_text(encoding="utf-8"))
    payload["meta"]["total"] = total
    result, _ = greenhouse(payload)
    assert (
        result.status is CollectionStatus.PARTIAL
        and result.stop_reason == "TOTAL_MISMATCH"
    )


@pytest.mark.parametrize(
    "key,value",
    [("default_company", ""), ("default_company", 10), ("fetch_details", "false")],
)
def test_source_fields_are_validated(key, value):
    raw = dict(
        code="x",
        kind="dynamic",
        start_url="https://example.org",
        enabled=True,
        max_pages=1,
        min_interval_seconds=3,
        requires_auth=False,
    )
    raw[key] = value
    with pytest.raises(ConfigError):
        _load_source(raw, 0)


def test_default_company_does_not_replace_card_company():
    config = SourceConfig(
        code="x",
        kind=SourceKind.GENERIC,
        start_url="https://example.org",
        enabled=True,
        max_pages=1,
        min_interval_seconds=3,
        requires_auth=False,
        default_company="Fallback",
        single_page=True,
        selectors={
            "card": "article",
            "title": "h2",
            "url": "a::attr(href)",
            "company": ".company",
        },
    )
    parsed = adapter_for(config).parse_page(
        page(
            '<article><h2>Dev</h2><a href="/1">Link</a><span class="company">Real</span></article>',
            config.start_url,
        ),
        config,
    )
    assert parsed.records[0].company == "Real"


def test_single_api_without_total_and_with_incomplete_items():
    config = source("greenhouse-abinbev")
    payload = json.loads((FIXTURES / "greenhouse-abinbev-sanitized.json").read_text(encoding="utf-8"))
    item = payload["jobs"][0]
    item["content"] = "<p>Java &amp; Spring</p>"
    item["application_deadline"] = "2026-11-01"
    result, _ = greenhouse(payload)
    assert result.records[0].description_summary == "Java & Spring"
    assert result.records[0].application_deadline == "2026-11-01T00:00:00+00:00"
    payload["jobs"].append({})
    payload["meta"]["total"] = 2
    result, _ = greenhouse(payload)
    assert (
        result.status is CollectionStatus.PARTIAL
        and result.stop_reason == "PARSE_INCOMPLETE"
    )
    api = dict(config.api)
    api.pop("total_path")
    result, _ = greenhouse({"jobs": []}, replace(config, api=api))
    assert result.status is CollectionStatus.EMPTY


def test_new_source_defaults_and_total_path_validation():
    raw = dict(
        code="x",
        kind="dynamic",
        start_url="https://example.org",
        enabled=True,
        max_pages=1,
        min_interval_seconds=3,
        requires_auth=False,
    )
    config = _load_source(raw, 0)
    assert config.default_company is None and config.fetch_details is True
    raw.update(
        kind="json",
        api=dict(
            page_mode="single",
            items="jobs",
            fields={"title": "title", "url": "url"},
            total_path="",
        ),
    )
    with pytest.raises(ConfigError):
        _load_source(raw, 0)


def test_utf8_fixtures_preserve_accents_under_windows_locale(monkeypatch):
    original = Path.read_text

    def windows_read_text(path, encoding=None, errors=None, **kwargs):
        return original(path, encoding=encoding or "cp1252", errors=errors, **kwargs)

    monkeypatch.setattr(Path, "read_text", windows_read_text)
    result, _ = greenhouse()
    assert result.records[0].location == "São Paulo, Brazil"
    assert any("Híbrido" in record.title for record in html_result("inhire-bionexo").records)
