from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from job_radar.tracking import TrackingError, TrackingStore, tracking_path

NOW = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
URL = "https://example.com/vagas/1"


def test_empty_store_returns_no_entries(tmp_path: Path) -> None:
    assert TrackingStore(tmp_path / "t.json").load() == {}


def test_set_status_persists_and_can_be_cleared(tmp_path: Path) -> None:
    store = TrackingStore(tmp_path / "t.json")

    store.set_status(URL, "APPLIED", now=NOW, note="  Enviei pelo Gupy  ")

    reloaded = TrackingStore(tmp_path / "t.json").load()
    assert reloaded == {
        URL: {
            "status": "APPLIED",
            "updated_at": NOW.isoformat(),
            "applied_at": NOW.isoformat(),
            "note": "Enviei pelo Gupy",
        }
    }

    store.set_status(URL, None, now=NOW)
    assert store.load() == {}


@pytest.mark.parametrize(
    ("url", "status"),
    [
        ("javascript:alert(1)", "SAVED"),
        ("ftp://example.com/x", "SAVED"),
        ("https://" + "a" * 2100, "SAVED"),
        (URL, "HIRED"),
    ],
)
def test_set_status_rejects_invalid_input(tmp_path: Path, url: str, status: str) -> None:
    with pytest.raises(TrackingError):
        TrackingStore(tmp_path / "t.json").set_status(url, status, now=NOW)


def test_note_is_limited(tmp_path: Path) -> None:
    with pytest.raises(TrackingError):
        TrackingStore(tmp_path / "t.json").set_status(URL, "SAVED", now=NOW, note="x" * 501)


def test_corrupted_file_is_not_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "t.json"
    path.write_text("{quebrado", encoding="utf-8")

    with pytest.raises(TrackingError):
        TrackingStore(path).set_status(URL, "SAVED", now=NOW)
    assert path.read_text(encoding="utf-8") == "{quebrado"


def test_default_path_lives_under_local_app_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert tracking_path() == tmp_path / "JobRadar" / "tracking.json"


@pytest.mark.parametrize(
    ('broken_url', 'broken_entry'),
    [
        (URL, ['registro danificado']),
        (URL, {'status': 'UNKNOWN'}),
        ('javascript:alert(1)', {'status': 'SAVED'}),
        (URL, {'status': 'SAVED', 'note': False}),
        (URL, {'status': 'SAVED', 'saved_at': 123}),
        (URL, {'status': ['SAVED']}),
        ('https://[endereco-invalido', {'status': 'SAVED'}),
    ],
)
def test_structurally_corrupt_tracking_refuses_load_and_rewrite(
    tmp_path, broken_url, broken_entry,
):
    import json

    path = tmp_path / 'tracking.json'
    path.write_text(json.dumps({'version': 1, 'jobs': {
        'https://example.com/vagas/valida': {'status': 'APPLIED', 'note': 'Nota válida'},
        broken_url: broken_entry,
    }}), encoding='utf-8')
    before = path.read_bytes()
    store = TrackingStore(path)
    with pytest.raises(TrackingError):
        store.load()
    with pytest.raises(TrackingError):
        store.set_status('https://example.com/vagas/nova', 'SAVED', now=NOW)
    assert path.read_bytes() == before


def test_presence_validation_and_write_hold_same_transaction(tmp_path):
    """A publicação concorrente espera até SAVED já estar persistido."""
    from threading import Event, Thread

    store = TrackingStore(tmp_path / 'tracking.json')
    validation = Event()
    started = Event()
    observed = []

    def publish():
        started.set()
        with TrackingStore(store._path).transaction():
            observed.append(TrackingStore(store._path).load())

    def validate(url):
        assert url == URL
        validation.set()
        worker.start()
        assert started.wait(2)
        assert observed == []

    worker = Thread(target=publish)
    entries = store.set_status(URL, 'SAVED', now=NOW, validate=validate)
    worker.join(2)
    assert not worker.is_alive()
    assert validation.is_set()
    assert observed == [entries]
    assert observed[0][URL]['status'] == 'SAVED'


def test_failed_presence_validation_does_not_write(tmp_path):
    store = TrackingStore(tmp_path / 'tracking.json')
    store.set_status(URL, 'APPLIED', now=NOW)
    before = store._path.read_bytes()

    def absent(url):
        raise TrackingError('Vaga removida')

    with pytest.raises(TrackingError, match='Vaga removida'):
        store.set_status(URL, 'SAVED', now=NOW, validate=absent)
    assert store._path.read_bytes() == before


def test_snapshot_version_and_content_come_from_same_transaction(tmp_path):
    from threading import Event, Thread

    store = TrackingStore(tmp_path / 'tracking.json')
    store.set_status(URL, 'SAVED', now=NOW)
    original_load = store.load
    started = Event()

    def writer():
        started.set()
        TrackingStore(store._path).set_status(URL, 'APPLIED', now=NOW)

    worker = Thread(target=writer)

    def load_during_concurrent_write():
        entries = original_load()
        worker.start()
        assert started.wait(2)
        return entries

    store.load = load_during_concurrent_write
    entries, version = store.snapshot()
    worker.join(2)
    assert not worker.is_alive()
    assert entries[URL]['status'] == 'SAVED'
    updated, next_version = TrackingStore(store._path).snapshot()
    assert updated[URL]['status'] == 'APPLIED'
    assert next_version != version
