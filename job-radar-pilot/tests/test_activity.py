from __future__ import annotations

from datetime import datetime, timezone

from job_radar.activity import (
    ACTIVE_CONFIRMED, ACTIVE_LISTED, CLOSED, UNKNOWN, activity_state,
)

NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
PUB = "2026-09-30T00:00:00+00:00"


def _job(**extra):
    return {"published_at": PUB, "observed_at": "2026-10-02T10:00:00+00:00", **extra}


def test_open_deadline_is_confirmed() -> None:
    assert activity_state(_job(application_deadline="2026-10-20T02:59:59+00:00"), NOW) == ACTIVE_CONFIRMED


def test_expired_deadline_wins_over_current_listing() -> None:
    assert activity_state(_job(application_deadline="2026-10-01T02:59:59+00:00"), NOW) == CLOSED


def test_recent_listing_without_deadline_is_listed() -> None:
    assert activity_state(_job(), NOW) == ACTIVE_LISTED


def test_preserved_old_record_is_not_active_by_inertia() -> None:
    assert activity_state(_job(observed_at="2026-09-01T00:00:00+00:00"), NOW) == UNKNOWN


def test_recent_listing_without_publication_is_listed_but_future_publication_is_unknown() -> None:
    assert activity_state(_job(published_at=None), NOW) == ACTIVE_LISTED
    assert activity_state(_job(published_at="2026-12-01T00:00:00+00:00"), NOW) == UNKNOWN


def test_recent_v2_link_confirms_without_publication_and_dead_closes():
    base = _job(published_at=None, observed_at="2026-08-01T00:00:00+00:00")
    for link, want in (("LIVE", ACTIVE_CONFIRMED), ("DEAD", CLOSED), ("UNKNOWN", UNKNOWN)):
        assert activity_state({**base, "match_labels": [f"LINK:{link}", "LINK_CHECKED_AT:2026-10-02T10:00:00+00:00", "LINK_CHECK_METHOD:JOB_DETAIL_V2"]}, NOW) == want


def test_expired_deadline_wins_live_and_link_age_is_bounded():
    base = _job(published_at=None, observed_at="2026-08-01T00:00:00+00:00")
    labels = ["LINK:LIVE", "LINK_CHECK_METHOD:JOB_DETAIL_V2"]
    for date in ("2026-09-01T00:00:00+00:00", "2026-10-03T00:00:00+00:00"):
        assert activity_state({**base, "match_labels": [*labels, f"LINK_CHECKED_AT:{date}"]}, NOW) == UNKNOWN
    fresh = {**base, "match_labels": [*labels, "LINK_CHECKED_AT:2026-10-02T10:00:00+00:00"]}
    assert activity_state({**fresh, "application_deadline": "2026-10-01T00:00:00+00:00"}, NOW) == CLOSED
    assert activity_state({**base, "match_labels": ["LINK:LIVE", "LINK_CHECKED_AT:2026-10-02T10:00:00+00:00"]}, NOW) == UNKNOWN


def test_future_observation_never_counts_as_recent_listing():
    assert activity_state(_job(observed_at="2026-10-03T00:00:00+00:00"), NOW) == UNKNOWN
