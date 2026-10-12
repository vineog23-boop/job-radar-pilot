from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from job_radar.history import NEW_LABEL, SeenHistory
from job_radar.models import VacancyRecord

NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def _record(job_id: str) -> VacancyRecord:
    return VacancyRecord(
        source="gupy",
        source_job_id=job_id,
        canonical_url=f"https://x.gupy.io/jobs/{job_id}",
        title="Desenvolvedor Java Junior",
        company=None,
        description_summary=None,
        location=None,
        observed_at=NOW.isoformat(),
        evidence_snippets=(),
    )


def test_first_run_marks_nothing_as_new(tmp_path: Path) -> None:
    history = SeenHistory(tmp_path / "h.json")
    result = history.annotate([_record("1"), _record("2")], NOW)
    assert all(NEW_LABEL not in r.match_labels for r in result)


def test_second_run_marks_only_unseen(tmp_path: Path) -> None:
    history = SeenHistory(tmp_path / "h.json")
    history.annotate([_record("1")], NOW)
    result = history.annotate([_record("1"), _record("2")], NOW)
    labels = {r.source_job_id: NEW_LABEL in r.match_labels for r in result}
    assert labels == {"1": False, "2": True}
    third = history.annotate([_record("2")], NOW)
    assert NEW_LABEL not in third[0].match_labels


def test_corrupted_history_is_treated_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "h.json"
    path.write_text("{nao e json", encoding="utf-8")
    result = SeenHistory(path).annotate([_record("1")], NOW)
    assert NEW_LABEL not in result[0].match_labels
    assert '"seen"' in path.read_text(encoding="utf-8")


def _result(code: str, count: int, status=None):
    from job_radar.models import CollectionStatus, SourceRunResult

    return SourceRunResult(
        source_code=code,
        status=status or CollectionStatus.SUCCESS,
        records=tuple(_record(f"{code}-{index}") for index in range(count)),
    )


def test_source_drop_warning_needs_previous_runs(tmp_path: Path) -> None:
    history = SeenHistory(tmp_path / "h.json")

    warnings = history.check_source_counts([_result("gupy", 0)])

    assert warnings == {}


def test_source_drop_over_half_of_average_warns(tmp_path: Path) -> None:
    history = SeenHistory(tmp_path / "h.json")
    history.check_source_counts([_result("gupy", 100), _result("nube", 40)])
    history.check_source_counts([_result("gupy", 80), _result("nube", 40)])

    warnings = history.check_source_counts([_result("gupy", 30), _result("nube", 25)])

    assert warnings == {"gupy": "SOURCE_COUNT_DROP:30<90"}


def test_source_dropping_to_zero_warns(tmp_path: Path) -> None:
    history = SeenHistory(tmp_path / "h.json")
    history.check_source_counts([_result("nube", 4)])
    history.check_source_counts([_result("nube", 5)])

    warnings = history.check_source_counts([_result("nube", 0)])

    assert warnings == {"nube": "SOURCE_COUNT_ZERO:0<4"}


def test_failed_runs_do_not_pollute_average(tmp_path: Path) -> None:
    from job_radar.models import CollectionStatus

    history = SeenHistory(tmp_path / "h.json")
    history.check_source_counts([_result("gupy", 100)])
    history.check_source_counts([_result("gupy", 0, CollectionStatus.ERROR)])
    history.check_source_counts([_result("gupy", 100)])

    assert history.check_source_counts([_result("gupy", 90)]) == {}


def test_source_counts_and_seen_entries_coexist(tmp_path: Path) -> None:
    history = SeenHistory(tmp_path / "h.json")
    history.annotate([_record("1")], NOW)
    history.check_source_counts([_result("gupy", 10)])
    history.check_source_counts([_result("gupy", 10)])

    result = history.annotate([_record("1"), _record("2")], NOW)

    assert [NEW_LABEL in r.match_labels for r in result] == [False, True]
    assert history.check_source_counts([_result("gupy", 1)]) == {
        "gupy": "SOURCE_COUNT_DROP:1<10"
    }


def test_corrupted_history_is_preserved_before_being_replaced(tmp_path: Path) -> None:
    path = tmp_path / "h.json"
    path.write_text("{corrompido", encoding="utf-8")

    SeenHistory(path).annotate([_record("1")], NOW)

    copies = list(tmp_path.glob("h.corrompido-*.json"))
    assert len(copies) == 1
    assert copies[0].read_text(encoding="utf-8") == "{corrompido"
    assert json.loads(path.read_text(encoding="utf-8"))["seen"]  # histórico novo e válido


def test_valid_history_is_not_copied(tmp_path: Path) -> None:
    history = SeenHistory(tmp_path / "h.json")
    history.annotate([_record("1")], NOW)
    history.annotate([_record("2")], NOW)

    assert not list(tmp_path.glob("*corrompido*"))


def test_source_count_check_continues_when_history_directory_is_not_writable(
    tmp_path: Path, monkeypatch
) -> None:
    history = SeenHistory(tmp_path / "h.json")

    def deny_temporary_file(*args, **kwargs):
        raise PermissionError("sem permissao para criar historico temporario")

    monkeypatch.setattr(tempfile, "mkstemp", deny_temporary_file)

    assert history.check_source_counts([_result("gupy", 10)]) == {}


# --- first_seen_at (10/10/2026): "vista pela 1ª vez" separada da data do portal ---------


def test_first_seen_at_is_kept_across_runs_and_never_touches_published_at(tmp_path: Path) -> None:
    from datetime import timedelta

    history = SeenHistory(tmp_path / "h.json")
    first = history.annotate([_record("1")], NOW)
    assert first[0].first_seen_at == NOW.isoformat()
    assert first[0].published_at is None
    later = NOW + timedelta(days=3)
    again = history.annotate([_record("1"), _record("2")], later)
    by_id = {r.source_job_id: r for r in again}
    assert by_id["1"].first_seen_at == NOW.isoformat()
    assert by_id["2"].first_seen_at == later.isoformat()
    assert all(r.published_at is None for r in again)


def test_first_seen_at_is_valid_in_the_output_schema() -> None:
    import jsonschema

    schema = json.loads((Path(__file__).resolve().parents[1] / "schemas" / "vagas.schema.json").read_text("utf-8"))
    assert "first_seen_at" in schema["properties"]
    assert "first_seen_at" not in schema["required"]
    from dataclasses import replace

    from job_radar.output import _record_payload

    record = replace(_record("1"), first_seen_at=NOW.isoformat(), content_hash="0" * 64)
    jsonschema.validate(_record_payload(record), schema)


def test_first_seen_at_survives_reclassification_roundtrip() -> None:
    from dataclasses import replace

    from job_radar.output import _record_payload
    from job_radar.reclassify import record_from_payload

    record = replace(_record("1"), first_seen_at=NOW.isoformat(), content_hash="0" * 64)
    assert record_from_payload(_record_payload(record)).first_seen_at == NOW.isoformat()
