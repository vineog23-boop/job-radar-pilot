from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_radar.models import SearchProfile, WorkplaceModel
from job_radar.preferences import (
    PreferencesError,
    SearchPreferences,
    apply_preferences,
    load_preferences,
    preferences_from_dict,
    preferences_path,
    preferences_to_dict,
    save_preferences,
    validate_preferences_payload,
)


PROFILE = SearchProfile(
    positive_keywords=("java", "spring boot"),
    seniority_levels=("estagio", "junior"),
    location_scopes=("remoto-brasil", "sao-carlos-sp"),
    excluded_terms=("senior",),
)


def test_missing_file_uses_profile_and_current_queries_as_defaults(tmp_path: Path) -> None:
    preferences = load_preferences(
        default_profile=PROFILE,
        default_search_terms=(
            "Java junior",
            "estagio desenvolvimento",
            "java JUNIOR",
        ),
        path=tmp_path / "missing.json",
    )

    assert preferences == SearchPreferences(
        search_terms=("Java junior", "estagio desenvolvimento"),
        seniority_levels=("estagio", "junior"),
        workplace_models=(),
        location_scopes=("remoto-brasil", "sao-carlos-sp"),
        technologies=("java", "spring boot"),
        excluded_terms=("senior",),
    )


def test_save_is_atomic_and_round_trips_only_allowed_fields(tmp_path: Path) -> None:
    path = tmp_path / "JobRadar" / "search-preferences.json"
    preferences = SearchPreferences(
        search_terms=("Java Junior", "Estagio Backend"),
        seniority_levels=("junior",),
        workplace_models=(WorkplaceModel.REMOTE, WorkplaceModel.HYBRID),
        location_scopes=("remoto-brasil", "minas-gerais"),
    )

    assert save_preferences(preferences, path=path) == path

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "search_terms": ["Java Junior", "Estagio Backend"],
        "seniority_levels": ["junior"],
        "workplace_models": ["REMOTE", "HYBRID"],
        "location_scopes": ["remoto-brasil", "minas-gerais"],
        "technologies": [],
        "excluded_terms": [],
        "required_keywords": [],
        "bonus_keywords": [],
        "blocked_keywords": [],
        "excluded_companies": [],
        "favorite_companies": [],
        "contract_types": [],
        "avoid_advanced_english": False,
    }
    assert list(path.parent.glob("*.tmp")) == []
    assert load_preferences(
        default_profile=PROFILE,
        default_search_terms=("ignored",),
        path=path,
    ) == preferences


@pytest.mark.parametrize(
    "payload, expected",
    [
        (
            {
                "search_terms": [],
                "seniority_levels": ["junior"],
                "workplace_models": [],
                "location_scopes": [],
            },
            "search_terms",
        ),
        (
            {
                "search_terms": ["java"] * 13,
                "seniority_levels": ["junior"],
                "workplace_models": [],
                "location_scopes": [],
            },
            "search_terms",
        ),
        (
            {
                "search_terms": ["java"],
                "seniority_levels": ["coordenador"],
                "workplace_models": [],
                "location_scopes": [],
            },
            "seniority_levels",
        ),
        (
            {
                "search_terms": ["java"],
                "seniority_levels": ["junior"],
                "workplace_models": ["ANYWHERE"],
                "location_scopes": [],
            },
            "workplace_models",
        ),
        (
            {
                "search_terms": ["java"],
                "seniority_levels": ["junior"],
                "workplace_models": [],
                "location_scopes": [f"estado-{index}" for index in range(13)],
            },
            "location_scopes",
        ),
        (
            {
                "search_terms": ["java"],
                "seniority_levels": ["junior"],
                "workplace_models": [],
                "location_scopes": [],
                "password": "nao-pode",
            },
            "desconhecidas",
        ),
    ],
)
def test_payload_validation_rejects_out_of_contract_data(
    payload: dict[str, object], expected: str
) -> None:
    with pytest.raises(PreferencesError, match=expected):
        preferences_from_dict(payload)


def test_public_payload_validator_normalizes_valid_ui_input() -> None:
    preferences = validate_preferences_payload(
        {
            "search_terms": ["  Java junior  "],
            "seniority_levels": ["Estágio"],
            "workplace_models": ["REMOTE"],
            "location_scopes": ["  Minas-Gerais  "],
        }
    )

    assert preferences.search_terms == ("Java junior",)
    assert preferences.seniority_levels == ("estagio",)
    assert preferences.workplace_models == (WorkplaceModel.REMOTE,)
    assert preferences.location_scopes == ("minas-gerais",)


