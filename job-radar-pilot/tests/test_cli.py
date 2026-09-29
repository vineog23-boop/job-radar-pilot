from __future__ import annotations

from pathlib import Path

import pytest
from scrapling.parser import Adaptor
import yaml

from job_radar import cli
from job_radar.fetching import FetchResult
from job_radar.models import CollectionStatus, SourceRunResult
from job_radar.output import write_outputs
from job_radar.pipeline import PipelineResult


def _pipeline_result(
    status: CollectionStatus = CollectionStatus.SUCCESS,
    *,
    warnings: tuple[str, ...] = (),
) -> PipelineResult:
    return PipelineResult(
        started_at="2026-09-29T12:00:00+00:00",
        finished_at="2026-09-29T12:01:00+00:00",
        records=(),
        ambiguous=(),
        source_results=(SourceRunResult("programathor", status, warnings=warnings),),
        raw_record_count=0,
        duplicate_count=0,
    )


class FakePipeline:
    result = _pipeline_result()
    selected: list[str] | None = None
    profile: object | None = None
    kwargs: dict[str, object] = {}

    def __init__(self, *args: object, **kwargs: object) -> None:
        type(self).profile = args[1]
        type(self).kwargs = kwargs

    def run(self, source_codes: list[str] | None = None) -> PipelineResult:
        type(self).selected = source_codes
        callback = type(self).kwargs.get("on_source_done")
        if callable(callback):
            for source_result in type(self).result.source_results:
                callback(source_result)
        return type(self).result


class FakeFetchPolicy:
    entered = 0
    exited = 0

    def __enter__(self) -> "FakeFetchPolicy":
        type(self).entered += 1
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        type(self).exited += 1


class FakeSuggestionFetchPolicy:
    page: object
    calls: list[tuple[str, object]] = []

    def __enter__(self) -> "FakeSuggestionFetchPolicy":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def fetch(self, url: str, source: object) -> FetchResult:
        type(self).calls.append((url, source))
        return FetchResult(
            CollectionStatus.SUCCESS,
            response=type(self).page,  # type: ignore[arg-type]
            attempts=1,
        )


def _suggestion_page(url: str = "https://programathor.com.br/jobs-java") -> Adaptor:
    return Adaptor(
        """
        <ul class="jobs">
          <li class="vaga x1"><a href="/1"><h3>Desenvolvedor Java Junior</h3></a></li>
          <li class="vaga x2"><a href="/2"><h3>Estagio Java</h3></a></li>
          <li class="vaga x3"><a href="/3"><h3>Backend Junior</h3></a></li>
        </ul>
        """,
        url=url,
    )


def test_help_lists_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])

    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "collect" in output
    assert "auth" in output
    assert "validate-output" in output
    assert "suggest-selectors" in output


def test_suggest_selectors_for_configured_source_outputs_yaml_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sources_path = cli._project_root() / "config" / "sources.yaml"
    sources_before = sources_path.read_bytes()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    FakeSuggestionFetchPolicy.page = _suggestion_page()
    FakeSuggestionFetchPolicy.calls = []
    monkeypatch.setattr(cli, "FetchPolicy", FakeSuggestionFetchPolicy)

    exit_code = cli.main(
        [
            "suggest-selectors",
            "programathor",
            "--text",
            "Desenvolvedor Java Junior",
        ]
    )

    output = yaml.safe_load(capsys.readouterr().out)
    assert exit_code == 0
    assert output == {
        "selectors": {
            "card": "li.vaga",
            "title": "h3::all-text",
            "url": "a::attr(href)",
        },
        "cards_found": 3,
        "validation": {"title": "3/3", "url": "3/3"},
    }
    assert len(FakeSuggestionFetchPolicy.calls) == 1
    fetched_url, source = FakeSuggestionFetchPolicy.calls[0]
    assert fetched_url == "https://programathor.com.br/jobs-java"
    assert getattr(source, "code") == "programathor"
    assert getattr(source, "adaptive") is False
    assert sources_path.read_bytes() == sources_before
    assert not (tmp_path / "JobRadar" / "adaptive" / "adaptive.db").exists()


