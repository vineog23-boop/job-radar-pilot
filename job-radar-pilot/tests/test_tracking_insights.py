"""Sugestões a partir do que o usuário salvou/aplicou × descartou (item 1.3)."""

from __future__ import annotations

from job_radar.models import SearchProfile, WorkplaceModel
from job_radar.reclassify import tracking_insights

PROFILE = SearchProfile(
    positive_keywords=("java",),
    seniority_levels=("junior",),
    location_scopes=("brasil",),
    workplace_models=(WorkplaceModel.REMOTE,),
)


def _job(url: str, company: str, technologies: tuple[str, ...] = (), match_labels=()):
    return {
        "canonical_url": url,
        "company": company,
        "technologies": list(technologies),
        "match_labels": list(match_labels),
    }


def _tracked(status: str) -> dict[str, str]:
    return {"status": status}


def test_discarded_company_without_positive_signal_is_suggested_to_avoid() -> None:
    payloads = [
        _job("https://a.test/1", "Fintech X"),
        _job("https://a.test/2", "Fintech X"),
        _job("https://a.test/3", "Fintech X"),
    ]
    tracking = {url: _tracked("DISCARDED") for url in ("https://a.test/1", "https://a.test/2", "https://a.test/3")}

    result = tracking_insights(payloads, tracking, PROFILE)

    assert result["sample"] == {"saved": 0, "discarded": 3}
    assert result["companies_avoid"] == [{"term": "Fintech X", "count": 3, "other_count": 0}]
    assert result["companies_favorite"] == []


def test_saved_company_without_negative_signal_is_suggested_as_favorite() -> None:
    payloads = [_job(f"https://a.test/{i}", "BoaEmpresa") for i in range(3)]
    tracking = {job["canonical_url"]: _tracked("SAVED") for job in payloads}

    result = tracking_insights(payloads, tracking, PROFILE)

    assert result["companies_favorite"] == [{"term": "BoaEmpresa", "count": 3, "other_count": 0}]
    assert result["companies_avoid"] == []


def test_keywords_follow_the_same_skew_rule() -> None:
    payloads = [
        _job("https://a.test/1", "X", technologies=("cobol",)),
        _job("https://a.test/2", "Y", technologies=("cobol",)),
        _job("https://a.test/3", "Z", technologies=("kotlin",)),
        _job("https://a.test/4", "W", technologies=("kotlin",)),
    ]
    tracking = {
        "https://a.test/1": _tracked("DISCARDED"),
        "https://a.test/2": _tracked("DISCARDED"),
        "https://a.test/3": _tracked("APPLIED"),
        "https://a.test/4": _tracked("INTERVIEW"),
    }

    result = tracking_insights(payloads, tracking, PROFILE)

    assert {"term": "cobol", "count": 2, "other_count": 0} in result["keywords_avoid"]
    assert {"term": "kotlin", "count": 2, "other_count": 0} in result["keywords_favorite"]


def test_company_already_in_profile_is_never_suggested_again() -> None:
    payloads = [_job(f"https://a.test/{i}", "Fintech X") for i in range(3)]
    tracking = {job["canonical_url"]: _tracked("DISCARDED") for job in payloads}
    profile = _with(PROFILE, excluded_companies=("Fintech X",))

    result = tracking_insights(payloads, tracking, profile)

    assert result["companies_avoid"] == []


def test_signal_tied_on_both_sides_is_not_suggested() -> None:
    payloads = [
        _job("https://a.test/1", "Dividida"),
        _job("https://a.test/2", "Dividida"),
        _job("https://a.test/3", "Dividida"),
        _job("https://a.test/4", "Dividida"),
    ]
    tracking = {
        "https://a.test/1": _tracked("DISCARDED"),
        "https://a.test/2": _tracked("DISCARDED"),
        "https://a.test/3": _tracked("SAVED"),
        "https://a.test/4": _tracked("APPLIED"),
    }

    result = tracking_insights(payloads, tracking, PROFILE)

    # 2 descartes x 2 salvas/aplicadas: empate não é um sinal claro o bastante.
    assert result["companies_avoid"] == []
    assert result["companies_favorite"] == []


def test_below_min_count_is_not_suggested() -> None:
    payloads = [_job("https://a.test/1", "Rara")]
    tracking = {"https://a.test/1": _tracked("DISCARDED")}

    result = tracking_insights(payloads, tracking, PROFILE, min_count=2)

    assert result["companies_avoid"] == []


def test_untracked_and_rejected_jobs_are_ignored() -> None:
    payloads = [
        _job("https://a.test/1", "Fora"),  # sem entrada no tracking
        _job("https://a.test/2", "Fora"),
        _job("https://a.test/3", "Fora"),
    ]
    tracking = {
        "https://a.test/2": _tracked("REJECTED"),
        "https://a.test/3": _tracked("REJECTED"),
    }

    result = tracking_insights(payloads, tracking, PROFILE)

    assert result["sample"] == {"saved": 0, "discarded": 0}
    assert result["companies_avoid"] == [] and result["companies_favorite"] == []


def _with(profile: SearchProfile, **overrides) -> SearchProfile:
    from dataclasses import replace

    return replace(profile, **overrides)
