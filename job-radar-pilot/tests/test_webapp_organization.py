"""Histórico, publicação e sincronização exercitados pelo painel real."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from job_radar.tracking import TrackingStore
from job_radar.webapp import SearchController, create_server, filter_jobs_for_export

NOW = datetime.now(timezone.utc)
WEB = Path(__file__).resolve().parents[1] / 'src/job_radar/web'


def job(i, days=2, **extra):
    return {'title': f'Java {i}', 'company': 'Exemplo', 'source': 'example',
            'canonical_url': f'https://example.com/{i}', 'match_labels': ['FIT:READY'],
            'published_at': (NOW - timedelta(days=days)).isoformat(),
            'observed_at': NOW.isoformat(), **extra}


@pytest.fixture
def radar(tmp_path):
    output = tmp_path / 'output'
    output.mkdir()
    jobs = [job(1), job(2, 90, application_deadline=(NOW - timedelta(days=80)).isoformat()),
            job(3, published_at=None, observed_at=None),
            job(4, application_deadline=(NOW - timedelta(days=1)).isoformat())]
    (output / 'vagas.jsonl').write_text(''.join(json.dumps(j) + '\n' for j in jobs))
    tracking = TrackingStore(tmp_path / 'tracking.json')
    tracking.set_status('https://example.com/2', 'SAVED', now=NOW)
    controller = SearchController(output, runner=lambda *_: 0)
    server = create_server('127.0.0.1', 0, controller, WEB, tracking_path=tmp_path / 'tracking.json')
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', controller, tracking, jobs
    server.shutdown()
    server.server_close()
    thread.join(2)


def api(base, path, payload=None):
    request = Request(base + path, data=json.dumps(payload).encode() if payload is not None else None,
                      headers={'Content-Type': 'application/json'}, method='PUT' if payload is not None else 'GET')
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def test_state_synchronizes_tracking_without_resending_jobs(radar):
    base, _, store, _ = radar
    _, first = api(base, '/api/state')
    assert first['tracking']['https://example.com/2']['status'] == 'SAVED'
    store.set_status('https://example.com/1', 'APPLIED', now=NOW)
    _, changed = api(base, f"/api/state?since={first['output_version']}&tracking_since={first['tracking_version']}")
    assert changed['unchanged']
    assert changed['tracking']['https://example.com/1']['status'] == 'APPLIED'
    assert changed['tracking_version'] != first['tracking_version']
    _, same = api(base, f"/api/state?tracking_since={changed['tracking_version']}")
    assert 'tracking' not in same


def test_state_corrupt_tracking_does_not_publish_empty_snapshot(radar):
    base, _, store, _ = radar
    store._path.write_text('{quebrado')
    status, payload = api(base, '/api/state')
    assert status == 500
    assert 'error' in payload
    assert 'tracking_version' not in payload


def test_tracking_rejects_url_removed_since_screen(radar):
    base, controller, store, _ = radar
    (controller.output_dir / 'vagas.jsonl').write_text('')
    status, payload = api(base, '/api/tracking', {'url': 'https://example.com/1', 'status': 'SAVED'})
    assert status == 409
    assert 'recarreg' in payload['error'].lower()
    assert 'https://example.com/1' not in store.load()


def test_progress_reports_finished_and_total(radar):
    _, controller, _, _ = radar
    controller._on_line('PROGRESS: 3/25 portais')
    assert controller.snapshot()['progress'] == {'finished': 3, 'total': 25}


def test_export_period_is_independent_of_closed_activity():
    closed = job(4, application_deadline=(NOW - timedelta(days=1)).isoformat())
    assert filter_jobs_for_export([closed], max_age_days=30, now=NOW) == [closed]
    assert filter_jobs_for_export([closed], match='ready', max_age_days=30, now=NOW) == []


@pytest.fixture
def page(radar):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        # Impede o seed age=any do conftest e exercita os defaults de produção.
        page.add_init_script("sessionStorage.setItem('age-any-seeded', '1')")
        page.goto(radar[0])
        page.wait_for_function("outputVersion !== ''")
        yield page
        browser.close()


@pytest.mark.production_filters
def test_fresh_dashboard_uses_production_age_and_activity_defaults(radar):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(radar[0])
            page.wait_for_function("outputVersion !== ''")
            assert page.evaluate("sessionStorage.getItem('age-any-seeded')") is None
            assert page.locator('#age-filter').input_value() == '30'
            assert page.locator('#activity-filter').input_value() == 'active'
            assert page.locator('#jobs-table-body .job-title').all_inner_texts() == ['Java 1']
        finally:
            browser.close()


def test_saved_shortcut_exposes_old_closed_history_and_allows_refinement(page):
    assert page.locator('#age-filter').input_value() == '30'
    assert page.locator('#activity-filter').input_value() == 'active'
    page.locator('#text-filter').fill('impossível')
    page.locator('#funnel').get_by_role('button', name='1 salva', exact=True).click()
    assert page.locator('#jobs-table-body .job-title').all_inner_texts() == ['Java 2']
    assert page.locator('#age-filter').input_value() == ''
    assert page.locator('#activity-filter').input_value() == 'all'
    page.locator('#text-filter').fill('impossível')
    assert page.locator('#jobs-table-body .job-title').count() == 0


def test_second_tab_tracking_updates_panel_and_keeps_status_focus(page, radar):
    from playwright.sync_api import expect
    second = page.context.new_page()
    second.goto(radar[0])
    second.wait_for_function("outputVersion !== ''")
    first_select = page.get_by_label('Acompanhamento da vaga Java 1')
    first_select.focus()
    second.get_by_label('Acompanhamento da vaga Java 1').select_option('APPLIED')
    page.evaluate('refreshState()')
    expect(first_select).to_have_value('APPLIED')
    expect(first_select).to_be_focused()
    expect(page.locator('#funnel')).to_contain_text('1 aplicada')


def test_details_focus_survives_render(page):
    from playwright.sync_api import expect
    cell = page.locator('.title-cell', has_text='Java 1')
    cell.focus()
    cell.press('Enter')
    expect(cell).to_be_focused()
    expect(cell).to_have_attribute('aria-expanded', 'true')


def test_undated_action_exposes_unknown_jobs_and_closed_period_remains_independent(page):
    page.locator('#show-undated').click()
    assert page.locator('#jobs-table-body .job-title').all_inner_texts() == ['Java 3']
    assert page.locator('#activity-filter').input_value() == 'all'
    page.locator('#age-filter').select_option('30')
    page.locator('#activity-filter').select_option('closed')
    assert page.locator('#jobs-table-body .job-title').all_inner_texts() == ['Java 4']


def test_source_selection_restores_only_enabled_codes(page):
    from playwright.sync_api import expect
    page.route('**/api/sources', lambda route: route.fulfill(json={'sources': [
        {'code': 'one', 'tech_focus': True}, {'code': 'two', 'tech_focus': False}]}))
    page.evaluate("localStorage.setItem('radar.selectedSources', JSON.stringify(['two', 'removed']))")
    page.locator('#sources-button').click()
    expect(page.locator('#sources-list input')).to_have_count(2)
    assert page.locator('#sources-list input:checked').evaluate_all('(inputs) => inputs.map(i => i.value)') == ['two']
    page.locator('#sources-list input[value="one"]').check()
    page.reload()
    page.locator('#sources-button').click()
    expect(page.locator('#sources-list input:checked')).to_have_count(2)


def test_verification_describes_pages_and_preparation(page):
    page.evaluate("dashboardState.verification = {status:'RUNNING',checked:0,total:0}; renderRunState()")
    assert 'Preparando' in page.locator('#verification-status').inner_text()
    page.evaluate("dashboardState.verification = {status:'DONE',counts:{'LINK:LIVE':1,'LINK:DEAD':0,'LINK:UNKNOWN':0}}; renderRunState()")
    text = page.locator('#verification-status').inner_text()
    assert '1 página' in text
    assert 'ativa(s)' not in text
    assert 'prazo' in text


def test_exact_export_contains_entire_filtered_order_beyond_first_page(page):
    page.evaluate("""() => { const template = dashboardState.jobs[0];
      dashboardState.jobs = Array.from({length:325}, (_,i) => ({...template,
        title:`Java ${i}`,canonical_url:`https://example.com/${i}`})); renderTable(); }""")
    assert page.locator('#jobs-table-body .job-title').count() < 325
    captured = []
    def export(route):
        captured.append(route.request.post_data_json)
        route.fulfill(status=200, body='csv', headers={'Content-Type':'text/csv'})
    page.route('**/api/export/csv', export)
    page.evaluate("downloadTableExport('csv')")
    assert captured[0]['urls'] == [f'https://example.com/{i}' for i in range(325)]
    assert captured[0]['output_version']


@pytest.mark.parametrize('raw', ['{quebrado', '{"bad":true}', '[null]'])
def test_malformed_source_memory_uses_enabled_defaults(page, raw):
    from playwright.sync_api import expect
    page.route('**/api/sources', lambda route: route.fulfill(json={'sources': [
        {'code': 'one', 'tech_focus': True}, {'code': 'two', 'tech_focus': False}]}))
    page.evaluate("raw => localStorage.setItem('radar.selectedSources', raw)", raw)
    page.locator('#sources-button').click()
    expect(page.locator('#sources-list input:checked')).to_have_count(2)


def test_collection_progress_names_total_and_read_records(page, radar):
    _, controller, _, _ = radar
    controller._status = 'RUNNING'
    controller._on_line('one: SUCCESS; pages=2; cards=7; records=5; stop=EXHAUSTED')
    controller._on_line('PROGRESS: 1/25 portais')
    page.evaluate('refreshState()')
    text = page.locator('#live-status').inner_text()
    assert '1 de 25 portais' in text
    assert '5 vagas lidas' in text
    assert 'salvas ao concluir' in text


def test_saved_history_keeps_personal_marks_even_outside_ti(page, radar):
    base, controller, store, jobs = radar
    outside = job(5, 90, match_labels=['FIT:EXCLUDE', 'RELEVANCE:OFF_TOPIC'])
    store.set_status(outside['canonical_url'], 'SAVED', now=NOW)
    (controller.output_dir / 'vagas.jsonl').write_text(''.join(json.dumps(j) + '\n' for j in [*jobs, outside]))
    page.evaluate('refreshState()')
    page.locator('#funnel').get_by_role('button', name='2 salvas', exact=True).click()
    assert sorted(page.locator('#jobs-table-body .job-title').all_inner_texts()) == ['Java 2', 'Java 5']


def test_saved_export_keeps_personal_marks_even_outside_ti():
    outside = job(5, 90, match_labels=['FIT:EXCLUDE', 'RELEVANCE:OFF_TOPIC'])
    assert filter_jobs_for_export([outside], tracked='saved', tracking={
        outside['canonical_url']: {'status': 'SAVED'}}) == [outside]


def test_own_tracking_change_keeps_status_keyboard_focus(page):
    from playwright.sync_api import expect
    control = page.get_by_label('Acompanhamento da vaga Java 1')
    control.focus()
    control.select_option('SAVED')
    expect(control).to_have_value('SAVED')
    expect(control).to_be_focused()


def test_tracking_change_keeps_focus_even_when_the_server_is_slow(page):
    """Regressão da instabilidade do CI (10/10/2026): desabilitar o <select> focado durante o
    fetch faz o Chromium mover o foco para o <body> no quadro seguinte. Com resposta lenta o
    foco se perdia sempre; com resposta rápida, às vezes. O atraso aqui torna isso determinístico."""
    import time

    from playwright.sync_api import expect

    def slow(route):
        time.sleep(0.3)
        route.continue_()

    page.route("**/api/tracking", slow)
    control = page.get_by_label('Acompanhamento da vaga Java 1')
    control.focus()
    control.select_option('SAVED')
    expect(control).to_have_value('SAVED')
    expect(control).to_be_focused()