def test_suggest_selectors_missing_text_fetches_once_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sources_path = cli._project_root() / "config" / "sources.yaml"
    sources_before = sources_path.read_bytes()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    FakeSuggestionFetchPolicy.page = _suggestion_page()
    FakeSuggestionFetchPolicy.calls = []
    monkeypatch.setattr(cli, "FetchPolicy", FakeSuggestionFetchPolicy)

    exit_code = cli.main(
        ["suggest-selectors", "programathor", "--text", "Cobol Senior"]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "texto" in captured.err.casefold()
    assert len(FakeSuggestionFetchPolicy.calls) == 1
    assert sources_path.read_bytes() == sources_before
    assert not (tmp_path / "JobRadar" / "adaptive" / "adaptive.db").exists()


def test_suggest_selectors_raw_url_uses_matching_configured_source(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_url = "https://programathor.com.br/jobs-java?q=backend"
    FakeSuggestionFetchPolicy.page = _suggestion_page(raw_url)
    FakeSuggestionFetchPolicy.calls = []
    monkeypatch.setattr(cli, "FetchPolicy", FakeSuggestionFetchPolicy)
    monkeypatch.setattr(
        cli,
        "_resolved_addresses",
        lambda hostname: ("8.8.8.8",),
        raising=False,
    )

    exit_code = cli.main(
        [
            "suggest-selectors",
            raw_url,
            "--text",
            "Desenvolvedor Java Junior",
        ]
    )

    assert exit_code == 0
    assert yaml.safe_load(capsys.readouterr().out)["cards_found"] == 3
    assert len(FakeSuggestionFetchPolicy.calls) == 1
    fetched_url, source = FakeSuggestionFetchPolicy.calls[0]
    assert fetched_url == raw_url
    assert getattr(source, "code") == "programathor"
    assert getattr(source, "start_url") == raw_url
    assert getattr(source, "adaptive") is False


@pytest.mark.parametrize(
    "target",
    (
        "http://programathor.com.br/jobs-java",
        "https://user:password@programathor.com.br/jobs-java",
        "https://localhost/jobs",
        "https://127.0.0.1/jobs",
        "https://10.0.0.1/jobs",
        "https://169.254.1.1/jobs",
        "https://[::1]/jobs",
        "https://[fe80::1]/jobs",
        "https://programathor.com.br:bad/jobs",
        "not-a-source-or-url",
    ),
)
def test_suggest_selectors_rejects_unsafe_target_before_fetch(
    target: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "FetchPolicy",
        lambda: (_ for _ in ()).throw(AssertionError("fetch policy created")),
    )

    exit_code = cli.main(
        ["suggest-selectors", target, "--text", "Java Junior"]
    )

    assert exit_code == 2
    assert capsys.readouterr().out == ""


def test_suggest_selectors_rejects_private_dns_result_before_fetch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "_resolved_addresses",
        lambda hostname: ("127.0.0.1", "8.8.8.8"),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "FetchPolicy",
        lambda: (_ for _ in ()).throw(AssertionError("fetch policy created")),
    )

    exit_code = cli.main(
        [
            "suggest-selectors",
            "https://programathor.com.br/jobs-java",
            "--text",
            "Java Junior",
        ]
    )

    assert exit_code == 2
    assert capsys.readouterr().out == ""


def test_suggest_selectors_rejects_unconfigured_raw_origin_before_fetch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    resolver_calls: list[str] = []

    def resolve(hostname: str) -> tuple[str, ...]:
        resolver_calls.append(hostname)
        return ("8.8.8.8",)

    monkeypatch.setattr(
        cli,
        "_resolved_addresses",
        resolve,
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "FetchPolicy",
        lambda: (_ for _ in ()).throw(AssertionError("fetch policy created")),
    )

    exit_code = cli.main(
        [
            "suggest-selectors",
            "https://unconfigured.example/jobs",
            "--text",
            "Java Junior",
        ]
    )

    assert exit_code == 2
    assert "configurada" in capsys.readouterr().err.casefold()
    assert resolver_calls == []


def test_suggest_selectors_rejects_cross_origin_response(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_url = "https://programathor.com.br/jobs-java"
    FakeSuggestionFetchPolicy.page = _suggestion_page("https://attacker.example/jobs")
    FakeSuggestionFetchPolicy.calls = []
    monkeypatch.setattr(cli, "FetchPolicy", FakeSuggestionFetchPolicy)
    monkeypatch.setattr(
        cli,
        "_resolved_addresses",
        lambda hostname: ("8.8.8.8",),
        raising=False,
    )

    exit_code = cli.main(
        ["suggest-selectors", raw_url, "--text", "Java Junior"]
    )

    assert exit_code == 2
    assert len(FakeSuggestionFetchPolicy.calls) == 1
    assert "origem" in capsys.readouterr().err.casefold()


def test_suggest_selectors_rejects_cross_origin_response_for_configured_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sources_path = cli._project_root() / "config" / "sources.yaml"
    sources_before = sources_path.read_bytes()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    FakeSuggestionFetchPolicy.page = _suggestion_page(
        "https://attacker.example/jobs"
    )
    FakeSuggestionFetchPolicy.calls = []
    monkeypatch.setattr(cli, "FetchPolicy", FakeSuggestionFetchPolicy)

    exit_code = cli.main(
        [
            "suggest-selectors",
            "programathor",
            "--text",
            "Desenvolvedor Java Junior",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "origem" in captured.err.casefold()
    assert len(FakeSuggestionFetchPolicy.calls) == 1
    assert sources_path.read_bytes() == sources_before
    assert not (tmp_path / "JobRadar" / "adaptive" / "adaptive.db").exists()


@pytest.mark.parametrize(
    "raw_url",
    (
        "https://app.eureca.me/oportunidades?q=java",
        "https://portal.gupy.io/job-search?term=java",
    ),
)
def test_suggest_selectors_rejects_browser_backed_raw_url_before_fetch(
    raw_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    FakeSuggestionFetchPolicy.page = _suggestion_page(raw_url)
    FakeSuggestionFetchPolicy.calls = []
    monkeypatch.setattr(cli, "FetchPolicy", FakeSuggestionFetchPolicy)
    monkeypatch.setattr(
        cli,
        "_resolved_addresses",
        lambda hostname: ("8.8.8.8",),
        raising=False,
    )

    exit_code = cli.main(
        ["suggest-selectors", raw_url, "--text", "Desenvolvedor Java Junior"]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "url crua" in captured.err.casefold()
    assert FakeSuggestionFetchPolicy.calls == []


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
    assert "15 fontes habilitadas" in output
    assert "16 fontes configuradas" in output
    assert "locale=pt-BR" in output
    assert "timezone=America/Sao_Paulo" in output
    assert "accept_language=pt-BR,pt;q=0.9,en;q=0.6" in output
    assert "block_ads=false" in output
    assert "disable_resources=false" in output
    assert "blocked_domains=-" in output


def test_collect_accepts_repeated_source_filters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakePipeline.result = _pipeline_result()
    FakePipeline.selected = None
    FakeFetchPolicy.entered = 0
    FakeFetchPolicy.exited = 0
    monkeypatch.setattr(cli, "JobRadarPipeline", FakePipeline)
    monkeypatch.setattr(cli, "FetchPolicy", FakeFetchPolicy)

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
    assert FakeFetchPolicy.entered == 1
    assert FakeFetchPolicy.exited == 1
    assert (tmp_path / "relatorio-execucao.json").exists()


def test_collect_workers_three_uses_factory_and_prints_progress_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class ProgressPipeline(FakePipeline):
        def run(self, source_codes: list[str] | None = None) -> PipelineResult:
            return super().run(source_codes)

    ProgressPipeline.result = _pipeline_result()
    monkeypatch.setattr(cli, "JobRadarPipeline", ProgressPipeline)
    monkeypatch.setattr(cli, "FetchPolicy", FakeFetchPolicy)

    exit_code = cli.main(
        [
            "collect",
            "--workers",
            "3",
            "--source",
            "programathor",
            "--output",
            str(tmp_path),
        ]
    )

    progress_lines = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("programathor:")
    ]
    assert exit_code == 0
    assert ProgressPipeline.kwargs["workers"] == 3
    assert ProgressPipeline.kwargs["fetcher_factory"] is FakeFetchPolicy
    assert progress_lines == [
        "programathor: SUCCESS; pages=0; cards=0; records=0; stop=EXHAUSTED"
    ]


@pytest.mark.parametrize("workers", ["0", "5"])
def test_collect_rejects_workers_outside_supported_range(workers: str) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["collect", "--workers", workers, "--dry-run"])

    assert error.value.code == 2


def test_collect_applies_local_preferences_to_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from job_radar.models import WorkplaceModel
    from job_radar.preferences import SearchPreferences

    FakePipeline.result = _pipeline_result()
    FakePipeline.profile = None
    monkeypatch.setattr(cli, "JobRadarPipeline", FakePipeline)
    monkeypatch.setattr(cli, "FetchPolicy", FakeFetchPolicy)
    monkeypatch.setattr(
        cli,
        "load_preferences",
        lambda **kwargs: SearchPreferences(
            search_terms=("estagio java remoto",),
            seniority_levels=("estagio",),
            workplace_models=(WorkplaceModel.REMOTE,),
            location_scopes=("remoto-brasil",),
        ),
    )

    assert cli.main(["collect", "--source", "indeed", "--output", str(tmp_path)]) == 0

    assert FakePipeline.profile is not None
    assert getattr(FakePipeline.profile, "search_terms") == ("estagio java remoto",)
    assert getattr(FakePipeline.profile, "seniority_levels") == ("estagio",)
    assert getattr(FakePipeline.profile, "workplace_models") == (WorkplaceModel.REMOTE,)


def test_unknown_source_returns_exit_code_2(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["collect", "--source", "unknown", "--dry-run"])

    assert exit_code == 2
    assert "desconhecida" in capsys.readouterr().err


def test_partial_run_returns_exit_code_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakePipeline.result = _pipeline_result(CollectionStatus.PARTIAL)
    monkeypatch.setattr(cli, "JobRadarPipeline", FakePipeline)
    monkeypatch.setattr(cli, "FetchPolicy", FakeFetchPolicy)

    exit_code = cli.main(
        ["collect", "--source", "programathor", "--output", str(tmp_path)]
    )

    assert exit_code == 3


def test_collect_prints_warnings_separately_without_changing_progress_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    FakePipeline.result = _pipeline_result(
        CollectionStatus.PARTIAL,
        warnings=("SELECTOR_RELOCATED:card",),
    )
    monkeypatch.setattr(cli, "JobRadarPipeline", FakePipeline)
    monkeypatch.setattr(cli, "FetchPolicy", FakeFetchPolicy)

    exit_code = cli.main(
        ["collect", "--source", "programathor", "--output", str(tmp_path)]
    )

    lines = capsys.readouterr().out.splitlines()
    assert exit_code == 3
    assert lines[0] == (
        "programathor: PARTIAL; pages=0; cards=0; records=0; stop=EXHAUSTED"
    )
    assert lines[1] == "WARNING programathor: SELECTOR_RELOCATED:card"


def test_auth_opens_configured_source_without_receiving_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    def fake_bootstrap(source: object) -> Path:
        captured["source"] = source
        return tmp_path / "nube"

    monkeypatch.setattr(cli, "bootstrap_auth", fake_bootstrap)

    exit_code = cli.main(["auth", "nube"])

    assert exit_code == 0
    assert getattr(captured["source"], "code") == "nube"
    output = capsys.readouterr().out
    assert "AUTH_PROFILE_SAVED_UNVERIFIED: nube" in output
    assert "senha" not in output.casefold()


def test_auth_rejects_unknown_source_without_opening_browser(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "bootstrap_auth",
        lambda source: (_ for _ in ()).throw(AssertionError("browser opened")),
    )

    exit_code = cli.main(["auth", "unknown"])

    assert exit_code == 2
    assert "desconhecida" in capsys.readouterr().err


def test_validate_output_returns_zero_or_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = write_outputs(_pipeline_result(), tmp_path)

    assert cli.main(["validate-output", str(manifest.jsonl_path)]) == 0
    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text('{"source":"only"}\n', encoding="utf-8")
    assert cli.main(["validate-output", str(invalid)]) == 1
    assert "INVALID" in capsys.readouterr().out
