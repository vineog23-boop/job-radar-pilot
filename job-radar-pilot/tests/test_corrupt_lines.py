"""Linha ilegível no vagas.jsonl: nada que regrava o arquivo pode apagá-la.

Limpeza, desfazer e reaplicar liam o arquivo pulando linhas inválidas e depois
regravavam só o que conseguiram ler — a linha sumia sem aviso e sem backup.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_radar.cleanup import BACKUP_NAME, CleanupError, clean_output, undo_cleanup
from job_radar.models import SearchProfile
from job_radar.reclassify import reclassify_output

GOOD = {
    "source": "gupy",
    "canonical_url": "https://x.com/1",
    "title": "Auxiliar",
    "company": "Acme",
    "match_labels": ["FIT:AMBIGUOUS", "RELEVANCE:OFF_TOPIC"],
}
PROFILE = SearchProfile(
    positive_keywords=("java",), seniority_levels=("junior",), location_scopes=("brasil",)
)


def _corrupt_output(tmp_path: Path) -> str:
    content = json.dumps(GOOD) + "\n" + '{"title": "linha cortada no meio\n'
    (tmp_path / "vagas.jsonl").write_text(content, encoding="utf-8")
    return content


def test_cleanup_refuses_file_with_unreadable_lines(tmp_path: Path) -> None:
    content = _corrupt_output(tmp_path)

    with pytest.raises(CleanupError, match="1 linha"):
        clean_output(tmp_path)

    assert (tmp_path / "vagas.jsonl").read_text(encoding="utf-8") == content


def test_undo_refuses_file_with_unreadable_lines(tmp_path: Path) -> None:
    content = _corrupt_output(tmp_path)
    (tmp_path / BACKUP_NAME).write_text(
        json.dumps({**GOOD, "canonical_url": "https://x.com/2"}) + "\n", encoding="utf-8"
    )

    with pytest.raises(CleanupError, match="ilegív"):
        undo_cleanup(tmp_path)

    assert (tmp_path / "vagas.jsonl").read_text(encoding="utf-8") == content
    assert (tmp_path / BACKUP_NAME).exists()


def test_reapply_refuses_file_with_unreadable_lines(tmp_path: Path) -> None:
    content = _corrupt_output(tmp_path)

    with pytest.raises(ValueError, match="ilegív"):
        reclassify_output(tmp_path, PROFILE, {})

    assert (tmp_path / "vagas.jsonl").read_text(encoding="utf-8") == content
