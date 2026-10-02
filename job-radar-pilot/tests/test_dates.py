from __future__ import annotations

from datetime import datetime, timezone

import pytest

from job_radar.dates import parse_published_at


NOW = datetime(2026, 9, 29, 15, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-09-20T10:00:00Z", "2026-09-20T10:00:00+00:00"),
        ("2026-09-20T10:00:00-03:00", "2026-09-20T13:00:00+00:00"),
        ("2026-09-20", "2026-09-20T00:00:00+00:00"),
        ("20/09/2026", "2026-09-20T00:00:00+00:00"),
        ("há 3 dias", "2026-09-26T15:30:00+00:00"),
        ("Publicada há 1 dia", "2026-09-28T15:30:00+00:00"),
        ("há 2 semanas", "2026-09-15T15:30:00+00:00"),
        ("há 5 horas", "2026-09-29T10:30:00+00:00"),
        ("Há 1 mês", "2026-08-30T15:30:00+00:00"),
        ("hoje", "2026-09-29T15:30:00+00:00"),
        ("Publicada ontem", "2026-09-28T15:30:00+00:00"),
        ("3 days ago", "2026-09-26T15:30:00+00:00"),
    ],
)
def test_parse_published_at_converts_known_formats(raw: str, expected: str) -> None:
    assert parse_published_at(raw, now=NOW) == expected


@pytest.mark.parametrize(
    "raw",
    [None, "", "   ", "em breve", "31/02/2026", "há muito tempo", "2030-01-01", "há 0 dias x"],
)
def test_parse_published_at_returns_none_without_evidence(raw: str | None) -> None:
    assert parse_published_at(raw, now=NOW) is None


def test_parses_portuguese_long_date() -> None:
    from datetime import datetime, timezone

    from job_radar.dates import parse_published_at

    now = datetime(2026, 9, 30, tzinfo=timezone.utc)
    assert parse_published_at("29 de setembro de 2026", now=now).startswith("2026-09-29")
    assert parse_published_at("1 de março de 2026", now=now).startswith("2026-03-01")
    assert parse_published_at("31 de fevereiro de 2026", now=now) is None
    assert parse_published_at("15 de dezembro de 2026", now=now) is None


def test_parse_deadline_date_only_valid_until_end_of_day_in_brasilia() -> None:
    from job_radar.dates import is_expired, parse_deadline
    from datetime import datetime, timezone

    deadline = parse_deadline("2026-10-20")
    assert deadline == "2026-10-21T02:59:59+00:00"
    assert not is_expired(deadline, datetime(2026, 10, 21, 2, 0, tzinfo=timezone.utc))
    assert is_expired(deadline, datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc))
    assert parse_deadline("lixo") is None and parse_deadline(None) is None


def test_is_stale_requires_a_proven_date() -> None:
    from job_radar.dates import is_stale
    from datetime import datetime, timezone

    now = datetime(2026, 10, 2, tzinfo=timezone.utc)
    assert is_stale("2026-08-01T00:00:00+00:00", 30, now)
    assert not is_stale("2026-09-25T00:00:00+00:00", 30, now)
    assert not is_stale(None, 30, now)
    assert not is_stale("2026-08-01T00:00:00+00:00", None, now)
