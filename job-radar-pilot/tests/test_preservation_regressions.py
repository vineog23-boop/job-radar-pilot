from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import multiprocessing
from pathlib import Path
from threading import Event, Thread

import pytest

from job_radar import cli
from job_radar.models import CollectionStatus, SourceRunResult, VacancyRecord
from job_radar.output import OutputError, write_outputs
from job_radar.pipeline import PipelineResult
from job_radar.tracking import TrackingStore

NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
OLD = '2026-09-01T12:00:00+00:00'
URL = 'https://example.com/jobs/1'


def record(url=URL, *, source='programathor', title='Java Junior'):
    return VacancyRecord(source=source, source_job_id=None, company="Acme", canonical_url=url, title=title,
                         observed_at=OLD, match_labels=('FIT:READY',))


def result(records=(), *, status=CollectionStatus.SUCCESS, source='programathor'):
    return PipelineResult(started_at=NOW.isoformat(), finished_at=NOW.isoformat(),
                          records=tuple(records), ambiguous=(),
                          source_results=(SourceRunResult(source, status, records=tuple(records)),),
                          raw_record_count=len(records), duplicate_count=0)


def jobs(output):
    return [json.loads(line) for line in (output / 'vagas.jsonl').read_text().splitlines()]


def test_saved_old_job_survives_empty_full_collection(tmp_path):
    write_outputs(result((record(),)), tmp_path)
    before = jobs(tmp_path)[0]
    write_outputs(result(status=CollectionStatus.EMPTY), tmp_path,
                  keep_urls={URL}, prune=True, max_age_days=1)
    assert jobs(tmp_path) == [before]
    assert jobs(tmp_path)[0]['observed_at'] == OLD


@pytest.mark.parametrize('status', [CollectionStatus.BLOCKED, CollectionStatus.PARTIAL])
def test_incomplete_source_preserves_old_jobs_without_partial_merge(tmp_path, status):
    write_outputs(result((replace(record(), published_at=OLD, match_labels=('FIT:EXCLUDE',)),)), tmp_path)
    before = jobs(tmp_path)[0]
    write_outputs(result(status=status), tmp_path, prune=True, max_age_days=1)
    assert jobs(tmp_path) == [before]


def test_success_replaces_only_untracked_jobs_and_new_url_wins(tmp_path):
    old = record()
    untracked = record('https://example.com/jobs/2')
    write_outputs(result((old, untracked)), tmp_path)
    new = replace(old, title='Java Junior atualizada', observed_at=NOW.isoformat())
    write_outputs(result((new,)), tmp_path, keep_urls={URL})
    assert [(job['canonical_url'], job['title'], job['observed_at']) for job in jobs(tmp_path)] == [
        (URL, 'Java Junior atualizada', NOW.isoformat())]
    report = json.loads((tmp_path / 'relatorio-execucao.json').read_text())
    assert report['totals']['unique'] == 1
    assert len(report['sources']) == 1


@pytest.mark.parametrize('merge', [False, True])
@pytest.mark.parametrize('corrupt', ['{quebrado', '[]', '{"source":"programathor"}'])
def test_corrupt_previous_jsonl_refuses_every_overwrite(tmp_path, merge, corrupt):
    write_outputs(result((record(),)), tmp_path)
    with (tmp_path / 'vagas.jsonl').open('a') as stream:
        stream.write(corrupt + '\n')
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    with pytest.raises(OutputError):
        write_outputs(result(), tmp_path, merge_unrefreshed=merge)
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()} == before


def test_incomplete_source_keeps_discarded_basket_without_duplicates(tmp_path):
    excluded = replace(record(), match_labels=('FIT:EXCLUDE',))
    write_outputs(result((excluded,)), tmp_path, prune=True)
    write_outputs(result(status=CollectionStatus.BLOCKED), tmp_path, prune=True)
    basket = tmp_path / 'vagas-descartadas-na-coleta.jsonl'
    assert [json.loads(line)['canonical_url'] for line in basket.read_text().splitlines()] == [URL]


