from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from job_radar.models import VacancyRecord, WorkplaceModel
from job_radar.output import _record_payload, rewrite_payloads
from job_radar.output_lock import OutputLock
from job_radar.preferences import preferences_from_dict
from job_radar.profiles import activate_profile, save_profile
from job_radar.tracking import TrackingStore
from job_radar.webapp import SearchController, create_server


def _prefs(tech='java'):
    return {'search_terms': [f'{tech} junior'], 'seniority_levels': ['junior'],
            'workplace_models': ['REMOTE'], 'location_scopes': ['brasil'],
            'technologies': [tech]}


@contextmanager
def _api(tmp_path, runner=None):
    output = tmp_path / 'output'
    output.mkdir()
    record = VacancyRecord(source='example', source_job_id='1',
                           canonical_url='https://example.com/job/1',
                           title='Desenvolvedor Python Junior', company='Exemplo',
                           description_summary='Python e SQL', location='Brasil',
                           workplace_model=WorkplaceModel.REMOTE,
                           observed_at='2026-10-01T12:00:00+00:00',
                           match_labels=('FIT:OTHER_STACK', 'LINK:LIVE', 'STATUS:NEW'))
    rewrite_payloads(output, [_record_payload(record)])
    prefpath = tmp_path / 'prefs.json'
    save_profile(prefpath, 'Java', preferences_from_dict(_prefs()))
    activate_profile(prefpath, 'Java')
    save_profile(prefpath, 'Python', preferences_from_dict(_prefs('python')))
    TrackingStore(tmp_path / 'tracking.json').set_status(record.canonical_url, 'SAVED',
                       note='Entrevista marcada', now=datetime(2026, 10, 1, tzinfo=timezone.utc))
    controller = SearchController(output, runner=runner or (lambda *_: 0))
    static = Path(__file__).resolve().parents[1] / 'src/job_radar/web'
    server = create_server('127.0.0.1', 0, controller, static,
                           preferences_path=prefpath, tracking_path=tmp_path / 'tracking.json')
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'

    def request(path, payload=None, method='POST'):
        req = Request(base + path, data=json.dumps(payload or {}).encode(), method=method,
                      headers={'Content-Type': 'application/json'})
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())
    try:
        yield request, controller, base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _snapshot(tmp_path):
    return {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob('*')
            if p.is_file() and not p.name.startswith('.radar')}


@pytest.mark.parametrize(('path', 'payload', 'method'), [
    ('/api/profiles/activate', {'name': 'Python'}, 'POST'),
    ('/api/profiles', {'name': 'Python', 'preferences': _prefs('python')}, 'PUT'),
    ('/api/preferences', _prefs('python'), 'PUT'),
])
def test_apply_profile_reclassifies_preserving_tracking_links_and_observed_at(tmp_path, path, payload, method):
    with _api(tmp_path) as (api, _, _):
        tracking = (tmp_path / 'tracking.json').read_bytes()
        status, body = api(path, payload, method)
        assert status == 200, body
        job = json.loads((tmp_path / 'output/vagas.jsonl').read_text())
        assert 'FIT:READY' in job['match_labels']
        assert {'LINK:LIVE', 'STATUS:NEW'} <= set(job['match_labels'])
        assert job['observed_at'] == '2026-10-01T12:00:00+00:00'
        assert (tmp_path / 'tracking.json').read_bytes() == tracking
        assert body['reapplied']['ready'] == 1
        active_name = 'java' if path == '/api/preferences' else 'python'
        stored = json.loads((tmp_path / f'profiles/{active_name}.json').read_text())
        assert stored['preferences']['technologies'] == ['python']


@pytest.mark.parametrize('busy', ['external', 'collection'])
def test_busy_profile_mutations_leave_all_files_unchanged(tmp_path, busy):
    entered, release = Event(), Event()
    def runner(*_):
        entered.set()
        release.wait(10)
        return 0
    with _api(tmp_path, runner) as (api, controller, _):
        before = _snapshot(tmp_path)
        lock = OutputLock(controller.output_dir)
        if busy == 'external':
            lock.__enter__()
        else:
            controller.start()
            assert entered.wait(2)
        try:
            for path, payload, method in [
                ('/api/profiles/activate', {'name': 'Python'}, 'POST'),
                ('/api/profiles', {'name': 'Novo', 'preferences': _prefs('python')}, 'PUT'),
                ('/api/preferences', _prefs('python'), 'PUT'),
            ]:
                assert api(path, payload, method)[0] == 409
            assert _snapshot(tmp_path) == before
        finally:
            if busy == 'external':
                lock.__exit__(None, None, None)
            release.set()
            controller.wait(2)


@pytest.mark.parametrize('failure', ['classify', 'output', 'preferences', 'profile', 'active'])
@pytest.mark.parametrize('action', ['activate', 'save', 'preferences'])
def test_profile_failures_restore_output_and_metadata(tmp_path, monkeypatch, failure, action):
    with _api(tmp_path) as (api, _, _):
        before = _snapshot(tmp_path)
        def fail(*args, **kwargs):
            if failure == 'output':
                (tmp_path / 'output/vagas.jsonl').write_text('partial')
            raise OSError('Falha injetada de gravação')
        target = {'classify': 'job_radar.reclassify.classify',
                  'output': 'job_radar.output.rewrite_payloads',
                  'preferences': 'job_radar.preferences.save_preferences',
                  'active': 'job_radar.profiles._set_active',
                  'profile': 'job_radar.profiles.save_profile'}[failure]
        monkeypatch.setattr(target, fail)
        if failure == 'preferences':
            monkeypatch.setattr('job_radar.profiles.save_preferences', fail)
        if action == 'activate':
            status, body = api('/api/profiles/activate', {'name': 'Python'})
        elif action == 'save':
            status, body = api('/api/profiles', {'name': 'Novo', 'preferences': _prefs('python')}, 'PUT')
        else:
            status, body = api('/api/preferences?reapply=1', _prefs('python'), 'PUT')
        assert status >= 400, body
        assert _snapshot(tmp_path) == before