def test_malformed_persisted_file_is_not_silently_replaced(tmp_path: Path) -> None:
    path = tmp_path / "search-preferences.json"
    path.write_text('{"search_terms": ["java"], "password": "secret"}', encoding="utf-8")

    with pytest.raises(PreferencesError, match="chaves"):
        load_preferences(
            default_profile=PROFILE,
            default_search_terms=("java",),
            path=path,
        )

    assert "secret" in path.read_text(encoding="utf-8")


def test_apply_preferences_changes_only_editable_search_fields() -> None:
    preferences = SearchPreferences(
        search_terms=("estagio java remoto",),
        seniority_levels=("estagio",),
        workplace_models=(WorkplaceModel.REMOTE,),
        location_scopes=("remoto-brasil",),
    )

    updated = apply_preferences(PROFILE, preferences)

    assert updated.search_terms == ("estagio java remoto",)
    assert updated.seniority_levels == ("estagio",)
    assert updated.workplace_models == (WorkplaceModel.REMOTE,)
    assert updated.location_scopes == ("remoto-brasil",)
    assert updated.positive_keywords == PROFILE.positive_keywords
    assert updated.excluded_terms == PROFILE.excluded_terms
    assert preferences_to_dict(preferences)["workplace_models"] == ["REMOTE"]


def test_default_path_lives_under_local_app_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert preferences_path() == tmp_path / "JobRadar" / "search-preferences.json"


@pytest.mark.parametrize(
    "field, overrides",
    [
        ("seniority_levels", {"seniority_levels": []}),
        ("location_scopes", {"location_scopes": []}),
    ],
)
def test_preferences_require_at_least_one_seniority_and_location(
    field: str, overrides: dict[str, object]
) -> None:
    payload: dict[str, object] = {
        "search_terms": ["java junior"],
        "seniority_levels": ["junior"],
        "workplace_models": [],
        "location_scopes": ["remoto-brasil"],
    }
    payload.update(overrides)

    with pytest.raises(PreferencesError, match=field):
        validate_preferences_payload(payload)


def test_missing_file_exposes_profile_stacks_and_exclusions_as_defaults(
    tmp_path: Path,
) -> None:
    preferences = load_preferences(
        default_profile=PROFILE,
        default_search_terms=("java",),
        path=tmp_path / "missing.json",
    )

    assert preferences.technologies == ("java", "spring boot")
    assert preferences.excluded_terms == ("senior",)


def test_legacy_file_without_stacks_and_exclusions_still_loads(tmp_path: Path) -> None:
    path = tmp_path / "search-preferences.json"
    path.write_text(
        json.dumps(
            {
                "search_terms": ["java"],
                "seniority_levels": ["junior"],
                "workplace_models": [],
                "location_scopes": ["remoto-brasil"],
            }
        ),
        encoding="utf-8",
    )

    preferences = load_preferences(
        default_profile=PROFILE, default_search_terms=("x",), path=path
    )

    assert preferences.technologies == ()
    assert preferences.excluded_terms == ()
    updated = apply_preferences(PROFILE, preferences)
    assert updated.positive_keywords == PROFILE.positive_keywords
    assert updated.excluded_terms == PROFILE.excluded_terms


def test_stacks_and_exclusions_are_normalized_saved_and_applied(tmp_path: Path) -> None:
    preferences = validate_preferences_payload(
        {
            "search_terms": ["java"],
            "seniority_levels": ["junior"],
            "workplace_models": [],
            "location_scopes": ["remoto-brasil"],
            "technologies": ["  Java ", "Spring Boot", "java", "Kotlin"],
            "excluded_terms": ["Pleno", "Sênior", "PHP"],
        }
    )

    assert preferences.technologies == ("java", "spring boot", "kotlin")
    assert preferences.excluded_terms == ("pleno", "sênior", "php")

    path = tmp_path / "prefs.json"
    save_preferences(preferences, path=path)
    loaded = load_preferences(default_profile=PROFILE, default_search_terms=(), path=path)
    assert loaded == preferences

    updated = apply_preferences(PROFILE, preferences)
    assert updated.positive_keywords == ("java", "spring boot", "kotlin")
    assert updated.excluded_terms == ("pleno", "sênior", "php")


@pytest.mark.parametrize("field", ["technologies", "excluded_terms"])
def test_stacks_and_exclusions_have_limits(field: str) -> None:
    payload = {
        "search_terms": ["java"],
        "seniority_levels": ["junior"],
        "workplace_models": [],
        "location_scopes": ["remoto-brasil"],
        field: [f"termo-{index}" for index in range(41)],
    }

    with pytest.raises(PreferencesError, match=field):
        preferences_from_dict(payload)
