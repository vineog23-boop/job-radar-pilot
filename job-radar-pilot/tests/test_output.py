from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from job_radar.models import (
    CollectionStatus,
    SourceRunResult,
    VacancyRecord,
    WorkplaceModel,
)
from job_radar.output import (
    OutputError,
    ValidationResult,
    validate_jsonl,
    write_outputs,
)
from job_radar.pipeline import PipelineResult


PROJECT = Path(__file__).resolve().parents[1]
SCHEMA = PROJECT / "schemas" / "vagas.schema.json"


def _record(*, partial: bool = False) -> VacancyRecord:
    return VacancyRecord(
        source="programathor",
        source_job_id=None if partial else "123",
        canonical_url="https://programathor.com.br/jobs/123",
        title="Estágio Java com acentuação" if partial else "Java Junior",
        company=None if partial else "Acme",
        description_summary=None if partial else "API REST com Spring Boot",
        seniority=None if partial else "junior",
        employment_type=None if partial else "CLT",
        technologies=("Java", "Spring Boot") if not partial else (),
        location=None if partial else "São Carlos, SP",
        workplace_model=WorkplaceModel.UNKNOWN if partial else WorkplaceModel.HYBRID,
        remote_scope=None,
        published_at=None,
        observed_at="2026-09-29T12:00:00+00:00",
        application_deadline=None,
        requirements=() if partial else ("Java 17",),
        eligibility_notes=(),
        evidence_snippets=("Estágio Java",),
        match_labels=("TECH_MATCH:java",),
        collection_status=CollectionStatus.SUCCESS,
        content_hash=None,
    )


def _result() -> PipelineResult:
    records = (_record(), _record(partial=True))
    return PipelineResult(
        started_at="2026-09-29T12:00:00+00:00",
        finished_at="2026-09-29T12:01:00+00:00",
        records=records,
        ambiguous=(),
        source_results=(
            SourceRunResult(
                source_code="programathor",
                status=CollectionStatus.SUCCESS,
                records=records,
                pages_observed=1,
                cards_observed=2,
            ),
        ),
        raw_record_count=2,
        duplicate_count=0,
    )


def test_write_outputs_validates_complete_and_partial_records(tmp_path: Path) -> None:
    manifest = write_outputs(_result(), tmp_path)

    validation = validate_jsonl(manifest.jsonl_path, SCHEMA)
    lines = [json.loads(line) for line in manifest.jsonl_path.read_text(encoding="utf-8").splitlines()]

    assert validation == ValidationResult(valid=True, line_count=2, errors=())
    assert len(lines[0]["content_hash"]) == 64
    assert lines[1]["company"] is None
    assert lines[1]["published_at"] is None
    assert lines[1]["technologies"] == []


def _valid_payload() -> dict[str, object]:
    return {
        "source": "programathor",
        "source_job_id": "123",
        "canonical_url": "https://programathor.com.br/jobs/123",
        "title": "Java Junior",
        "company": "Acme",
        "description_summary": None,
        "seniority": "junior",
        "employment_type": None,
        "technologies": ["Java"],
        "location": "São Carlos, SP",
        "workplace_model": "HYBRID",
        "remote_scope": None,
        "published_at": None,
        "observed_at": "2026-09-29T12:00:00+00:00",
        "application_deadline": None,
        "requirements": [],
        "eligibility_notes": [],
        "evidence_snippets": ["Java"],
        "match_labels": ["TECH_MATCH:java"],
        "collection_status": "SUCCESS",
        "content_hash": "a" * 64,
        "identity_strength": "STRONG",
    }


def test_validate_jsonl_rejects_missing_field(tmp_path: Path) -> None:
    payload = _valid_payload()
    del payload["title"]
    target = tmp_path / "invalid.jsonl"
    target.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    validation = validate_jsonl(target, SCHEMA)

    assert validation.valid is False
    assert validation.line_count == 1
    assert any("required" in error for error in validation.errors)


def test_validate_jsonl_rejects_unknown_field(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["unexpected"] = "field"
    target = tmp_path / "invalid.jsonl"
    target.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    validation = validate_jsonl(target, SCHEMA)

    assert validation.valid is False
    assert any("Additional properties" in error for error in validation.errors)


def test_csv_header_and_report_counts_are_reconciled(tmp_path: Path) -> None:
    manifest = write_outputs(_result(), tmp_path)

    with manifest.csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    report = json.loads(manifest.report_path.read_text(encoding="utf-8"))

    assert list(rows[0]) == [
        "source",
        "source_job_id",
        "title",
        "company",
        "location",
        "workplace_model",
        "canonical_url",
        "match_labels",
    ]
    assert len(rows) == 2
    assert report["scrapling_version"] == "0.4.15"
    assert len(report["upstream_commit"]) == 40
    assert report["totals"] == {
        "raw": 2,
        "unique": 2,
        "ambiguous": 0,
        "duplicates": 0,
    }
    assert report["sources"][0]["cards_observed"] == 2


def test_validation_failure_preserves_previous_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = tmp_path / "vagas.jsonl"
    previous.write_text("previous-valid-output\n", encoding="utf-8")
    monkeypatch.setattr(
        "job_radar.output.validate_jsonl",
        lambda path, schema: ValidationResult(False, 2, ("forced failure",)),
    )

    with pytest.raises(OutputError, match="schema"):
        write_outputs(_result(), tmp_path)

    assert previous.read_text(encoding="utf-8") == "previous-valid-output\n"
    assert not (tmp_path / "vagas.csv").exists()
    assert not (tmp_path / "relatorio-execucao.json").exists()
