from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

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
