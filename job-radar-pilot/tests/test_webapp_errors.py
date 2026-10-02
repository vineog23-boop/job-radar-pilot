"""Erro inesperado numa rota vira resposta JSON 500, não conexão fechada."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from job_radar.webapp import SearchController, create_server


@pytest.fixture()
def server(tmp_path: Path):
    controller = SearchController(tmp_path / "output", runner=lambda *_: 0)
    instance = create_server(
        "127.0.0.1",
        0,
        controller,
        tmp_path,
        preferences_path=tmp_path / "prefs" / "search-preferences.json",
        tracking_path=tmp_path / "prefs" / "tracking.json",
    )
    thread = Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{instance.server_port}", controller
    instance.shutdown()
    instance.server_close()
    thread.join(timeout=2)


def _get(url: str):
    try:
        with urlopen(url, timeout=3) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def test_unexpected_error_in_route_returns_json_500(server, monkeypatch) -> None:
    base, _ = server

    def explode(*_args, **_kwargs):
        raise RuntimeError("disco sumiu")

    monkeypatch.setattr("job_radar.profiles.list_profiles", explode)

    status, body = _get(f"{base}/api/profiles")

    assert status == 500
    assert "disco sumiu" in body["error"]


def test_control_reports_disk_error_instead_of_crashing(tmp_path: Path, monkeypatch) -> None:
    started = Event()
    release = Event()

    def runner(*_args):
        started.set()
        release.wait(timeout=5)
        return 0

    controller = SearchController(tmp_path / "output", runner=runner)
    controller.start()
    assert started.wait(timeout=5)

    def fail(*_args):
        raise PermissionError("arquivo de controle travado")

    monkeypatch.setattr("job_radar.run_control.write_state", fail)
    try:
        error = controller.control("pause")
    finally:
        release.set()
        controller.wait(timeout=5)

    assert error is not None and "arquivo de controle travado" in error
