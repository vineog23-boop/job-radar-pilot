"""Uma lista curta para decidir, candidaturas preservadas e exportação do recorte."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from threading import Thread
from xml.etree import ElementTree
import zipfile

import pytest

from job_radar.webapp import SearchController, create_server

WEB = Path(__file__).resolve().parents[1] / 'src/job_radar/web'


@pytest.fixture
def focused_dashboard(tmp_path):
    now = datetime.now(timezone.utc)
    live = ['LINK:LIVE', 'LINK_CHECK_METHOD:JOB_DETAIL_V2', f'LINK_CHECKED_AT:{now.isoformat()}']
    def job(number, title, fit='READY', role='DEVELOPMENT', confirmed=True, **extra):
        return {'title': title, 'company': 'Exemplo', 'source': 'example',
                'canonical_url': f'https://example.com/jobs/{number}',
                'workplace_model': 'REMOTE', 'location': 'Brasil', 'observed_at': now.isoformat(),
                'published_at': (now - timedelta(days=2)).isoformat(),
                'description_summary': 'Desenvolvimento de aplicações e APIs.',
                'match_labels': [f'FIT:{fit}', 'FIT_SCORE:4', f'ROLE:{role}', 'SENIORITY_MATCH:junior',
                                 * (live if confirmed else [])], **extra}
    jobs = [job(1, 'Desenvolvedor Java Junior'),
            job(2, 'Estágio em Inteligência Artificial', role='AI'),
            job(3, 'Desenvolvedor Spring Junior — conferir', confirmed=False),
            job(4, 'Suporte Java Junior', fit='EXCLUDE', role='OTHER'),
            job(5, 'Candidatura Java antiga', published_at=(now - timedelta(days=45)).isoformat(), application_deadline=(now - timedelta(days=1)).isoformat()),
            job(6, 'Desenvolvedor .NET Senior', fit='EXCLUDE')]
    output = tmp_path / 'output'; output.mkdir()
    (output / 'vagas.jsonl').write_text(''.join(json.dumps(j) + '\n' for j in jobs))
    tracking = tmp_path / 'user' / 'tracking.json'; tracking.parent.mkdir()
    tracking.write_text(json.dumps({'version': 1, 'jobs': {jobs[4]['canonical_url']: {
        'status': 'APPLIED', 'applied_at': (now-timedelta(days=45)).isoformat(), 'note': 'Aguardar resposta'}}}))
    server = create_server('127.0.0.1', 0, SearchController(output, runner=lambda *_: 0), WEB,
                           preferences_path=tmp_path/'user'/'prefs.json', tracking_path=tracking)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/', tracking
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


@pytest.mark.production_filters
def test_focused_journey_separates_verified_jobs_review_and_old_applications(focused_dashboard):
    from playwright.sync_api import expect, sync_playwright
    base, tracking = focused_dashboard
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(base)
        titles = page.locator('#jobs-table-body .job-title')
        expect(titles).to_have_text(['Desenvolvedor Java Junior', 'Estágio em Inteligência Artificial'])
        expect(page.get_by_role('button', name='Configurar busca', exact=True)).not_to_be_visible()
        with page.expect_download() as download:
            page.get_by_role('button', name='Exportar resultados', exact=False).click()
        with zipfile.ZipFile(download.value.path()) as workbook:
            sheet = ElementTree.fromstring(workbook.read('xl/worksheets/sheet1.xml'))
        ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        assert len(sheet.findall('.//m:row', ns)) == 3
        page.locator('[data-workspace=review]').click()
        expect(titles).to_have_text(['Desenvolvedor Spring Junior — conferir'])
        page.locator('#age-filter').select_option('7')
        page.get_by_role('button', name='Candidaturas', exact=False).click()
        page.reload()
        expect(titles).to_have_text(['Candidatura Java antiga'])
        titles.first.click()
        note = page.get_by_label('Observação da candidatura')
        expect(note).to_have_value('Aguardar resposta')
        note.fill('Retornar na próxima semana')
        page.get_by_role('button', name='Salvar observação', exact=True).click()
        expect(page.get_by_text('Observação salva.', exact=True)).to_be_visible()
        assert next(iter(json.loads(tracking.read_text())['jobs'].values()))['note'] == 'Retornar na próxima semana'
        page.get_by_role('button', name='Oportunidades', exact=False).click()
        expect(titles).to_have_text(['Desenvolvedor Java Junior', 'Estágio em Inteligência Artificial'])
        page.reload()
        expect(titles).to_have_count(2)
        browser.close()


@pytest.mark.production_filters
def test_focus_settings_can_be_edited_without_losing_the_search_policy(focused_dashboard):
    from playwright.sync_api import expect, sync_playwright
    base, _ = focused_dashboard
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(base)
        page.get_by_role('button', name='Configurações', exact=True).click()
        page.get_by_role('button', name='Configurar busca', exact=True).click()
        development = page.get_by_label('Somente desenvolvimento de software')
        expect(development).to_be_visible()
        development.check()
        page.get_by_label('Estágios em Inteligência Artificial', exact=True).check()
        page.get_by_label('Estágios full stack', exact=True).check()
        page.get_by_role('button', name='Salvar configurações', exact=True).click()
        expect(page.locator('#preferences-status')).to_contain_text('Configurações salvas')
        page.reload()
        page.get_by_role('button', name='Configurar busca', exact=True).click()
        expect(development).to_be_checked()
        expect(page.get_by_label('Estágios em Inteligência Artificial', exact=True)).to_be_checked()
        expect(page.get_by_label('Estágios full stack', exact=True)).to_be_checked()
        browser.close()
