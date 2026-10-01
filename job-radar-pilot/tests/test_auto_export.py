"""Exportação automática ao fim de cada coleta (painel ou agendada)."""

from __future__ import annotations

from datetime import datetime, timezone
import io
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

import pytest

from job_radar import cli
from job_radar.auto_export import (
    AutoExportSettings,
    export_after_collection,
    load_settings,
    save_settings,
    settings_from_dict,
)
from job_radar.models import CollectionStatus, SourceRunResult, VacancyRecord
from job_radar.pipeline import PipelineResult

NOW = datetime(2026, 10, 1, 8, 30, tzinfo=timezone.utc)


def _job(url: str, title: str, labels: list[str]) -> dict:
    return {
        "source": "gupy",
        "canonical_url": url,
        "title": title,
        "company": "Acme",
        "match_labels": labels,
        "technologies": [],
    }


JOBS = [
    _job("https://x.com/1", "Dev Java Júnior", ["FIT:READY", "FIT_SCORE:4"]),
    _job("https://x.com/2", "Dev Java Pleno", ["FIT:CONDITIONAL", "FIT_SCORE:2"]),
    _job("https://x.com/3", "Dev Python", ["FIT:OTHER_STACK", "FIT_SCORE:2"]),
    _job("https://x.com/4", "Auxiliar", ["FIT:AMBIGUOUS", "RELEVANCE:OFF_TOPIC"]),
    _job("https://x.com/5", "Dev Java descartada", ["FIT:READY", "FIT_SCORE:4"]),
]
TRACKING = {"https://x.com/5": {"status": "DISCARDED"}}


def _write_output(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "vagas.jsonl").write_text(
        "".join(json.dumps(job, ensure_ascii=False) + "\n" for job in JOBS), encoding="utf-8"
    )


def _xlsx_titles(path: Path) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    return [title for title in ("Dev Java Júnior", "Dev Java Pleno", "Dev Python", "Auxiliar", "Dev Java descartada") if title in sheet]


def test_default_settings_are_on_and_point_to_documents(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / "prefs" / "search-preferences.json")

    assert settings.enabled is True
    assert settings.folder.name == "Radar de Vagas"


def test_settings_round_trip_and_validation(tmp_path: Path) -> None:
    prefs = tmp_path / "prefs" / "search-preferences.json"
    folder = tmp_path / "minhas planilhas"

    save_settings(prefs, settings_from_dict({"enabled": False, "folder": str(folder)}))

    loaded = load_settings(prefs)
    assert loaded == AutoExportSettings(enabled=False, folder=folder)
    with pytest.raises(ValueError):
        settings_from_dict({"enabled": True, "folder": "relativa/sem/raiz"})
    with pytest.raises(ValueError):
        settings_from_dict({"enabled": "sim"})


def test_export_writes_best_xlsx_full_csv_and_latest_copy(tmp_path: Path) -> None:
    output = tmp_path / "output"
    _write_output(output)
    folder = tmp_path / "exportacoes"

    written = export_after_collection(
        output, AutoExportSettings(enabled=True, folder=folder), TRACKING, now=NOW
    )

    names = sorted(path.name for path in written)
    assert names == [
        "melhores-vagas-2026-10-01-0830.xlsx",
        "todas-de-ti-2026-10-01-0830.csv",
        "ultima-busca.xlsx",
    ]
    best = _xlsx_titles(folder / "melhores-vagas-2026-10-01-0830.xlsx")
    assert best == ["Dev Java Júnior", "Dev Java Pleno"]  # sem outra stack, fora de TI e descartadas
    assert (folder / "ultima-busca.xlsx").read_bytes() == (
        folder / "melhores-vagas-2026-10-01-0830.xlsx"
    ).read_bytes()
    csv_text = (folder / "todas-de-ti-2026-10-01-0830.csv").read_text(encoding="utf-8-sig")
    assert "Dev Python" in csv_text and "Auxiliar" not in csv_text
    assert "Dev Java descartada" not in csv_text


def test_disabled_or_empty_output_writes_nothing(tmp_path: Path) -> None:
    output = tmp_path / "output"
    _write_output(output)

    assert export_after_collection(output, AutoExportSettings(enabled=False, folder=tmp_path / "x"), {}) == []
    assert export_after_collection(tmp_path / "vazia", AutoExportSettings(enabled=True, folder=tmp_path / "y"), {}) == []
    assert not (tmp_path / "x").exists() and not (tmp_path / "y").exists()


