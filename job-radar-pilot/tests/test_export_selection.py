"""Downloads da tabela respeitam seleção, ordem e versão da saída local."""
from __future__ import annotations

import csv
import io
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from xml.etree import ElementTree
import zipfile

import pytest

from job_radar.output_lock import OutputLock
from job_radar.webapp import SearchController, create_server, filter_jobs_for_export
from job_radar.xlsx_export import job_score

NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
FORMATS = ('csv', 'markdown', 'xlsx', 'ai')


def _job(number, **extra):
    job = {'canonical_url': f'https://example.com/jobs/{number}', 'title': f'Vaga {number}',
           'company': 'Exemplo', 'source': 'fixture', 'workplace_model': 'REMOTE',
           'match_labels': ['FIT:READY', 'FIT_SCORE:4'],
           'published_at': (NOW - timedelta(days=1)).isoformat(), 'observed_at': NOW.isoformat()}
    job.update(extra)
    return job


@contextmanager
def _serve(tmp_path, jobs):
    output = tmp_path / 'output'
    output.mkdir()
    (output / 'vagas.jsonl').write_text(''.join(json.dumps(j) + '\n' for j in jobs), encoding='utf-8')
    controller = SearchController(output, runner=lambda *_: 0)
    server = create_server('127.0.0.1', 0, controller,
                          Path(__file__).resolve().parents[1] / 'src/job_radar/web',
                          preferences_path=tmp_path / 'prefs.json', tracking_path=tmp_path / 'tracking.json')
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', controller
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _post(base, kind, payload, **headers):
    body = json.dumps(payload).encode()
    request = Request(f'{base}/api/export/{kind}', data=body, method='POST',
                      headers={'Content-Type': 'application/json', **headers})
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, response.read(), response.headers
    except HTTPError as error:
        return error.code, error.read(), error.headers


def _titles(kind, body):
    if kind == 'csv':
        return [row['titulo'] for row in csv.DictReader(io.StringIO(body.decode('utf-8-sig')), delimiter=';')]
    if kind == 'xlsx':
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            sheet = ElementTree.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        return [row.findall('m:c', ns)[1].findtext('.//m:t', namespaces=ns)
                for row in sheet.findall('.//m:row', ns)[1:]]
    text = body.decode('utf-8-sig')
    if kind == 'markdown':
        return [line[4:] for line in text.splitlines() if line.startswith('### ')]
    return [line.split('|')[3].strip() for line in text.splitlines() if line.startswith('| ') and line.split('|')[1].strip().isdigit()]


@pytest.mark.parametrize('kind', FORMATS)
def test_selection_preserves_exact_order_and_uses_only_local_records(tmp_path, kind):
    jobs = [_job(1), _job(2, match_labels=['FIT:CONDITIONAL', 'FIT_SCORE:1']), _job(3)]
    with _serve(tmp_path, jobs) as (base, controller):
        status, body, headers = _post(base, kind, {'urls': [jobs[1]['canonical_url'], jobs[0]['canonical_url']],
                                                  'output_version': controller.snapshot()['output_version']})
    assert status == 200
    assert _titles(kind, body) == ['Vaga 2', 'Vaga 1']
    assert 'attachment;' in headers['Content-Disposition']


@pytest.mark.parametrize('kind', FORMATS)
def test_empty_selection_never_falls_back_to_all_jobs(tmp_path, kind):
    with _serve(tmp_path, [_job(1)]) as (base, controller):
        status, body, _ = _post(base, kind, {'urls': [], 'output_version': controller.snapshot()['output_version']})
    assert status == 200
    assert _titles(kind, body) == []


@pytest.mark.parametrize(('urls', 'version', 'expected'), [
    (['https://example.com/jobs/404'], None, 409),
    (['https://example.com/jobs/1'] * 2, None, 400),
    (['javascript:alert(1)'], None, 400), (['https://'], None, 400),
    (['https://example.com/a b'], None, 400), ([42], None, 400),
    ('https://example.com/jobs/1', None, 400), ([], '', 400),
    ([], 42, 400), ([], 'obsolete', 409),
])
def test_selection_rejects_invalid_or_stale_request(tmp_path, urls, version, expected):
    with _serve(tmp_path, [_job(1)]) as (base, controller):
        status, body, _ = _post(base, 'csv', {'urls': urls, 'output_version': version if version is not None else controller.snapshot()['output_version']})
    assert status == expected
    assert json.loads(body)['error']


