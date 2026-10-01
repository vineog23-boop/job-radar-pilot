from __future__ import annotations

import pytest

from job_radar.dates import parse_iso_datetime
from job_radar.fit import FIT_NAMES, fit_name, fit_state


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"match_labels": ["FIT:READY", "FIT_SCORE:4"]}, "READY"),
        ({"match_labels": ["FIT:EXCLUDE"]}, "EXCLUDE"),
        (["FIT:CONDITIONAL"], "CONDITIONAL"),
        ({"match_labels": []}, "AMBIGUOUS"),
        ({"match_labels": None}, "AMBIGUOUS"),
        ({"match_labels": "FIT:READY"}, "AMBIGUOUS"),  # texto solto não é lista
        ({}, "AMBIGUOUS"),
        (None, "AMBIGUOUS"),
    ],
)
def test_fit_state_reads_one_label(value, expected: str) -> None:
    assert fit_state(value) == expected


def test_fit_name_uses_portuguese_names() -> None:
    assert fit_name({"match_labels": ["FIT:READY"]}) == FIT_NAMES["READY"] == "Mais compatível"


def test_parse_iso_datetime_accepts_z_and_naive_as_utc() -> None:
    assert parse_iso_datetime("2026-10-01T10:00:00Z").utcoffset().total_seconds() == 0
    assert parse_iso_datetime(" 2026-10-01 ").tzinfo is not None
    assert parse_iso_datetime("ontem") is None
    assert parse_iso_datetime(None) is None
