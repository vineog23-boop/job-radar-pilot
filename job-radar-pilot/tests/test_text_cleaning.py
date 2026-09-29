from __future__ import annotations

import pytest

from job_radar.text_cleaning import clean_title


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Nova Desenvolvedor Java Júnior", "Desenvolvedor Java Júnior"),
        ("Desenvolvedor Java Júnior Nova", "Desenvolvedor Java Júnior"),
        ("  Desenvolvedor   Java \n Júnior  ", "Desenvolvedor Java Júnior"),
        ("Desenvolvedor Java Júnior | Acme Tecnologia", "Desenvolvedor Java Júnior"),
        ("Estágio em TI | Vaga afirmativa", "Estágio em TI"),
        ("Novo", "Novo"),
        ("Nova", "Nova"),
    ],
)
def test_clean_title_removes_noise(raw: str, expected: str) -> None:
    assert clean_title(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Desenvolvedor Java | Júnior",
        "Backend Java | Estágio",
        "Analista de Sistemas Novo Mundo",
        "Java Developer Nova Scotia",
        "Nova Scotia Java Júnior",
    ],
)
def test_clean_title_keeps_seniority_and_legitimate_words(raw: str) -> None:
    assert clean_title(raw) == raw


def test_clean_title_handles_none_and_blank() -> None:
    assert clean_title(None) is None
    assert clean_title("   ") is None