def test_ui_primary_preset_preserves_custom_terms_and_applies_profile(tmp_path):
    from playwright.sync_api import sync_playwright

    with _api(tmp_path) as (_, _, base):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(base)
            page.get_by_role('button', name='Configurar busca').click()
            page.locator('#search-terms').fill('minha consulta exclusiva')
            page.locator('#stack-chips .chip[data-stack="python"]').click()
            page.get_by_role('button', name='Preencher sugestões').click()
            page.wait_for_function("() => document.querySelector('#primary-technologies')?.value.includes('python')", timeout=2000)
            assert 'minha consulta exclusiva' in page.locator('#search-terms').input_value()
            assert 'python junior' in page.locator('#search-terms').input_value()
            page.locator('#primary-technologies-entry').fill('java')
            page.locator('#primary-technologies-entry').press('Enter')
            assert 'minha consulta exclusiva' in page.locator('#search-terms').input_value()
            assert 'java junior' in page.locator('#search-terms').input_value()
            page.get_by_role('button', name='Salvar configurações', exact=True).click()
            page.get_by_text('Perfil aplicado às vagas salvas.').wait_for()
            assert 'FIT:READY' in json.loads((tmp_path / 'output/vagas.jsonl').read_text())['match_labels']
            browser.close()


def test_first_profile_failure_restores_previously_absent_files(tmp_path, monkeypatch):
    with _api(tmp_path) as (api, _, _):
        (tmp_path / 'prefs.json').unlink()
        for path in (tmp_path / 'profiles').glob('*.json'):
            path.unlink()
        (tmp_path / 'output/vagas.jsonl').unlink()
        (tmp_path / 'output/vagas.csv').unlink()
        before = _snapshot(tmp_path)
        def fail(*args):
            raise OSError('Falha depois de criar preferências e perfil')
        monkeypatch.setattr('job_radar.profiles._set_active', fail)
        assert api('/api/profiles', {'name': 'Novo', 'preferences': _prefs()}, 'PUT')[0] == 400
        assert _snapshot(tmp_path) == before


def test_corrupt_tracking_prevents_profile_rewrite(tmp_path):
    with _api(tmp_path) as (api, _, _):
        (tmp_path / 'tracking.json').write_bytes(b'{invalid json')
        before = _snapshot(tmp_path)
        assert api('/api/profiles/activate', {'name': 'Python'})[0] == 400
        assert _snapshot(tmp_path) == before


def test_terms_builder_uses_explicit_primary_over_complementary_technologies(tmp_path):
    from playwright.sync_api import sync_playwright

    with _api(tmp_path) as (_, _, base):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(base)
            page.get_by_role('button', name='Configurar busca').click()
            page.locator('#primary-technologies-entry').fill('python')
            page.locator('#primary-technologies-entry').press('Enter')
            page.locator('#terms-builder-toggle').click()
            page.locator('#terms-groups h4').first.wait_for()
            assert 'Python' in page.locator('#terms-groups h4').all_text_contents()
            assert 'Java / Spring' not in page.locator('#terms-groups h4').all_text_contents()
            browser.close()


def test_missing_primary_is_warning_not_satisfied_criterion(tmp_path):
    from playwright.sync_api import sync_playwright

    with _api(tmp_path) as (_, _, base):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(base)
            facts = page.evaluate("""() => [...detailRow({match_labels: [
                "FIT:AMBIGUOUS", "PRIMARY_TECH_MISSING:Java", "TECH_MATCH:SQL"
            ]}).querySelectorAll('.detail-facts li')].map(li => li.textContent)""")
            criteria = next(fact for fact in facts if fact.startswith('Critérios atendidos'))
            assert 'Tecnologia: SQL' in criteria
            assert 'principal' not in criteria.lower()
            assert any('Atenção' in fact and 'stack principal não confirmada' in fact for fact in facts)
            browser.close()


def test_ui_save_keeps_region_rule_and_shows_it(tmp_path):
    """Modalidade por região ainda não tem campo no formulário: salvar não pode apagá-la."""
    from playwright.sync_api import sync_playwright

    regra = {"HYBRID": ["sp"], "ONSITE": ["sao-carlos-sp", "florianopolis-sc"]}
    with _api(tmp_path) as (_, _, base):
        prefs_path = tmp_path / 'prefs.json'
        prefs = json.loads(prefs_path.read_text(encoding='utf-8'))
        prefs['workplace_location_scopes'] = regra
        prefs_path.write_text(json.dumps(prefs), encoding='utf-8')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(base)
            page.get_by_role('button', name='Configurar busca').click()
            nota = page.locator('#region-rules')
            nota.wait_for(state='visible')
            assert 'híbrido só em sp' in nota.inner_text()
            page.get_by_role('button', name='Salvar configurações', exact=True).click()
            page.get_by_text('Perfil aplicado às vagas salvas.').wait_for()
            browser.close()
        assert json.loads(prefs_path.read_text(encoding='utf-8'))['workplace_location_scopes'] == regra
