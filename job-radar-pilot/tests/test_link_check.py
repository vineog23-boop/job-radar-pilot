from __future__ import annotations

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
    text = "Vaga Java. Descrição completa com requisitos em Java e Spring Boot. Candidate-se agora. " * 3
    assert classify_page_text(text) == LINK_LIVE


def test_classify_page_text_unknown_when_empty_or_short() -> None:
    assert classify_page_text("") == LINK_UNKNOWN
    assert classify_page_text(None) == LINK_UNKNOWN
    assert classify_page_text("curto") == LINK_UNKNOWN


def test_verify_records_marks_dead_and_live_from_fresh_fetch() -> None:
    live_html = "<html><body><p>" + "Vaga Java Spring Boot junior remoto. Requisitos Java. Candidate-se agora. " * 6 + "</p></body></html>"
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
        {other.canonical_url: "<html><body>" + "Vaga Java com requisitos e responsabilidades. Candidate-se agora. " * 6 + "</body></html>"}
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
        {record.canonical_url: "Vaga Java com requisitos e responsabilidades. Candidate-se agora. " * 10 for record in records}
    )

    _, counts = verify_records(records, [_source()], limit=2, fetcher_factory=lambda: fetcher)

    assert sum(counts.values()) == 2
    assert len(fetcher.urls) == 2


def test_verify_records_replaces_previous_link_labels() -> None:
    record = _record(labels=("FIT:READY", "LINK:DEAD", "LINK_CHECKED_AT:old"))
    fetcher = _ScriptedFetcher(
        {record.canonical_url: "Vaga Java com requisitos e responsabilidades. Candidate-se agora. " * 6}
    )

    updated, _ = verify_records([record], [_source()], fetcher_factory=lambda: fetcher)

    labels = updated[0].match_labels
    assert labels.count("LINK:DEAD") == 0
    assert link_status(labels) == LINK_LIVE
    assert sum(label.startswith("LINK_CHECKED_AT:") for label in labels) == 1


def test_institutional_login_and_captcha_never_confirm_live():
    for text in (
        "Nossa empresa e nossos valores. " * 20,
        "Faça login para continuar. Vaga Java requisitos candidate-se. " * 8,
        "CAPTCHA confirme que você é humano. Vaga Java candidate-se. " * 8,
    ):
        assert classify_page_text(text) == LINK_UNKNOWN


def test_job_identity_required_when_title_available():
    from job_radar.link_check import check_canonical_url
    url = "https://x.com.br/jobs/1"
    fetcher = _ScriptedFetcher({url: "Vaga Python requisitos responsabilidades candidate-se agora."})
    assert check_canonical_url(url, _source(), fetcher, expected_title="Java Junior") == LINK_UNKNOWN
    fetcher = _ScriptedFetcher({url: "Java Junior vaga requisitos responsabilidades candidate-se agora."})
    assert check_canonical_url(url, _source(), fetcher, expected_title="Java Junior") == LINK_LIVE


def test_authorized_404_and_410_are_dead_but_failed_fetch_is_unknown():
    from job_radar.link_check import check_canonical_url
    class Fetcher:
        def __init__(self, status, code):
            self.status, self.code = status, code
        def fetch(self, url, source):
            return FetchResult(status=self.status, response=SimpleNamespace(status=self.code, body=b"", url=url))
    for code in (404, 410):
        assert check_canonical_url("https://x.com.br/jobs/1", _source(), Fetcher(CollectionStatus.SUCCESS, code)) == LINK_DEAD
        assert check_canonical_url("https://x.com.br/jobs/1", _source(), Fetcher(CollectionStatus.BLOCKED, code)) == LINK_UNKNOWN


def test_redirect_to_home_does_not_confirm_another_job():
    from job_radar.link_check import check_canonical_url
    class Fetcher:
        def fetch(self, url, source):
            return FetchResult(status=CollectionStatus.SUCCESS, response=SimpleNamespace(status=200, body=b"Vaga Java requisitos responsabilidades candidate-se agora. " * 10, url="https://x.com.br/"))
    assert check_canonical_url("https://x.com.br/jobs/1", _source(), Fetcher()) == LINK_UNKNOWN


def test_verification_emits_method_progress_and_prioritizes_best_score():
    from datetime import datetime, timezone
    low = _record(labels=("FIT:CONDITIONAL", "FIT_SCORE:1"), url="https://x.com.br/low")
    high = _record(labels=("FIT:READY", "FIT_SCORE:4"), url="https://x.com.br/high")
    fetcher = _ScriptedFetcher({high.canonical_url: "Vaga requisitos responsabilidades candidate-se agora."})
    progress = []
    updated, counts = verify_records([low, high], [_source()], limit=1, fetcher_factory=lambda: fetcher,
        now=datetime(2026, 10, 6, tzinfo=timezone.utc), on_progress=lambda *args: progress.append(args))
    assert link_status(updated[0].match_labels) is None
    assert "LINK_CHECK_METHOD:JOB_DETAIL_V2" in updated[1].match_labels
    assert progress[0][0:2] == (0, 1)
    assert progress[-1][0:2] == (1, 1)
    assert counts[LINK_LIVE] == 1