def test_tracking_threads_preserve_both_urls_and_notes(tmp_path):
    path = tmp_path / 'tracking.json'
    writing = Event()
    second_done = Event()
    failures = []

    class PausedStore(TrackingStore):
        def _write(self, entries):
            writing.set()
            second_done.wait(.3)
            super()._write(entries)

    def first():
        try:
            PausedStore(path).set_status(URL, 'SAVED', now=NOW, note='Primeira nota')
        except Exception as error:
            failures.append(error)

    def second():
        try:
            TrackingStore(path).set_status('https://example.com/jobs/2', 'APPLIED',
                                           now=NOW, note='Segunda nota')
        except Exception as error:
            failures.append(error)
        finally:
            second_done.set()

    one = Thread(target=first)
    two = Thread(target=second)
    one.start()
    assert writing.wait(5)
    two.start()
    one.join(5)
    two.join(5)
    assert not one.is_alive() and not two.is_alive()
    assert failures == []
    entries = TrackingStore(path).load()
    assert {url: value['note'] for url, value in entries.items()} == {
        URL: 'Primeira nota', 'https://example.com/jobs/2': 'Segunda nota'}


def _tracking_process(path, writing, second_done, paused):
    class PausedStore(TrackingStore):
        def _write(self, entries):
            writing.set()
            second_done.wait(.5)
            super()._write(entries)

    store = PausedStore(Path(path)) if paused else TrackingStore(Path(path))
    store.set_status(URL if paused else 'https://example.com/jobs/2', 'SAVED', now=NOW,
                     note='Primeira nota' if paused else 'Segunda nota')
    if not paused:
        second_done.set()


def test_tracking_processes_preserve_both_urls_and_notes(tmp_path):
    context = multiprocessing.get_context('spawn')
    writing, second_done = context.Event(), context.Event()
    path = tmp_path / 'tracking.json'
    one = context.Process(target=_tracking_process, args=(str(path), writing, second_done, True))
    two = context.Process(target=_tracking_process, args=(str(path), writing, second_done, False))
    one.start()
    try:
        assert writing.wait(10)
        two.start()
        one.join(10)
        two.join(10)
        assert one.exitcode == two.exitcode == 0
        assert {url: value['note'] for url, value in TrackingStore(path).load().items()} == {
            URL: 'Primeira nota', 'https://example.com/jobs/2': 'Segunda nota'}
    finally:
        for process in (one, two):
            if process.is_alive():
                process.terminate()
                process.join(5)


@pytest.mark.parametrize('corrupt_tracking', [False, True])
def test_cli_rechecks_tracking_after_collection(tmp_path, monkeypatch, corrupt_tracking):
    output = tmp_path / 'out'
    old = replace(record(), match_labels=('FIT:EXCLUDE',))
    write_outputs(result((old,)), output)
    tracking = TrackingStore(tmp_path / 'tracking.json')
    monkeypatch.setattr(cli, 'TrackingStore', lambda: tracking)

    def collect(*args, **kwargs):
        if corrupt_tracking:
            tracking._path.write_text('{corrompido')
        else:
            tracking.set_status(URL, 'SAVED', now=NOW)
        return result(status=CollectionStatus.EMPTY)

    monkeypatch.setattr(cli, '_run_pipeline', collect)
    assert cli.main(['collect', '--no-history', '--no-export', '--output', str(output)]) == 0
    assert [job['canonical_url'] for job in jobs(output)] == [URL]


def test_success_carries_missing_tracked_job_but_replaces_untracked(tmp_path):
    write_outputs(result((record(), record('https://example.com/jobs/2'))), tmp_path)
    write_outputs(result((record('https://example.com/jobs/3'),)), tmp_path, keep_urls={URL})
    assert [job['canonical_url'] for job in jobs(tmp_path)] == ['https://example.com/jobs/3', URL]


