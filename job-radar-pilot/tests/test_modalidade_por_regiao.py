"""Modalidade por região (10/10/2026): o local permitido depende do modelo de trabalho.

Critério do usuário: remoto no Brasil todo; híbrido só no estado de SP (e na Grande
Florianópolis); presencial só em São Carlos/SP e na Grande Florianópolis/SC."""

from __future__ import annotations

from dataclasses import replace

import pytest

from job_radar.classifier import classify
from job_radar.fit import fit_state
from job_radar.models import SearchProfile, VacancyRecord, WorkplaceModel
from job_radar.preferences import (
    PreferencesError,
    apply_preferences,
    preferences_from_dict,
    preferences_to_dict,
)

REGIOES = {
    "HYBRID": ["sp", "florianopolis-sc", "sao-jose-sc", "palhoca-sc", "biguacu-sc"],
    "ONSITE": ["sao-carlos-sp", "florianopolis-sc", "sao-jose-sc", "palhoca-sc", "biguacu-sc"],
}

PROFILE = SearchProfile(
    positive_keywords=("java", "spring boot"),
    seniority_levels=("estagio", "junior"),
    location_scopes=("remoto-brasil", "brasil", "sao-carlos-sp", "florianopolis-sc"),
    excluded_terms=("senior",),
    workplace_models=(WorkplaceModel.REMOTE, WorkplaceModel.HYBRID, WorkplaceModel.ONSITE),
    workplace_location_scopes=tuple((k, tuple(v)) for k, v in REGIOES.items()),
)


def _record(location: str, workplace: WorkplaceModel) -> VacancyRecord:
    return VacancyRecord(
        source="example", source_job_id="1", canonical_url="https://jobs.example.com/1",
        title="Desenvolvedor Java Júnior", company="Acme", description_summary="Java e Spring Boot",
        location=location, workplace_model=workplace, evidence_snippets=("Java",),
    )


@pytest.mark.parametrize(
    ("location", "workplace"),
    [
        ("Curitiba, PR", WorkplaceModel.HYBRID),
        ("Rio de Janeiro, RJ", WorkplaceModel.HYBRID),
        ("São Paulo, SP", WorkplaceModel.ONSITE),
        ("Campinas, SP", WorkplaceModel.ONSITE),
    ],
)
def test_outside_the_region_of_its_workplace_is_excluded(location, workplace) -> None:
    result = classify(_record(location, workplace), PROFILE, default_country="BR")
    assert fit_state(result.match_labels) == "EXCLUDE"
    assert f"REGION_MISMATCH:{workplace.value.lower()}" in result.match_labels


@pytest.mark.parametrize(
    ("location", "workplace"),
    [
        ("Campinas, SP", WorkplaceModel.HYBRID),
        ("São Paulo, SP", WorkplaceModel.HYBRID),
        ("São Carlos, SP", WorkplaceModel.ONSITE),
        ("Florianópolis, SC", WorkplaceModel.ONSITE),
        ("Brasil", WorkplaceModel.REMOTE),
    ],
)
def test_inside_the_region_is_not_excluded_by_the_rule(location, workplace) -> None:
    result = classify(_record(location, workplace), PROFILE, default_country="BR")
    assert not any(label.startswith("REGION_MISMATCH:") for label in result.match_labels)


def test_without_the_rule_behaviour_is_unchanged() -> None:
    plain = replace(PROFILE, workplace_location_scopes=())
    result = classify(_record("Curitiba, PR", WorkplaceModel.HYBRID), plain, default_country="BR")
    assert not any(label.startswith("REGION_MISMATCH:") for label in result.match_labels)


def _prefs(**extra) -> dict:
    return {
        "search_terms": ["java junior"], "seniority_levels": ["junior"],
        "workplace_models": ["REMOTE", "HYBRID"], "location_scopes": ["brasil"], **extra,
    }


def test_preferences_roundtrip_and_profile() -> None:
    prefs = preferences_from_dict(_prefs(workplace_location_scopes=REGIOES))
    assert preferences_to_dict(prefs)["workplace_location_scopes"] == REGIOES
    profile = apply_preferences(PROFILE, prefs)
    assert dict(profile.workplace_location_scopes)["HYBRID"][0] == "sp"


def test_preferences_without_the_rule_stay_valid() -> None:
    assert "workplace_location_scopes" not in preferences_to_dict(preferences_from_dict(_prefs()))


@pytest.mark.parametrize(
    "bad",
    [{"LUA": ["sp"]}, {"HYBRID": []}, {"HYBRID": "sp"}, ["sp"]],
)
def test_preferences_reject_invalid_rule(bad) -> None:
    with pytest.raises(PreferencesError, match="workplace_location_scopes"):
        preferences_from_dict(_prefs(workplace_location_scopes=bad))
