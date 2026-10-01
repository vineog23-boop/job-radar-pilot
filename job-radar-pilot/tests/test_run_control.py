from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from threading import Event, Thread
from urllib.request import Request, urlopen

import pytest

from job_radar import run_control
from job_radar.models import (
    CollectionStatus,
    SearchProfile,
    SourceConfig,
    SourceKind,
    SourceRunResult,
    VacancyRecord,
)
from job_radar.output import write_outputs
from job_radar.pipeline import JobRadarPipeline, PipelineResult
from job_radar.run_control import RunControl, write_state

PROFILE = SearchProfile(
    positive_keywords=("java",),
    seniority_levels=("junior",),
    location_scopes=("brasil",),
)


def _source(code: str, **extra) -> SourceConfig:
    values = dict(
        code=code,
        kind=SourceKind.GENERIC,
        start_url=f"https://{code}.example.com/jobs",
        enabled=True,
        max_pages=1,
        min_interval_seconds=0,
        requires_auth=False,
        selectors={"card": "article", "title": "h2", "url": "a::attr(href)"},
    )
    values.update(extra)
    return SourceConfig(**values)


def _record(source: str, url: str) -> VacancyRecord:
    return VacancyRecord(
        source=source,
        source_job_id=None,
        canonical_url=url,
        title="Desenvolvedor Java Junior",
        company="Acme",
        location="Remoto",
    )


# --- arquivo de controle ---------------------------------------------------------


def test_run_control_reads_states_and_ignores_garbage(tmp_path: Path) -> None:
    path = tmp_path / ".radar-control"
    control = RunControl(path)
    assert control.state() == "run"  # sem arquivo
    write_state(path, "pause")
    assert control.state() == "pause"
    write_state(path, "stop")
    assert control.state() == "stop" and control.should_stop()
    path.write_text("qualquer coisa", encoding="utf-8")
    assert control.state() == "run"
    write_state(path, "run")
    assert not path.exists()
    with pytest.raises(ValueError):
        write_state(path, "explodir")
    assert RunControl().state() == "run"  # sem caminho nunca pausa


def test_wait_if_paused_blocks_until_resumed(tmp_path: Path) -> None:
    path = tmp_path / ".radar-control"
    write_state(path, "pause")
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 3:
            write_state(path, "run")

    control = RunControl(path, poll_seconds=0.1, sleep=fake_sleep)
    control.wait_if_paused()
    assert sleeps == [0.1, 0.1, 0.1]
    assert control.was_paused is True


def test_stop_while_paused_releases_the_wait(tmp_path: Path) -> None:
    path = tmp_path / ".radar-control"
    write_state(path, "pause")
    control = RunControl(path, sleep=lambda _: write_state(path, "stop"))
    assert control.should_stop() is True


# --- pipeline ---------------------------------------------------------------------


def test_pipeline_stops_between_sources_and_skips_the_rest(tmp_path: Path) -> None:
    path = tmp_path / ".radar-control"
    calls: list[str] = []

    class Adapter:
        def collect(self, config: SourceConfig, fetcher: object) -> SourceRunResult:
            calls.append(config.code)
            write_state(path, "stop")  # a pessoa clica em parar durante o 1º portal
            return SourceRunResult(
                config.code,
                CollectionStatus.SUCCESS,
                (_record(config.code, f"https://ats.test/{config.code}"),),
            )

    result = JobRadarPipeline(
        (_source("um"), _source("dois"), _source("tres")),
        PROFILE,
        fetcher=object(),
        adapter_factory=lambda config: Adapter(),
        control=RunControl(path),
    ).run()

    assert calls == ["um"]
    assert result.stopped is True
    assert [item.source_code for item in result.source_results] == ["um"]
    assert len(result.records) == 1


def test_pipeline_stop_mid_queries_marks_source_partial(tmp_path: Path) -> None:
    path = tmp_path / ".radar-control"
    source = replace(
        _source("indeed"),
        kind=SourceKind.INDEED,
        start_url="https://br.indeed.com/jobs?q=java",
        queries=("java junior", "spring junior", "backend junior"),
    )
    calls: list[str] = []

    class Adapter:
        def collect(self, config: SourceConfig, fetcher: object) -> SourceRunResult:
            calls.append(config.start_url)
            write_state(path, "stop")
            return SourceRunResult(
                config.code,
                CollectionStatus.SUCCESS,
                (_record(config.code, f"https://ats.test/{len(calls)}"),),
            )

    result = JobRadarPipeline(
        (source,),
        PROFILE,
        fetcher=object(),
        adapter_factory=lambda config: Adapter(),
        control=RunControl(path),
    ).run()

    assert len(calls) == 1
    (only,) = result.source_results
    assert only.status is CollectionStatus.PARTIAL
    assert only.stop_reason == run_control.STOP_REASON
    assert result.stopped is True


def test_pipeline_without_control_file_runs_everything() -> None:
    class Adapter:
        def collect(self, config: SourceConfig, fetcher: object) -> SourceRunResult:
            return SourceRunResult(config.code, CollectionStatus.EMPTY)

    result = JobRadarPipeline(
        (_source("um"), _source("dois")),
        PROFILE,
        fetcher=object(),
        adapter_factory=lambda config: Adapter(),
    ).run()
    assert result.stopped is False
    assert len(result.source_results) == 2


# --- gravação: o que não foi refeito continua na lista -------------------------------


def _result(records, source_results, *, stopped: bool) -> PipelineResult:
    return PipelineResult(
        started_at="2026-09-30T12:00:00+00:00",
        finished_at="2026-09-30T12:01:00+00:00",
        records=tuple(records),
        ambiguous=(),
        source_results=tuple(source_results),
        raw_record_count=len(records),
        duplicate_count=0,
        stopped=stopped,
    )


