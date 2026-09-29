from __future__ import annotations

from pathlib import Path

import pytest

from job_radar import cli
from job_radar.models import CollectionStatus, SourceRunResult
from job_radar.output import write_outputs
from job_radar.pipeline import PipelineResult


def _pipeline_result(status: CollectionStatus = CollectionStatus.SUCCESS) -> PipelineResult:
    return PipelineResult(
        started_at="2026-09-29T12:00:00+00:00",
        finished_at="2026-09-29T12:01:00+00:00",
        records=(),
        ambiguous=(),
        source_results=(SourceRunResult("programathor", status),),
        raw_record_count=0,
        duplicate_count=0,
    )


class FakePipeline:
    result = _pipeline_result()
    selected: list[str] | None = None

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def run(self, source_codes: list[str] | None = None) -> PipelineResult:
        type(self).selected = source_codes
        return type(self).result


def test_help_lists_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])

    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "collect" in output
    assert "validate-output" in output


def test_dry_run_validates_all_sources_without_fetching(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cli,
        "FetchPolicy",
        lambda: (_ for _ in ()).throw(AssertionError("network policy created")),
    )

    exit_code = cli.main(["collect", "--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "DRY_RUN" in output
    assert "programathor" in output
    assert "companhia-de-estagios" in output
    assert "16 fontes habilitadas" in output


def test_collect_accepts_repeated_source_filters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakePipeline.result = _pipeline_result()
    FakePipeline.selected = None
    monkeypatch.setattr(cli, "JobRadarPipeline", FakePipeline)
    monkeypatch.setattr(cli, "FetchPolicy", lambda: object())

    exit_code = cli.main(
        [
            "collect",
            "--source",
            "programathor",
            "--source",
            "indeed",
            "--output",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert FakePipeline.selected == ["programathor", "indeed"]
    assert (tmp_path / "relatorio-execucao.json").exists()


def test_unknown_source_returns_exit_code_2(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["collect", "--source", "unknown", "--dry-run"])

    assert exit_code == 2
    assert "desconhecida" in capsys.readouterr().err


def test_partial_run_returns_exit_code_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakePipeline.result = _pipeline_result(CollectionStatus.PARTIAL)
    monkeypatch.setattr(cli, "JobRadarPipeline", FakePipeline)
    monkeypatch.setattr(cli, "FetchPolicy", lambda: object())

    exit_code = cli.main(
        ["collect", "--source", "programathor", "--output", str(tmp_path)]
    )

    assert exit_code == 3


def test_validate_output_returns_zero_or_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = write_outputs(_pipeline_result(), tmp_path)

    assert cli.main(["validate-output", str(manifest.jsonl_path)]) == 0
    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text('{"source":"only"}\n', encoding="utf-8")
    assert cli.main(["validate-output", str(invalid)]) == 1
    assert "INVALID" in capsys.readouterr().out