def test_selection_rejects_output_changed_after_table_loaded(tmp_path):
    with _serve(tmp_path, [_job(1)]) as (base, controller):
        version = controller.snapshot()['output_version']
        (controller.output_dir / 'vagas.jsonl').write_text(json.dumps(_job(2)), encoding='utf-8')
        status, _, _ = _post(base, 'csv', {'urls': [], 'output_version': version})
    assert status == 409


def test_selection_limits_body_and_number_of_urls_and_requires_version(tmp_path):
    with _serve(tmp_path, [_job(1)]) as (base, controller):
        version = controller.snapshot()['output_version']
        requests = [ {'urls': []},
                     {'urls': [f'https://example.com/{n}' for n in range(20001)], 'output_version': version} ]
        for payload in requests:
            assert _post(base, 'csv', payload)[0] == 400
        # O limite deve recusar o cabeçalho antes de ler/alocar o corpo excessivo.
        connection = HTTPConnection(base.removeprefix('http://'), timeout=5)
        try:
            connection.putrequest('POST', '/api/export/csv')
            connection.putheader('Content-Type', 'application/json')
            connection.putheader('Content-Length', str(2 * 1024 * 1024 + 1))
            connection.endheaders()
            assert connection.getresponse().status == 400
        finally:
            connection.close()


def test_selection_uses_local_http_guards_and_output_lock(tmp_path):
    with _serve(tmp_path, [_job(1)]) as (base, controller):
        payload = {'urls': [], 'output_version': controller.snapshot()['output_version']}
        assert _post(base, 'csv', payload, Host='evil.example')[0] == 403
        assert _post(base, 'csv', payload, **{'Content-Type': 'text/plain'})[0] == 415
        with OutputLock(controller.output_dir):
            assert _post(base, 'csv', payload)[0] == 409


@pytest.mark.parametrize('match', ['fit', 'ready'])
def test_best_export_excludes_closed_without_age_window(match):
    jobs = [_job(1), _job(2, application_deadline=(NOW - timedelta(seconds=1)).isoformat())]
    assert [job['title'] for job in filter_jobs_for_export(jobs, match=match, now=NOW)] == ['Vaga 1']


def test_temporal_filters_use_fractional_days_like_dashboard():
    jobs = [_job(1, published_at=(NOW - timedelta(days=7)).isoformat()),
            _job(2, published_at=(NOW - timedelta(days=7, seconds=1)).isoformat())]
    assert [j['title'] for j in filter_jobs_for_export(jobs, max_age_days=7, now=NOW)] == ['Vaga 1']


@pytest.mark.parametrize(('age', 'expected'), [(3, 60), (3.5, 57), (7.5, 54), (14.5, 52), (30.5, 50)])
def test_score_recency_uses_fractional_days(age, expected):
    assert job_score(_job(1, match_labels=['FIT:READY', 'FIT_SCORE:2'],
                          published_at=(NOW - timedelta(days=age)).isoformat()), NOW) == expected


def test_dashboard_exports_all_301_filtered_rows_in_table_order(tmp_path):
    from playwright.sync_api import sync_playwright
    live = datetime.now(timezone.utc)
    dates = {'published_at': (live - timedelta(days=1)).isoformat(), 'observed_at': live.isoformat()}
    jobs = [_job(n, **dates) for n in range(301)]
    jobs += [_job('presencial', **dates, workplace_model='ONSITE'),
             _job('antiga', **{**dates, 'published_at': (live - timedelta(days=35)).isoformat()}),
             _job('encerrada', **dates, application_deadline=(live - timedelta(days=1)).isoformat()),
             _job('incerta', **{**dates, 'observed_at': None})]
    with _serve(tmp_path, jobs) as (base, controller), sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(base)
        page.locator('#jobs-table-body tr').first.wait_for()
        page.locator('#age-filter').select_option('30')
        page.locator('#activity-filter').select_option('active')
        page.locator('[data-quick="remote"]').click()
        assert page.locator('#visible-count').inner_text() == '300 de 301 vagas'
        page.locator('#export-button').click()
        with page.expect_download() as download_info, page.expect_response(lambda r: r.url.endswith('/api/export/csv') and r.request.method == 'POST') as response_info:
            page.locator('#download-csv').click()
        download = download_info.value
        assert download.suggested_filename == 'vagas.csv'
        assert _titles('csv', Path(download.path()).read_bytes()) == [f'Vaga {n}' for n in range(301)]
        request = response_info.value.request.post_data_json
        assert request == {'urls': [f'https://example.com/jobs/{n}' for n in range(301)], 'output_version': controller.snapshot()['output_version']}
        browser.close()


