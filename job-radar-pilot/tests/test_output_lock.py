"""Trava da pasta de saída entre processos (coleta agendada × painel).

Sem ela, uma coleta do Agendador do Windows e o "reaplicar"/"limpar" do painel
podiam ler o mesmo vagas.jsonl e o último a gravar apagava o trabalho do outro.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from job_radar import cli
from job_radar.output_lock import OutputBusyError, OutputLock, is_output_locked


def test_lock_is_exclusive_and_released(tmp_path: Path) -> None:
    with OutputLock(tmp_path / "output"):
        assert is_output_locked(tmp_path / "output")
        with pytest.raises(OutputBusyError):
            with OutputLock(tmp_path / "output"):
                pass
    assert not is_output_locked(tmp_path / "output")
    with OutputLock(tmp_path / "output"):
        pass


def test_missing_output_dir_is_not_locked(tmp_path: Path) -> None:
    assert not is_output_locked(tmp_path / "nao-existe")


def test_collect_exits_busy_when_another_collection_holds_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class ExplodingPipeline:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("nao deveria coletar com a saida travada")

    monkeypatch.setattr(cli, "JobRadarPipeline", ExplodingPipeline)
    output = tmp_path / "out"

    with OutputLock(output):
        exit_code = cli.main(
            ["collect", "--source", "programathor", "--no-history", "--output", str(output)]
        )

    assert exit_code == cli.EXIT_BUSY == 5
    assert "outra coleta" in capsys.readouterr().err.casefold()
    assert not (output / "vagas.jsonl").exists()


def test_controller_explains_busy_exit_code(tmp_path: Path) -> None:
    from job_radar.webapp import SearchController

    controller = SearchController(tmp_path, runner=lambda *_: cli.EXIT_BUSY)
    controller.start()
    controller.wait(timeout=5)

    state = controller.snapshot()
    assert state["status"] == "ERROR"
    assert "outra coleta" in state["error"].casefold()


def _call(url: str, method: str, payload: dict):
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def test_dashboard_refuses_to_rewrite_output_while_locked(tmp_path: Path) -> None:
    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    output.mkdir()
    (output / "vagas.antes-da-limpeza.jsonl").write_text("", encoding="utf-8")
    static_dir = tmp_path / "web"
    static_dir.mkdir()
    controller = SearchController(output, runner=lambda *_: 0)
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
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with OutputLock(output):
            cleanup = _call(f"{base}/api/cleanup", "POST", {})
            undo = _call(f"{base}/api/cleanup/undo", "POST", {})
            imported = _call(
                f"{base}/api/linkedin/import",
                "POST",
                {"text": "https://www.linkedin.com/jobs/view/123"},
            )
            preview = _call(f"{base}/api/cleanup", "POST", {"dry_run": True})
            saved = _call(
                f"{base}/api/preferences?reapply=1",
                "PUT",
                {
                    "search_terms": ["java junior"],
                    "seniority_levels": ["junior"],
                    "workplace_models": ["REMOTE"],
                    "location_scopes": ["brasil"],
                    "technologies": ["java"],
                },
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    for status, body in (cleanup, undo, imported):
        assert status == 409
        assert "outra coleta" in body["error"].casefold()
    assert preview[0] == 200  # prévia só lê
    assert saved[0] == 409
    assert "outra coleta" in saved[1]["error"].casefold()
    assert not (tmp_path / "prefs" / "search-preferences.json").exists()
    assert (output / "vagas.antes-da-limpeza.jsonl").exists()
