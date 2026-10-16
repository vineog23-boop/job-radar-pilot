from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
import json

import pytest

from job_radar.enrich import enrich_records
from job_radar.fetching import FetchResult
from job_radar.models import CollectionStatus
from test_enrich import _record, _source, _with

NOW = datetime(2026, 10, 16, 20, tzinfo=timezone.utc)


class Pages:
    def __init__(self, text="Requisitos Java Spring Boot junior remoto Brasil. " * 5, blocked=False):
        self.text, self.blocked, self.urls = text, blocked, []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def fetch(self, url, source):
        self.urls.append(url)
        if self.blocked:
            return FetchResult(status=CollectionStatus.BLOCKED)
        html = f"<html><main><p>{self.text}</p></main></html>"
        return FetchResult(status=CollectionStatus.SUCCESS, response=SimpleNamespace(body=html.encode(), status=200, url=url))


def run(records, pages, limit=2):
    return enrich_records(records, lambda r: _with(r, ("FIT:READY",)), [_source()],
                          limit=limit, now=NOW, fetcher_factory=lambda: pages)


def test_duplicate_pages_do_not_consume_the_budget_for_distinct_vacancies():
    first = _record()
    duplicate = replace(first, source_job_id="alias")
    other = replace(first, source_job_id="2", canonical_url="https://x.com.br/gupy/2")
    pages = Pages()
    updated, count = run([first, duplicate, other], pages)
    assert pages.urls == ["https://x.com.br/gupy/1", "https://x.com.br/gupy/2"]
    assert count == 3
    assert all("ENRICHED:DETAIL" in r.match_labels for r in updated)
    assert updated[0].description_summary == updated[1].description_summary


def test_blocked_duplicate_page_is_not_retried_in_the_same_collection():
    record = _record()
    pages = Pages(blocked=True)
    updated, count = run([record, replace(record, source_job_id="alias")], pages)
    assert pages.urls == ["https://x.com.br/gupy/1"]
    assert count == 0 and updated[0].description_summary is None


def test_different_job_ids_in_query_parameters_are_distinct_pages():
    first = replace(_record(), canonical_url="https://x.com.br/job?id=1")
    second = replace(first, source_job_id="2", canonical_url="https://x.com.br/job?id=2")
    pages = Pages()
    updated, count = run([first, second], pages)
    assert pages.urls == ["https://x.com.br/job?id=1", "https://x.com.br/job?id=2"]
    assert count == len(updated) == 2


def test_complete_details_have_a_fresh_timestamp_for_safe_reuse():
    updated, _ = run([_record()], Pages())
    assert "ENRICHED:DETAIL_AT:2026-10-16T20:00:00+00:00" in updated[0].match_labels
    assert "ENRICHED:DETAIL_COMPLETE" in updated[0].match_labels


def test_truncated_details_never_keep_an_old_complete_marker():
    record = replace(_record(), match_labels=("ENRICHED:DETAIL_COMPLETE", "ENRICHED:DETAIL_AT:2026-09-01T00:00:00+00:00"))
    updated, _ = run([record], Pages(text="Java Spring Boot requisitos. " * 200))
    assert "ENRICHED:DETAIL_COMPLETE" not in updated[0].match_labels
    assert "ENRICHED:DETAIL_AT:2026-09-01T00:00:00+00:00" not in updated[0].match_labels
    assert "ENRICHED:DETAIL_AT:2026-10-16T20:00:00+00:00" in updated[0].match_labels


@pytest.mark.parametrize('kind', ['jsonld', 'jsonld-uri', 'jsonld-spaced', 'nextdata'])
def test_requirements_only_in_structured_data_prevent_reusing_a_visible_summary(kind):
    hidden_requirements = 'Requisitos obrigatórios: 5 anos de experiência e Kubernetes.'
    if kind.startswith('jsonld'):
        data = {'@type': 'https://schema.org/JobPosting' if kind == 'jsonld-uri' else 'JobPosting', 'description': hidden_requirements}
        script = f'<script type="application/ld+json">{json.dumps(data)}</script>'
        if kind == 'jsonld-spaced':
            script = script.replace('type=', 'type = ')
    else:
        data = {'props': {'pageProps': {'jobData': {'requirements': hidden_requirements}}}}
        script = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
    pages = Pages(text='Desenvolvedor Java Junior remoto. ' * 8 + script)
    updated, _ = run([_record()], pages)
    assert 'ENRICHED:DETAIL_COMPLETE' not in updated[0].match_labels


def test_structured_description_can_be_reused_when_fully_present_in_visible_text():
    text = 'Requisitos Java Spring Boot SQL REST. ' * 5
    script = '<script type="application/ld+json">' + json.dumps({'@type': 'JobPosting', 'description': text}) + '</script>'
    updated, _ = run([_record()], Pages(text=text + script))
    assert 'ENRICHED:DETAIL_COMPLETE' in updated[0].match_labels


def test_notice_outside_the_focused_main_prevents_complete_marker():
    text = 'Requisitos Java Spring Boot junior remoto Brasil. ' * 5

    class FocusedPages(Pages):
        def fetch(self, url, source):
            result = super().fetch(url, source)
            result.response.body = f'<p>Vaga encerrada</p><main>{text}</main>'.encode()
            result.response.xpath = lambda _: SimpleNamespace(getall=lambda: [text])
            return result

    updated, _ = run([_record()], FocusedPages())
    assert 'ENRICHED:DETAIL_COMPLETE' not in updated[0].match_labels


def test_structured_job_status_is_not_lost_when_reusing_plain_text():
    text = 'Requisitos Java Spring Boot SQL REST. ' * 5
    data = {'props': {'pageProps': {'job': {'description': text, 'status': 'unpublished'}}}}
    script = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
    updated, _ = run([_record()], Pages(text=text + script))
    assert 'ENRICHED:DETAIL_COMPLETE' not in updated[0].match_labels