def test_dashboard_shows_stale_selection_error_without_download(tmp_path):
    from playwright.sync_api import sync_playwright
    live = datetime.now(timezone.utc)
    with _serve(tmp_path, [_job(1, published_at=live.isoformat(), observed_at=live.isoformat())]) as (base, controller), sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(base)
        page.locator('#jobs-table-body tr').first.wait_for()
        page.locator('#export-button').click()
        (controller.output_dir / 'vagas.jsonl').write_text(json.dumps(_job(2)), encoding='utf-8')
        page.locator('#download-csv').click()
        page.wait_for_function("document.querySelector('#table-export-status')?.textContent.includes('A saída mudou')")
        browser.close()


def test_future_publication_is_not_recent_or_rewarded():
    job = _job(1, published_at=(NOW + timedelta(seconds=1)).isoformat(), match_labels=['FIT:READY', 'FIT_SCORE:2'])
    assert filter_jobs_for_export([job], max_age_days=7, now=NOW) == []
    assert job_score(job, NOW) == 50


@pytest.mark.parametrize('port', ['70000', 'abc', '-1'])
def test_selection_rejects_invalid_url_port_before_local_lookup(tmp_path, port):
    with _serve(tmp_path, [_job(1)]) as (base, controller):
        status, body, _ = _post(base, 'csv', {
            'urls': [f'https://example.com:{port}/jobs/1'],
            'output_version': controller.snapshot()['output_version'],
        })
    assert status == 400
    assert json.loads(body)['error']


def test_browser_future_publication_gets_no_recency_bonus(tmp_path):
    from playwright.sync_api import sync_playwright
    live = datetime.now(timezone.utc)
    future = _job('futura', published_at=(live + timedelta(days=1)).isoformat(),
                  observed_at=live.isoformat(), match_labels=['FIT:READY', 'FIT_SCORE:2'])
    with _serve(tmp_path, [future]) as (base, _), sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(base)
        page.locator('#age-filter').select_option('')
        page.locator('#activity-filter').select_option('all')
        page.locator('#jobs-table-body .title-cell').click()
        assert 'Score 50/100' in page.locator('.job-detail').inner_text()
        browser.close()


def test_browser_score_breakdown_names_each_criterion(tmp_path):
    from playwright.sync_api import sync_playwright
    live = datetime.now(timezone.utc)
    job = _job(
        'detalhada',
        match_labels=['FIT:READY', 'FIT_SCORE:2', 'TECH_MATCH:java', 'SENIORITY_MATCH:junior'],
        published_at=(live - timedelta(days=60)).isoformat(),
        observed_at=live.isoformat(),
    )
    with _serve(tmp_path, [job]) as (base, _), sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(base)
        page.locator('#age-filter').select_option('')
        page.locator('#activity-filter').select_option('all')
        page.locator('#jobs-table-body .title-cell').click()
        text = page.locator('.job-detail').inner_text()
        # 2 pontos de FIT_SCORE batem com os dois rótulos: nada vira "outros critérios".
        assert 'Score 50/100 — Tecnologia +20 · Nível +20 · Mais compatível +10' in text
        browser.close()


@pytest.mark.parametrize('window', ['days', 'custom', 'quick'])
def test_browser_future_publication_is_outside_dated_window(tmp_path, window):
    from playwright.sync_api import sync_playwright
    live = datetime.now(timezone.utc)
    jobs = [_job('atual', published_at=(live - timedelta(hours=1)).isoformat(), observed_at=live.isoformat()),
            _job('futura', published_at=(live + timedelta(days=1)).isoformat(), observed_at=live.isoformat())]
    with _serve(tmp_path, jobs) as (base, _), sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(base)
        page.locator('#age-filter').select_option('')
        page.locator('#activity-filter').select_option('all')
        assert page.locator('#jobs-table-body .job-title').all_inner_texts() == ['Vaga atual', 'Vaga futura']
        if window == 'days':
            page.locator('#age-filter').select_option('7')
        elif window == 'custom':
            page.locator('#age-filter').select_option('custom')
            page.locator('#age-from').fill((live - timedelta(days=1)).date().isoformat())
            page.locator('#age-to').fill((live + timedelta(days=2)).date().isoformat())
        else:
            page.locator('[data-quick="recent"]').click()
        assert page.locator('#jobs-table-body .job-title').all_inner_texts() == ['Vaga atual']
        browser.close()