def test_write_outputs_after_stop_keeps_skipped_and_partial_sources(tmp_path: Path) -> None:
    old = [
        _record("um", "https://ats.test/um-antiga"),
        _record("dois", "https://ats.test/dois-antiga"),
        _record("tres", "https://ats.test/tres-antiga"),
    ]
    write_outputs(
        _result(
            old,
            [SourceRunResult(code, CollectionStatus.SUCCESS) for code in ("um", "dois", "tres")],
            stopped=False,
        ),
        tmp_path,
    )

    new = [_record("um", "https://ats.test/um-nova"), _record("dois", "https://ats.test/dois-nova")]
    write_outputs(
        _result(
            new,
            [
                SourceRunResult("um", CollectionStatus.SUCCESS, (new[0],)),
                SourceRunResult(
                    "dois",
                    CollectionStatus.PARTIAL,
                    (new[1],),
                    stop_reason=run_control.STOP_REASON,
                ),
            ],
            stopped=True,
        ),
        tmp_path,
        merge_unrefreshed=True,
        partial_sources={"dois"},
    )

    urls = sorted(
        json.loads(line)["canonical_url"]
        for line in (tmp_path / "vagas.jsonl").read_text(encoding="utf-8").splitlines()
    )
    # "um" foi refeito por inteiro (a antiga sai); "dois" parou no meio (a antiga
    # fica); "tres" nem começou (a antiga fica).
    assert urls == [
        "https://ats.test/dois-antiga",
        "https://ats.test/dois-nova",
        "https://ats.test/tres-antiga",
        "https://ats.test/um-nova",
    ]


# --- painel: controlador e API --------------------------------------------------------


def test_controller_pause_resume_stop_and_final_status(tmp_path: Path) -> None:
    from job_radar.webapp import SearchController

    started = Event()
    release = Event()
    seen_states: list[str] = []

    def runner(output_dir, sources, workers, on_line):
        started.set()
        release.wait(timeout=5)
        seen_states.append(RunControl(output_dir / run_control.CONTROL_FILE_NAME).state())
        return 4

    controller = SearchController(tmp_path, runner=runner)
    assert controller.control("pause") == "Nenhuma busca em andamento."
    assert controller.start()
    assert started.wait(timeout=5)

    assert controller.control("pause") is None
    assert controller.snapshot()["paused"] is True
    assert (tmp_path / ".radar-control").read_text(encoding="utf-8") == "pause"
    assert controller.control("resume") is None
    assert controller.snapshot()["paused"] is False
    assert not (tmp_path / ".radar-control").exists()
    assert controller.control("explodir") == "Ação inválida."

    assert controller.control("stop") is None
    assert controller.snapshot()["stopping"] is True
    assert controller.control("pause") == "A busca já está sendo encerrada."
    release.set()
    assert controller.wait(timeout=5)

    snapshot = controller.snapshot()
    assert seen_states == ["stop"]
    assert snapshot["status"] == "STOPPED"
    assert snapshot["error"] is None
    assert snapshot["paused"] is False and snapshot["stopping"] is False
    assert not (tmp_path / ".radar-control").exists()


def test_api_search_control_endpoints(tmp_path: Path) -> None:
    from job_radar.webapp import SearchController, create_server

    started = Event()
    release = Event()

    def runner(output_dir, sources, workers, on_line):
        started.set()
        release.wait(timeout=5)
        return 0

    static_dir = tmp_path / "web"
    static_dir.mkdir()
    controller = SearchController(tmp_path / "output", runner=runner)
    server = create_server("127.0.0.1", 0, controller, static_dir)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def post(path: str):
        request = Request(f"{base}{path}", data=b"", method="POST")
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except Exception as error:  # HTTPError
            return error.code, json.loads(error.read())

    try:
        idle_status, idle = post("/api/search/pause")
        controller.start()
        assert started.wait(timeout=5)
        pause_status, paused = post("/api/search/pause")
        resume_status, resumed = post("/api/search/resume")
        release.set()
        controller.wait(timeout=5)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert idle_status == 409 and "Nenhuma busca" in idle["error"]
    assert pause_status == 200 and paused["paused"] is True
    assert resume_status == 200 and resumed["paused"] is False


def test_build_collection_command_passes_control_file(tmp_path: Path) -> None:
    from job_radar.webapp import build_collection_command

    command = build_collection_command(
        tmp_path, None, executable=Path("python.exe"), control_file=tmp_path / ".radar-control"
    )
    assert command[-2:] == ["--control-file", str(tmp_path / ".radar-control")]


def test_dashboard_shows_pause_and_stop_while_running(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    release = Event()

    def runner(output_dir, sources, workers, on_line):
        release.wait(timeout=20)
        return 4

    static_dir = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
    controller = SearchController(tmp_path / "output", runner=runner)
    server = create_server(
        "127.0.0.1",
        0,
        controller,
        static_dir,
        preferences_path=tmp_path / "search-preferences.json",
        tracking_path=tmp_path / "tracking.json",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("dialog", lambda dialog: dialog.accept())
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            assert page.locator("#run-controls").is_hidden()

            page.get_by_role("button", name="Buscar vagas agora").click()
            page.locator("#run-controls").wait_for(state="visible")

            page.get_by_role("button", name="⏸ Pausar busca").click()
            page.get_by_text("Busca pausada").wait_for()
            page.get_by_role("button", name="▶ Retomar busca").click()
            page.get_by_text("Buscando vagas").wait_for()

            page.get_by_role("button", name="■ Parar e salvar").click()
            page.get_by_text("Encerrando").wait_for()
            release.set()
            page.get_by_text("Busca interrompida").wait_for(timeout=10_000)
            page.locator("#run-controls").wait_for(state="hidden")
            browser.close()
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
