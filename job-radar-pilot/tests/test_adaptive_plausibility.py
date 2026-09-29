from __future__ import annotations

from job_radar.models import SourceConfig, VacancyRecord
from job_radar.sources.base import (
    PaginatedAdapter,
    ParsedPage,
    _adaptive_result_plausible,
)


def _config() -> SourceConfig:
    return SourceConfig(
        code="programathor",
        kind="generic",
        start_url="https://programathor.com.br/jobs-java",
        enabled=True,
        max_pages=20,
        min_interval_seconds=1,
        requires_auth=False,
        selectors={"card": ".x", "title": "h3", "url": "::attr(href)"},
    )


def _record(title: str, url: str) -> VacancyRecord:
    return VacancyRecord(
        source="programathor",
        source_job_id=None,
        canonical_url=url,
        title=title,
        company=None,
        description_summary=None,
        location=None,
        observed_at="2026-09-29T00:00:00+00:00",
        evidence_snippets=(title,),
    )


def _plausible(records, *, first_page=True, text="", url="https://programathor.com.br/jobs-java"):
    return _adaptive_result_plausible(
        _config(),
        ParsedPage(tuple(records), len(records), card_method="ADAPTIVE"),
        url,
        first_page=first_page,
        page_text=text,
        empty_markers=PaginatedAdapter.empty_markers,
    )


GOOD = [
    _record("Desenvolvedor Java Junior", "https://programathor.com.br/jobs/1-java"),
    _record("Backend Spring Boot Pleno", "https://programathor.com.br/jobs/2-spring"),
]


def test_accepts_two_real_jobs_on_first_page() -> None:
    assert _plausible(GOOD)


def test_rejects_relocation_after_first_page() -> None:
    assert not _plausible(GOOD, first_page=False)


def test_rejects_when_page_declares_no_results() -> None:
    assert not _plausible(GOOD, text="nenhuma vaga encontrada para a sua busca")


def test_rejects_filter_link_named_clt() -> None:
    fake = [
        _record(
            "CLT",
            "https://programathor.com.br/jobs-java?contract_type=CLT&page=2",
        )
    ]
    assert not _plausible(fake, url="https://programathor.com.br/jobs-java?page=2")


def test_rejects_login_link() -> None:
    fake = [
        _record("Entrar na plataforma", "https://casado.dev/login"),
        _record("Entrar novamente", "https://casado.dev/entrar"),
    ]
    assert not _plausible(fake)


def test_requires_at_least_two_valid_jobs() -> None:
    assert not _plausible(GOOD[:1])
