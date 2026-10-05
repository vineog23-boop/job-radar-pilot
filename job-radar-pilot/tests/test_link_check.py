from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from job_radar.fetching import FetchResult
from job_radar.link_check import (
    LINK_DEAD,
    LINK_LIVE,
    LINK_UNKNOWN,
    classify_page_text,
    link_status,
    verify_records,
)
from job_radar.models import CollectionStatus, SourceConfig, SourceKind, VacancyRecord


def _source(code="primeiravagatech"):
    return SourceConfig(
        code=code, kind=SourceKind.JSON, start_url="https://x.com.br/v",
        enabled=True, max_pages=1, min_interval_seconds=1, requires_auth=False,
    )


def _record(code="primeiravagatech", labels=("FIT:READY",), url=None):
    return VacancyRecord(
        source=code, source_job_id="1", canonical_url=url or f"https://x.com.br/{code}/1",
        title="Vaga", company=None, description_summary=None, location=None,
        observed_at="2026-09-29T00:00:00+00:00", evidence_snippets=(), match_labels=labels,
    )


class _ScriptedFetcher:
    """Fetcher falso: devolve a próxima resposta programada por URL chamada."""

    def __init__(self, pages: dict[str, str]):
        self._pages = pages
        self.urls: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def fetch(self, url, source):
        self.urls.append(url)
        html = self._pages.get(url)
        if html is None:
            return FetchResult(status=CollectionStatus.ERROR, response=None)
        return FetchResult(
            status=CollectionStatus.SUCCESS,
            response=SimpleNamespace(body=html.encode(), status=200, url=url),
        )


def test_classify_page_text_detects_dead_markers() -> None:
    assert classify_page_text("Vaga não encontrada ou erro ao carregar") == LINK_DEAD
    assert classify_page_text("This job is no longer available") == LINK_DEAD


def test_classify_page_text_live_with_enough_content() -> None:
    text = "Descrição completa da vaga com requisitos em Java e Spring Boot. " * 3
    assert classify_page_text(text) == LINK_LIVE


def test_classify_page_text_unknown_when_empty_or_short() -> None:
    assert classify_page_text("") == LINK_UNKNOWN
    assert classify_page_text(None) == LINK_UNKNOWN
    assert classify_page_text("curto") == LINK_UNKNOWN


def test_verify_records_marks_dead_and_live_from_fresh_fetch() -> None:
    live_html = "<html><body><p>" + "Requisitos Java Spring Boot junior remoto. " * 6 + "</p></body></html>"
    dead_html = "<html><body><p>Vaga não encontrada ou erro ao carregar</p></body></html>"
    dead_record = _record(url="https://x.com.br/primeiravagatech/dead")
    live_record = _record(url="https://x.com.br/primeiravagatech/live")
    fetcher = _ScriptedFetcher(
        {
            dead_record.canonical_url: dead_html,
            live_record.canonical_url: live_html,
        }
    )

    updated, counts = verify_records(
        [dead_record, live_record], [_source()], fetcher_factory=lambda: fetcher
    )

    assert link_status(updated[0].match_labels) == LINK_DEAD
    assert link_status(updated[1].match_labels) == LINK_LIVE
    assert counts == {LINK_LIVE: 1, LINK_DEAD: 1, LINK_UNKNOWN: 0}
    assert any(label.startswith("LINK_CHECKED_AT:") for label in updated[0].match_labels)


def test_verify_records_skips_non_best_fit_by_default() -> None:
    other = _record(labels=("FIT:OTHER_STACK",))
    fetcher = _ScriptedFetcher({})

    updated, counts = verify_records([other], [_source()], fetcher_factory=lambda: fetcher)

    assert link_status(updated[0].match_labels) is None
    assert counts == {LINK_LIVE: 0, LINK_DEAD: 0, LINK_UNKNOWN: 0}
    assert fetcher.urls == []


def test_verify_records_includes_all_when_only_best_fit_is_false() -> None:
    other = _record(labels=("FIT:AMBIGUOUS",))
    fetcher = _ScriptedFetcher(
        {other.canonical_url: "<html><body>" + "conteudo real da vaga aqui. " * 6 + "</body></html>"}
    )

    updated, counts = verify_records(
        [other], [_source()], only_best_fit=False, fetcher_factory=lambda: fetcher
    )

    assert link_status(updated[0].match_labels) == LINK_LIVE
    assert counts[LINK_LIVE] == 1


def test_verify_records_skips_indeed_as_unknown_without_fetch() -> None:
    record = _record(code="indeed", url="https://br.indeed.com/viewjob?jk=1")
    fetcher = _ScriptedFetcher({})

    updated, counts = verify_records(
        [record], [_source("indeed")], fetcher_factory=lambda: fetcher
    )

    assert link_status(updated[0].match_labels) == LINK_UNKNOWN
    assert fetcher.urls == []
    assert counts[LINK_UNKNOWN] == 1


def test_verify_records_limit_caps_how_many_are_checked() -> None:
    records = [_record(url=f"https://x.com.br/primeiravagatech/{i}") for i in range(5)]
    fetcher = _ScriptedFetcher(
        {record.canonical_url: "conteudo real da vaga aqui. " * 10 for record in records}
    )

    _, counts = verify_records(records, [_source()], limit=2, fetcher_factory=lambda: fetcher)

    assert sum(counts.values()) == 2
    assert len(fetcher.urls) == 2


def test_verify_records_replaces_previous_link_labels() -> None:
    record = _record(labels=("FIT:READY", "LINK:DEAD", "LINK_CHECKED_AT:old"))
    fetcher = _ScriptedFetcher(
        {record.canonical_url: "conteudo real e atual da vaga agora. " * 6}
    )

    updated, _ = verify_records([record], [_source()], fetcher_factory=lambda: fetcher)

    labels = updated[0].match_labels
    assert labels.count("LINK:DEAD") == 0
    assert link_status(labels) == LINK_LIVE
    assert sum(label.startswith("LINK_CHECKED_AT:") for label in labels) == 1
