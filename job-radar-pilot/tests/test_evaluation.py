"""Item 1.4: medir o classificador na amostra real (antes × depois e gabarito)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_radar import cli
from job_radar.evaluation import evaluate, format_report, load_gold
from job_radar.models import SearchProfile, WorkplaceModel

PROJECT = Path(__file__).resolve().parents[1]
SAMPLE = PROJECT / "tests" / "fixtures" / "amostra-real-2026-10-01.jsonl"


def _profile() -> SearchProfile:
    return SearchProfile(
        positive_keywords=("java", "spring boot"),
        seniority_levels=("estagio", "junior"),
        location_scopes=("remoto-brasil", "sao-carlos-sp"),
        workplace_models=(WorkplaceModel.REMOTE,),
    )


def _job(url: str, title: str, labels: list[str], **extra) -> dict:
    return {
        "source": extra.pop("source", "gupy"),
        "canonical_url": url,
        "title": title,
        "company": "Acme",
        "description_summary": extra.pop("description_summary", None),
        "location": extra.pop("location", "Remoto"),
        "workplace_model": extra.pop("workplace_model", "REMOTE"),
        "match_labels": labels,
        **extra,
    }


JOBS = [
    _job("https://x.com/1", "Desenvolvedor Java Júnior", ["FIT:READY"], remote_scope="Brasil"),
    _job("https://x.com/2", "Auxiliar Administrativo", ["FIT:READY"]),
    _job("https://x.com/3", "Desenvolvedor Java Sênior", ["FIT:CONDITIONAL"]),
]


def test_evaluate_counts_categories_and_changes_against_saved_labels() -> None:
    result = evaluate(JOBS, _profile(), {"gupy": "BR"})

    assert result["total"] == 3
    assert result["saved_distribution"] == {"READY": 2, "CONDITIONAL": 1}
    assert result["distribution"] == {"READY": 1, "OFF_TOPIC": 1, "EXCLUDE": 1}
    assert result["jobs"]["https://x.com/2"] == "OFF_TOPIC"
    assert result["changes"]["against"] == "amostra"
    assert result["changes"]["count"] == 2
    assert result["changes"]["transitions"] == {
        "CONDITIONAL -> EXCLUDE": 1,
        "READY -> OFF_TOPIC": 1,
    }
    assert result["by_source"] == {"gupy": {"READY": 1, "OFF_TOPIC": 1, "EXCLUDE": 1}}
    assert ("nível acima do desejado", 1) in result["reasons"]


def test_evaluate_compares_with_saved_base_run() -> None:
    base = {"jobs": {"https://x.com/1": "CONDITIONAL", "https://x.com/2": "OFF_TOPIC"}}

    result = evaluate(JOBS, _profile(), {"gupy": "BR"}, base=base)

    assert result["changes"]["against"] == "base"
    assert result["changes"]["transitions"] == {"CONDITIONAL -> READY": 1}


def test_gold_labels_measure_accuracy(tmp_path: Path) -> None:
    gold_path = tmp_path / "gabarito.csv"
    gold_path.write_text(
        "url;titulo;esperado;observacao\n"
        "https://x.com/1;Dev Java;READY;\n"
        "https://x.com/2;Auxiliar;off_topic;\n"
        "https://x.com/3;Dev Sênior;CONDITIONAL;eu aceitaria\n"
        "https://x.com/9;Sem resposta;;\n",
        encoding="utf-8-sig",
    )

    gold = load_gold(gold_path)
    result = evaluate(JOBS, _profile(), {"gupy": "BR"}, gold=gold)

    assert gold == {
        "https://x.com/1": "READY",
        "https://x.com/2": "OFF_TOPIC",
        "https://x.com/3": "CONDITIONAL",
    }
    assert result["gold"]["labeled"] == 3
    assert result["gold"]["correct"] == 2
    assert result["gold"]["accuracy"] == pytest.approx(2 / 3)
    assert result["gold"]["confusion"] == {"CONDITIONAL -> EXCLUDE": 1}
    assert result["gold"]["mistakes"][0]["title"] == "Desenvolvedor Java Sênior"


def test_gold_rejects_unknown_category(tmp_path: Path) -> None:
    gold_path = tmp_path / "gabarito.csv"
    gold_path.write_text("url;esperado\nhttps://x.com/1;TALVEZ\n", encoding="utf-8")

    with pytest.raises(ValueError, match="TALVEZ"):
        load_gold(gold_path)


def test_format_report_is_readable_portuguese() -> None:
    text = format_report(evaluate(JOBS, _profile(), {"gupy": "BR"}))

    assert "Vagas avaliadas: 3" in text
    assert "Mais compatível" in text
    assert "READY -> OFF_TOPIC" in text
    assert "gabarito" in text.casefold()


def test_cli_avaliar_runs_on_real_sample_and_saves_base(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saved = tmp_path / "base.json"

    exit_code = cli.main(["avaliar", "--amostra", str(SAMPLE), "--salvar", str(saved)])

    output = capsys.readouterr().out
    payload = json.loads(saved.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "Vagas avaliadas: 300" in output
    assert len(payload["jobs"]) == 300
    assert sum(payload["distribution"].values()) == 300


def test_cli_avaliar_compares_with_base(tmp_path: Path, capsys) -> None:
    base = tmp_path / "base.json"
    cli.main(["avaliar", "--amostra", str(SAMPLE), "--salvar", str(base)])
    capsys.readouterr()

    exit_code = cli.main(["avaliar", "--amostra", str(SAMPLE), "--base", str(base)])

    assert exit_code == 0
    assert "Mudaram de faixa em relação à base: 0" in capsys.readouterr().out