def _pipeline_result() -> PipelineResult:
    record = VacancyRecord(
        source="programathor",
        source_job_id="1",
        canonical_url="https://programathor.com.br/jobs/1",
        title="Desenvolvedor Java Júnior",
        company="Acme",
        observed_at="2026-09-29T12:00:00+00:00",
        match_labels=("FIT:READY", "FIT_SCORE:4"),
    )
    return PipelineResult(
        started_at="2026-09-29T12:00:00+00:00",
        finished_at="2026-09-29T12:01:00+00:00",
        records=(record,),
        ambiguous=(),
        source_results=(SourceRunResult("programathor", CollectionStatus.SUCCESS, records=(record,)),),
        raw_record_count=1,
        duplicate_count=0,
    )


class _Pipeline:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def run(self, source_codes=None) -> PipelineResult:
        return _pipeline_result()


class _Fetch:
    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None


def test_collect_exports_automatically_and_reports_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "JobRadarPipeline", _Pipeline)
    monkeypatch.setattr(cli, "FetchPolicy", _Fetch)

    exit_code = cli.main(
        ["collect", "--source", "programathor", "--no-history", "--keep-all", "--output", str(tmp_path / "out")]
    )

    out = capsys.readouterr().out
    export_dir = Path(__import__("os").environ["JOB_RADAR_EXPORT_DIR"])
    assert exit_code == 0
    assert (export_dir / "ultima-busca.xlsx").exists()
    assert f"EXPORT: {export_dir / 'ultima-busca.xlsx'}" in out


def test_collect_no_export_flag_and_failure_do_not_break_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "JobRadarPipeline", _Pipeline)
    monkeypatch.setattr(cli, "FetchPolicy", _Fetch)
    blocker = tmp_path / "arquivo-no-lugar-da-pasta"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("JOB_RADAR_EXPORT_DIR", str(blocker))

    failed = cli.main(["collect", "--source", "programathor", "--no-history", "--output", str(tmp_path / "a")])
    err = capsys.readouterr().err
    skipped = cli.main(
        ["collect", "--source", "programathor", "--no-history", "--no-export", "--output", str(tmp_path / "b")]
    )

    assert failed == 0 and "exportacao automatica" in err.casefold()
    assert skipped == 0


def test_controller_lists_exports_from_progress_lines(tmp_path: Path) -> None:
    from job_radar.webapp import SearchController

    def runner(output_dir, sources, workers, on_line):
        on_line(f"EXPORT: {tmp_path / 'ultima-busca.xlsx'}")
        return 0

    controller = SearchController(tmp_path, runner=runner)
    controller.start()
    controller.wait(timeout=5)

    assert controller.snapshot()["exports"] == [str(tmp_path / "ultima-busca.xlsx")]


def _call(base: str, path: str, method: str = "GET", payload: dict | None = None):
    request = Request(
        base + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def test_api_reads_and_saves_settings(tmp_path: Path) -> None:
    from job_radar.webapp import SearchController, create_server

    server = create_server(
        "127.0.0.1",
        0,
        SearchController(tmp_path / "output", runner=lambda *_: 0),
        tmp_path,
        preferences_path=tmp_path / "prefs" / "search-preferences.json",
        tracking_path=tmp_path / "prefs" / "tracking.json",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, current = _call(base, "/api/auto-export")
        saved_status, saved = _call(
            base, "/api/auto-export", "PUT", {"enabled": False, "folder": str(tmp_path / "pasta")}
        )
        bad_status, _ = _call(base, "/api/auto-export", "PUT", {"enabled": True, "folder": "x"})
        export_status, exported = _call(base, "/api/auto-export/run", "POST", {})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 200 and current["enabled"] is True
    assert saved_status == 200 and saved == {"enabled": False, "folder": str(tmp_path / "pasta")}
    assert bad_status == 400
    assert export_status == 200 and exported["files"] == []  # sem vagas ainda


def test_dashboard_auto_export_section(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    _write_output(output)
    folder = tmp_path / "planilhas"
    prefs = tmp_path / "prefs" / "search-preferences.json"
    save_settings(prefs, AutoExportSettings(enabled=True, folder=folder))
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(output, runner=lambda *_: 0),
        Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web",
        preferences_path=prefs,
        tracking_path=tmp_path / "prefs" / "tracking.json",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.get_by_role("button", name="Exportar vagas").click()
            page.wait_for_function(
                "document.querySelector('#auto-export-folder').value.length > 0"
            )
            assert page.locator("#auto-export-folder").input_value() == str(folder)

            page.locator("#auto-export-enabled").uncheck()
            page.wait_for_function(
                "document.querySelector('#auto-export-status').textContent.includes('Desligada')"
            )
            assert load_settings(prefs).enabled is False

            page.get_by_role("button", name="Exportar agora para a pasta").click()
            page.wait_for_function(
                "document.querySelector('#auto-export-status').textContent.startsWith('Pronto')"
            )
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert (folder / "ultima-busca.xlsx").exists()