def test_structured_jobposting_with_identity_confirms_without_visible_apply():
    from job_radar.link_check import check_canonical_url
    url = 'https://x.com.br/jobs/1'
    html = '''<html><body>Oportunidade em nossa equipe<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"Java Junior","description":"Requisitos Java e Spring Boot"}</script></body></html>'''
    fetcher = _ScriptedFetcher({url: html})
    assert check_canonical_url(url, _source(), fetcher, expected_title='Java Junior') == LINK_LIVE
    assert check_canonical_url(url, _source(), fetcher, expected_title='Python Senior') == LINK_UNKNOWN


def test_login_url_with_job_content_is_unknown():
    from job_radar.link_check import check_canonical_url
    class Fetcher:
        def fetch(self, url, source):
            return FetchResult(status=CollectionStatus.SUCCESS, response=SimpleNamespace(status=200,
                body=b'Vaga Java requisitos responsabilidades candidate-se agora.', url='https://x.com.br/login'))
    assert check_canonical_url('https://x.com.br/jobs/1', _source(), Fetcher()) == LINK_UNKNOWN


def test_disabled_or_authenticated_sources_are_not_fetched():
    from dataclasses import replace
    record = _record()
    for source in (replace(_source(), enabled=False), replace(_source(), requires_auth=True)):
        fetcher = _ScriptedFetcher({record.canonical_url: 'Vaga requisitos candidate-se agora.'})
        updated, _ = verify_records([record], [source], fetcher_factory=lambda: fetcher)
        assert link_status(updated[0].match_labels) == LINK_UNKNOWN
        assert fetcher.urls == []


def test_verify_output_preserves_observation_and_tracking_and_refuses_corruption(tmp_path):
    import json
    import pytest
    from job_radar.cleanup import CleanupError
    from job_radar.link_check import verify_output
    from job_radar.output import _record_payload
    record = _record()
    payload = _record_payload(record)
    output = tmp_path / 'output'
    output.mkdir()
    path = output / 'vagas.jsonl'
    path.write_text(json.dumps(payload) + '\n')
    tracking = output / 'tracking.json'
    tracking.write_text('{"saved":"intacto"}')
    fetcher = _ScriptedFetcher({record.canonical_url: 'Vaga requisitos responsabilidades candidate-se agora.'})
    result = verify_output(output, [_source()], fetcher_factory=lambda: fetcher)
    verified = json.loads(path.read_text())
    assert result['checked'] == 1
    assert verified['observed_at'] == '2026-09-29T00:00:00+00:00'
    for key in payload.keys() - {'match_labels', 'content_hash'}:
        assert verified[key] == payload[key]
    assert tracking.read_text() == '{"saved":"intacto"}'
    path.write_text(json.dumps(payload) + '\ncorrompido\n')
    before = path.read_bytes()
    with pytest.raises(CleanupError):
        verify_output(output, [_source()], fetcher_factory=lambda: fetcher)
    assert path.read_bytes() == before


def test_redirect_to_named_home_does_not_confirm_job():
    from job_radar.link_check import check_canonical_url
    class Fetcher:
        def fetch(self, url, source):
            return FetchResult(status=CollectionStatus.SUCCESS, response=SimpleNamespace(status=200,
                body=b'Vaga Java requisitos responsabilidades candidate-se agora.' * 8,
                url='https://x.com.br/home'))
    assert check_canonical_url('https://x.com.br/jobs/1', _source(), Fetcher()) == LINK_UNKNOWN


def test_redirect_to_nested_listings_does_not_confirm_card_identity():
    from job_radar.link_check import check_canonical_url
    class Fetcher:
        def __init__(self, final_url):
            self.final_url = final_url
        def fetch(self, url, source):
            return FetchResult(status=CollectionStatus.SUCCESS, response=SimpleNamespace(
                status=200, url=self.final_url,
                body=b'<article>Java Junior vaga requisitos responsabilidades candidate-se agora.</article><article>Python Junior vaga requisitos candidate-se.</article>'))
    for path in ('/pt-BR/jobs', '/jobs/search'):
        assert check_canonical_url('https://x.com.br/jobs/123', _source(),
            Fetcher('https://x.com.br' + path), expected_title='Java Junior') == LINK_UNKNOWN


def test_redirect_to_localized_job_detail_keeps_matching_identity():
    from job_radar.link_check import check_canonical_url
    class Fetcher:
        def fetch(self, url, source):
            return FetchResult(status=CollectionStatus.SUCCESS, response=SimpleNamespace(
                status=200, url='https://x.com.br/pt-BR/jobs/123',
                body=b'Java Junior vaga requisitos responsabilidades candidate-se agora.'))
    assert check_canonical_url('https://x.com.br/jobs/123', _source(), Fetcher(),
        expected_title='Java Junior') == LINK_LIVE
