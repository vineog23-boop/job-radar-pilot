from __future__ import annotations

from job_radar.models import WorkplaceModel
from job_radar.preferences import SearchPreferences


def test_linkedin_plan_uses_only_official_home_and_copyable_terms() -> None:
    from job_radar.manual_search import build_linkedin_search_plan

    preferences = SearchPreferences(
        search_terms=("Java junior", "estágio backend"),
        seniority_levels=("estagio", "junior"),
        workplace_models=(WorkplaceModel.REMOTE,),
        location_scopes=("remoto-brasil", "florianopolis-sc"),
    )

    plan = build_linkedin_search_plan(preferences)

    assert plan["access_mode"] == "MANUAL_FOREGROUND"
    assert plan["portal"] == "LinkedIn"
    assert plan["home_url"] == "https://www.linkedin.com/"
    assert plan["network_access"] is False
    assert [item["label"] for item in plan["searches"]] == [
        "Java junior",
        "estágio backend",
    ]
    assert all(set(item) == {"label"} for item in plan["searches"])


def test_linkedin_plan_is_bounded_by_validated_preferences() -> None:
    from job_radar.manual_search import build_linkedin_search_plan

    preferences = SearchPreferences(
        search_terms=tuple(f"termo {index}" for index in range(12)),
        seniority_levels=("junior",),
        workplace_models=(),
        location_scopes=("brasil",),
    )

    plan = build_linkedin_search_plan(preferences)

    assert len(plan["searches"]) == 12
    assert plan["filters"]["seniority_levels"] == ["junior"]
    assert plan["filters"]["workplace_models"] == []
    assert plan["filters"]["location_scopes"] == ["brasil"]