def test_new_url_wins_even_when_previous_source_is_unrefreshed(tmp_path):
    write_outputs(result((record(source='antiga'),), source='antiga'), tmp_path)
    write_outputs(result((record(title='Atualizada'),)), tmp_path, merge_unrefreshed=True)
    assert [(job['canonical_url'], job['title']) for job in jobs(tmp_path)] == [(URL, 'Atualizada')]


def test_cli_serializes_final_tracking_snapshot_with_publication(tmp_path, monkeypatch):
    output = tmp_path / 'out'
    write_outputs(result((record(),)), output)
    tracking = TrackingStore(tmp_path / 'tracking.json')
    tracking.set_status(URL, 'SAVED', now=NOW)
    monkeypatch.setattr(cli, 'TrackingStore', lambda: tracking)
    monkeypatch.setattr(cli, '_run_pipeline', lambda *args, **kwargs: result(status=CollectionStatus.EMPTY))
    updated = Event()
    failures = []
    original_write = cli.write_outputs
    threads = []

    def update():
        try:
            TrackingStore(tracking._path).set_status(URL, 'APPLIED', now=NOW, note='Nota simultânea')
        except Exception as error:
            failures.append(error)
        finally:
            updated.set()

    def publish(*args, **kwargs):
        thread = Thread(target=update)
        threads.append(thread)
        thread.start()
        assert not updated.wait(.3), 'Tracking mudou entre o snapshot final e a publicação'
        return original_write(*args, **kwargs)

    monkeypatch.setattr(cli, 'write_outputs', publish)
    try:
        assert cli.main(['collect', '--no-history', '--no-export', '--output', str(output)]) == 0
    finally:
        for thread in threads:
            thread.join(5)
    assert failures == []
    assert updated.is_set()
    assert tracking.load()[URL]['note'] == 'Nota simultânea'
    assert jobs(output)[0]['canonical_url'] == URL


@pytest.mark.parametrize('status', [CollectionStatus.SUCCESS, CollectionStatus.EMPTY])
@pytest.mark.parametrize('during_collection', [False, True])
@pytest.mark.parametrize(
    ('broken_url', 'broken_entry'),
    [
        (URL, ['registro danificado']),
        (URL, {'status': 'UNKNOWN'}),
        ('javascript:alert(1)', {'status': 'SAVED'}),
        (URL, {'status': 'SAVED', 'note': False}),
    ],
)
def test_full_collection_preserves_all_payloads_with_structurally_corrupt_tracking(
    tmp_path, monkeypatch, capsys, status, during_collection, broken_url, broken_entry,
):
    output = tmp_path / 'out'
    previous = (
        replace(record(), match_labels=('FIT:EXCLUDE',), published_at=OLD),
        replace(record('https://example.com/jobs/2'), match_labels=('FIT:EXCLUDE',)),
    )
    write_outputs(result(previous), output)
    before = {job['canonical_url']: job for job in jobs(output)}
    path = tmp_path / 'tracking.json'
    tracking = TrackingStore(path)
    corrupt = json.dumps({'version': 1, 'jobs': {
        'https://example.com/jobs/2': {'status': 'SAVED'}, broken_url: broken_entry,
    }})
    if not during_collection:
        path.write_text(corrupt, encoding='utf-8')
    monkeypatch.setattr(cli, 'TrackingStore', lambda: tracking)

    def collect(*args, **kwargs):
        if during_collection:
            path.write_text(corrupt, encoding='utf-8')
        new = replace(record('https://example.com/jobs/3'), match_labels=('FIT:EXCLUDE',))
        return result((new,) if status == CollectionStatus.SUCCESS else (), status=status)

    monkeypatch.setattr(cli, '_run_pipeline', collect)
    assert cli.main(['collect', '--no-history', '--no-export', '--max-age-days', '1',
                     '--output', str(output)]) == 0
    after = {job['canonical_url']: job for job in jobs(output)}
    assert {url: after.get(url) for url in before} == before
    assert len(after) == (3 if status == CollectionStatus.SUCCESS else 2)
    assert path.read_bytes() == corrupt.encode('utf-8')
    assert 'acompanhamento' in capsys.readouterr().err
