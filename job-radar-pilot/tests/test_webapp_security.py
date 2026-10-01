"""Proteções do servidor local contra sites maliciosos abertos no navegador.

- Formulário de outro site (CSRF): não consegue mandar ``application/json``,
  então todo POST/PUT exige esse tipo, mesmo os que não têm corpo.
- DNS rebinding: um domínio de fora que passa a apontar para 127.0.0.1 chega
  com outro ``Host``; o painel só responde ao próprio endereço.
- ``Origin`` de outro site em POST/PUT é recusado.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from job_radar.webapp import SearchController, create_server

FORM = "application/x-www-form-urlencoded"


@pytest.fixture()
def dashboard(tmp_path: Path):
    started = Event()
    release = Event()

    def runner(output_dir, sources, workers, on_line):
        started.set()
        release.wait(timeout=5)
        return 0

    output = tmp_path / "output"
    output.mkdir()
    static_dir = tmp_path / "web"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<p>ok</p>", encoding="utf-8")
    controller = SearchController(output, runner=runner)
    server = create_server(
        "127.0.0.1",
        0,
        controller,
        static_dir,
        preferences_path=tmp_path / "prefs" / "search-preferences.json",
        tracking_path=tmp_path / "prefs" / "tracking.json",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "base": f"http://127.0.0.1:{server.server_port}",
            "port": server.server_port,
            "controller": controller,
            "started": started,
            "release": release,
            "output": output,
        }
    finally:
        release.set()
        controller.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _request(url: str, method: str = "GET", body: bytes | None = None, headers=None):
    request = Request(url, data=body, method=method, headers=headers or {})
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def test_form_post_from_other_site_cannot_stop_search(dashboard) -> None:
    dashboard["controller"].start()
    assert dashboard["started"].wait(timeout=5)

    status, body = _request(
        f"{dashboard['base']}/api/search/stop",
        "POST",
        b"x=1",
        {"Content-Type": FORM},
    )

    assert status == 415
    assert json.loads(body)["error"]
    assert dashboard["controller"].run_flags()["stopping"] is False


def test_form_post_from_other_site_cannot_undo_cleanup(dashboard) -> None:
    backup = dashboard["output"] / "vagas.antes-da-limpeza.jsonl"
    backup.write_text("", encoding="utf-8")

    status, _ = _request(
        f"{dashboard['base']}/api/cleanup/undo", "POST", b"", {"Content-Type": FORM}
    )

    assert status == 415
    assert backup.exists()


@pytest.mark.parametrize("path", ["/api/search/pause", "/api/cleanup/undo"])
def test_bodyless_post_without_content_type_is_refused(dashboard, path: str) -> None:
    status, _ = _request(f"{dashboard['base']}{path}", "POST", b"")

    assert status == 415


def test_json_post_from_dashboard_origin_still_works(dashboard) -> None:
    dashboard["controller"].start()
    assert dashboard["started"].wait(timeout=5)

    status, body = _request(
        f"{dashboard['base']}/api/search/pause",
        "POST",
        b"{}",
        {"Content-Type": "application/json", "Origin": dashboard["base"]},
    )

    assert status == 200
    assert json.loads(body)["paused"] is True


def test_post_with_foreign_origin_is_refused(dashboard) -> None:
    dashboard["controller"].start()
    assert dashboard["started"].wait(timeout=5)

    status, _ = _request(
        f"{dashboard['base']}/api/search/stop",
        "POST",
        b"{}",
        {"Content-Type": "application/json", "Origin": "https://site-malicioso.example"},
    )

    assert status == 403
    assert dashboard["controller"].run_flags()["stopping"] is False


@pytest.mark.parametrize("path", ["/api/tracking", "/api/state", "/api/export/csv", "/"])
def test_rebinding_host_cannot_read_anything(dashboard, path: str) -> None:
    status, body = _request(
        f"{dashboard['base']}{path}",
        headers={"Host": f"rebind.example:{dashboard['port']}"},
    )

    assert status == 403
    assert b"tracking" not in body


def test_put_with_rebinding_host_is_refused(dashboard) -> None:
    status, _ = _request(
        f"{dashboard['base']}/api/tracking",
        "PUT",
        json.dumps({"url": "https://example.com/vaga", "status": "SAVED"}).encode(),
        {"Content-Type": "application/json", "Host": "rebind.example"},
    )

    assert status == 403


@pytest.mark.parametrize("host", ["127.0.0.1:{port}", "localhost:{port}"])
def test_local_hosts_are_accepted(dashboard, host: str) -> None:
    status, _ = _request(
        f"{dashboard['base']}/api/tracking",
        headers={"Host": host.format(port=dashboard["port"])},
    )

    assert status == 200


def test_local_host_with_other_port_is_refused(dashboard) -> None:
    status, _ = _request(
        f"{dashboard['base']}/api/tracking",
        headers={"Host": f"127.0.0.1:{dashboard['port'] + 1}"},
    )

    assert status == 403
