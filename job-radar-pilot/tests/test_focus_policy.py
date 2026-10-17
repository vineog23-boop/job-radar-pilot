"""Política opt-in de programação e exceções explícitas de estágio."""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from job_radar.classifier import classify
from job_radar.cleanup import (
    CleanupError,
    CleanupRules,
    discard_reason,
    prune_payloads,
    rules_from_dict,
)
from job_radar.config import ConfigError, load_profile
from job_radar.fit import fit_reasons
from job_radar.models import SearchProfile, VacancyRecord, WorkplaceModel
from job_radar.preferences import (
    PreferencesError,
    apply_preferences,
    load_preferences,
    preferences_from_dict,
    preferences_to_dict,
    save_preferences,
)
from job_radar.reclassify import reclassify_payloads


def _profile(**changes):
    return SearchProfile(
        positive_keywords=("java", "spring boot", "sql"),
        primary_technologies=("java", "spring boot"),
        seniority_levels=("estagio", "junior"),
        location_scopes=("sao-carlos-sp",),
        excluded_terms=("senior", ".net", "c#"),
        development_only=True,
        internship_tracks=("ai", "full_stack"),
        **changes,
    )


def _job(title, description="Java e SQL", **changes):
    return VacancyRecord(
        source="example",
        source_job_id=None,
        canonical_url="https://example.com/job",
        title=title,
        company="Acme",
        description_summary=description,
        location="São Carlos, SP",
        workplace_model=WorkplaceModel.HYBRID,
        **changes,
    )


@pytest.mark.parametrize(
    "title,description,fit,role",
    [
        ("Desenvolvedor Java Junior", "Java e Spring Boot", "READY", "DEVELOPMENT"),
        (
            "Estágio em Inteligência Artificial",
            "Python e machine learning",
            "READY",
            "AI",
        ),
        ("Estágio Full Stack", "React e Node.js", "READY", "DEVELOPMENT"),
        (
            "Analista de Dados Junior",
            "Python e inteligência artificial",
            "EXCLUDE",
            "OTHER",
        ),
        ("Desenvolvedor .NET Junior", "C# e SQL", "EXCLUDE", "DEVELOPMENT"),
        (
            "Suporte Técnico Junior Java",
            "Suporte de sistemas Java e Spring Boot",
            "EXCLUDE",
            "OTHER",
        ),
        ("Desenvolvedor Java Senior", "Java e Spring Boot", "EXCLUDE", "DEVELOPMENT"),
        ("Analista Junior", "SQL e Java", "AMBIGUOUS", "UNKNOWN"),
        ("Analista de BI Junior", "SQL e Java", "EXCLUDE", "OTHER"),
        ("Analista QA Junior", "Automação Java", "EXCLUDE", "OTHER"),
        ("Analista de Infraestrutura Junior", "Java e SQL", "EXCLUDE", "OTHER"),
        ("Engenheiro de IA Junior", "Python e SQL", "EXCLUDE", "AI"),
        (
            "Desenvolvedor Full Stack Junior",
            "React e Node.js",
            "OTHER_STACK",
            "DEVELOPMENT",
        ),
    ],
)
def test_development_focus_requires_role_and_limits_internship_exceptions(
    title, description, fit, role
):
    labels = classify(_job(title, description), _profile()).match_labels
    assert f"FIT:{fit}" in labels
    assert f"ROLE:{role}" in labels
    if role == "OTHER" or (role == "AI" and "Estágio" not in title):
        assert "ROLE_MISMATCH:outside_development" in labels


@pytest.mark.parametrize(
    "title", ["Trainee em Inteligência Artificial", "Aprendiz Full Stack"]
)
def test_internship_exception_does_not_expand_to_trainee_or_apprentice(title):
    labels = classify(_job(title, "Python e React"), _profile()).match_labels
    assert "FIT:READY" not in labels
    assert not any(label.startswith("INTERNSHIP_TRACK:") for label in labels)


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"location": "Curitiba, PR"}, "LOCATION_MISMATCH:outside_scope"),
        ({"title": "Estágio Full Stack .NET"}, "TITLE_EXCLUDED:.net"),
        ({"title": "Estágio Full Stack Senior"}, "SENIORITY_MISMATCH:senior"),
    ],
)
def test_internship_exceptions_keep_hard_exclusions(changes, reason):
    job = replace(_job("Estágio Full Stack", "React e Node.js"), **changes)
    labels = classify(job, _profile()).match_labels
    assert "FIT:EXCLUDE" in labels
    assert reason in labels


def test_internship_tracks_must_be_enabled_and_do_not_override_workplace():
    profile = replace(_profile(), internship_tracks=())
    assert (
        "FIT:READY"
        not in classify(
            _job("Estágio Full Stack", "React e Node"), profile
        ).match_labels
    )
    profile = replace(_profile(), workplace_models=(WorkplaceModel.REMOTE,))
    assert (
        "FIT:EXCLUDE" in classify(_job("Estágio em IA", "Python"), profile).match_labels
    )


def test_generic_profiles_keep_support_sql_and_other_seniority_valid():
    profile = SearchProfile(
        positive_keywords=("sql",),
        primary_technologies=("sql",),
        seniority_levels=("junior",),
        location_scopes=("sao-carlos-sp",),
    )
    labels = classify(_job("Analista de Suporte Junior", "SQL"), profile).match_labels
    assert "FIT:READY" in labels
    assert not any(label.startswith("ROLE:") for label in labels)


def test_reclassify_removes_old_role_labels_and_cleans_legacy_description():
    job = _job(
        "Desenvolvedor Python Junior",
        "Python. Dicas importantes: use Java e Spring Boot",
    )
    from dataclasses import asdict

    payload = asdict(job)
    payload["match_labels"] = [
        "ROLE:OTHER",
        "ROLE_MISMATCH:outside_development",
        "INTERNSHIP_TRACK:ai",
        "STATUS:NEW",
    ]
    updated = reclassify_payloads([payload], _profile())[0]
    assert updated["description_summary"] == "Python."
    assert "TECH_MATCH:java" not in updated["match_labels"]
    assert "FIT:OTHER_STACK" in updated["match_labels"]
    assert "ROLE:DEVELOPMENT" in updated["match_labels"]
    assert "ROLE:OTHER" not in updated["match_labels"]
    assert "ROLE_MISMATCH:outside_development" not in updated["match_labels"]
    assert "INTERNSHIP_TRACK:ai" not in updated["match_labels"]
    assert "STATUS:NEW" in updated["match_labels"]


def _preferences_payload():
    return {
        "search_terms": ["java junior"],
        "seniority_levels": ["junior"],
        "workplace_models": [],
        "location_scopes": ["sao-carlos-sp"],
        "development_only": True,
        "internship_tracks": ["ai", "full_stack"],
    }


def test_focus_preferences_round_trip_apply_and_missing_defaults(tmp_path):
    prefs = preferences_from_dict(_preferences_payload())
    assert prefs.development_only is True
    assert prefs.internship_tracks == ("ai", "full_stack")
    payload = preferences_to_dict(prefs)
    assert payload["development_only"] is True
    assert payload["internship_tracks"] == ["ai", "full_stack"]
    saved = save_preferences(prefs, tmp_path / "prefs.json")
    assert (
        load_preferences(
            default_profile=_profile(), default_search_terms=("java",), path=saved
        )
        == prefs
    )
    applied = apply_preferences(_profile(), prefs)
    assert applied.development_only is True and applied.internship_tracks == (
        "ai",
        "full_stack",
    )
    defaults = load_preferences(
        default_profile=_profile(),
        default_search_terms=("java",),
        path=tmp_path / "missing.json",
    )
    assert defaults.development_only is True and defaults.internship_tracks == (
        "ai",
        "full_stack",
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"development_only": "true"},
        {"internship_tracks": ["data"]},
        {"internship_tracks": "ai"},
    ],
)
def test_invalid_focus_preferences_are_rejected(changes):
    with pytest.raises(PreferencesError):
        preferences_from_dict({**_preferences_payload(), **changes})


def _yaml(extra):
    return (
        "positive_keywords: [java]\nseniority_levels: [junior]\nlocation_scopes: [sao-carlos-sp]\nsearch_terms: [java]\nprimary_technologies: [java]\n"
        + extra
    )


def test_yaml_focus_policy_is_optional_and_loaded(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        _yaml("development_only: true\ninternship_tracks: [ai, full_stack]\n")
    )
    profile = load_profile(path)
    assert profile.development_only is True
    assert profile.internship_tracks == ("ai", "full_stack")
    path.write_text(_yaml(""))
    profile = load_profile(path)
    assert profile.development_only is False and profile.internship_tracks == ()


@pytest.mark.parametrize(
    "extra",
    [
        "development_only: yesplease\n",
        "internship_tracks: [data]\n",
        "internship_tracks: ai\n",
    ],
)
def test_yaml_rejects_invalid_focus_policy(tmp_path, extra):
    path = tmp_path / "profile.yaml"
    path.write_text(_yaml(extra))
    with pytest.raises(ConfigError):
        load_profile(path)


def test_other_stack_cleanup_opt_in_round_trip_preserves_tracked_records():
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    other = {
        "canonical_url": "https://example.com/a",
        "match_labels": ["FIT:OTHER_STACK"],
    }
    assert discard_reason(other, now=now) is None
    rules = rules_from_dict({"other_stack": True})
    assert rules.to_dict()["other_stack"] is True
    assert "other_stack" not in CleanupRules().to_dict()
    assert discard_reason(other, now=now, rules=rules) == "other_stack"
    removed = []
    kept, counts = prune_payloads(
        [other],
        keep_urls={other["canonical_url"]},
        now=now,
        rules=rules,
        removed_jobs=removed,
    )
    assert kept == [other] and counts == {} and removed == []
    kept, counts = prune_payloads([other], now=now, rules=rules, removed_jobs=removed)
    assert kept == [] and counts == {"other_stack": 1} and removed == [other]
    assert discard_reason(other, now=now, rules=rules, max_age_days=30) == "other_stack"
    with pytest.raises(CleanupError):
        rules_from_dict({"other_stack": "yes"})


def test_cleanup_expired_uses_recent_dead_link_evidence():
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    job = {
        "match_labels": [
            "FIT:READY",
            "LINK:DEAD",
            "LINK_CHECKED_AT:2026-10-16T12:00:00+00:00",
        ]
    }
    assert discard_reason(job, now=now) == "expired"
    assert discard_reason(job, now=now, rules=CleanupRules(expired=False)) is None
    job["match_labels"][-1] = "LINK_CHECKED_AT:2026-09-01T00:00:00+00:00"
    assert discard_reason(job, now=now) is None


def test_focus_reason_explains_outside_development():
    assert "fora do foco de programação" in fit_reasons(
        ["FIT:EXCLUDE", "ROLE_MISMATCH:outside_development"]
    )


@pytest.mark.parametrize(
    "title,level",
    [("Desenvolvedor Java PL", "pleno"), ("Desenvolvedor Java SR", "senior")],
)
def test_development_focus_rejects_abbreviated_higher_levels(title, level):
    labels = classify(_job(title), _profile()).match_labels
    assert "FIT:EXCLUDE" in labels
    assert f"SENIORITY_MISMATCH:{level}" in labels


def test_generic_internship_with_incidental_ai_is_not_an_authorized_track():
    labels = classify(
        _job("Estágio de TI", "Apoio ao time com SQL e IA"), _profile()
    ).match_labels
    assert "FIT:AMBIGUOUS" in labels
    assert not any(label.startswith("INTERNSHIP_TRACK:") for label in labels)


@pytest.mark.parametrize(
    "title",
    [
        "Analista de Qualidade de Software Junior",
        "Software Test Engineer Junior",
        "Infrastructure Engineer Junior",
        "Security Analyst Junior",
        "Database Administrator Junior",
    ],
)
def test_explicit_non_development_roles_cannot_be_rescued_by_java_sql(title):
    labels = classify(_job(title), _profile()).match_labels
    assert "ROLE:OTHER" in labels
    assert "ROLE_MISMATCH:outside_development" in labels
    assert "FIT:EXCLUDE" in labels


def test_generic_software_title_does_not_prove_development_role():
    labels = classify(_job("Analista de Software Junior"), _profile()).match_labels
    assert "ROLE:UNKNOWN" in labels
    assert "FIT:AMBIGUOUS" in labels


@pytest.mark.parametrize(
    "title",
    [
        "Software Engineer Junior",
        "Engenheiro de Software Junior",
        "Estágio em Software",
    ],
)
def test_explicit_software_engineering_or_internship_proves_development_role(title):
    labels = classify(_job(title), _profile()).match_labels
    assert "ROLE:DEVELOPMENT" in labels
    assert "FIT:READY" in labels


def test_pl_sql_in_title_is_not_a_pleno_seniority_abbreviation():
    labels = classify(_job("Desenvolvedor Java Junior PL/SQL"), _profile()).match_labels
    assert "FIT:READY" in labels
    assert "SENIORITY_MISMATCH:pleno" not in labels


@pytest.mark.parametrize(
    "title,level",
    [
        ("Desenvolvedor Java Junior SR", "senior"),
        ("Desenvolvedor Java Junior PL", "pleno"),
    ],
)
def test_focus_higher_level_is_not_cancelled_by_an_entry_level_marker(title, level):
    profile = replace(_profile(), excluded_terms=())
    labels = classify(_job(title), profile).match_labels
    assert "FIT:EXCLUDE" in labels
    assert f"SENIORITY_MISMATCH:{level}" in labels


def test_legacy_internship_seniority_does_not_authorize_ai_trainee_junior():
    job = _job(
        "Profissional Fullstack (IA/Javascript) Trainee/Júnior - Remoto",
        "Javascript e IA",
        seniority="estagio",
    )
    labels = classify(job, _profile()).match_labels
    assert "FIT:READY" not in labels
    assert "INTERNSHIP_TRACK:ai" not in labels
    assert "INTERNSHIP_TRACK:full_stack" not in labels


@pytest.mark.parametrize(
    "title",
    [
        "Estágio em Contabilidade: Dados e Inteligência Artificial",
        "Estágio em Finanças e IA",
        "Estágio RH com IA",
        "Estágio Marketing e IA",
        "Estágio em Negócios e IA",
    ],
)
def test_business_internship_mentioning_ai_is_outside_programming_focus(title):
    labels = classify(
        _job(title, "Aprendizado com ferramentas de IA"), _profile()
    ).match_labels
    assert "ROLE:OTHER" in labels
    assert "FIT:EXCLUDE" in labels
    assert not any(label.startswith("INTERNSHIP_TRACK:") for label in labels)


@pytest.mark.parametrize("title", ["Analista de IA Junior", "Profissional de IA"])
def test_generic_ai_role_without_internship_or_development_is_unconfirmed(title):
    labels = classify(_job(title, "Python e IA"), _profile()).match_labels
    assert "ROLE:UNKNOWN" in labels
    assert "FIT:AMBIGUOUS" in labels


@pytest.mark.parametrize(
    "title,description",
    [
        ("Estágio Full Stack", "Desenvolvimento C# e ASP.NET, SQL Server"),
        ("Estágio em IA", "Requisito obrigatório: C# e .NET"),
        ("Estágio em Inteligência Artificial", "Aplicações com dotnet e Python"),
    ],
)
def test_internship_exception_keeps_rejected_dotnet_stack_in_relevant_body(
    title, description
):
    labels = classify(_job(title, description), _profile()).match_labels
    assert "FIT:EXCLUDE" in labels
    assert any(
        label in labels for label in ("KEYWORD_BLOCKED:.net", "KEYWORD_BLOCKED:c#")
    )


def test_ordinary_java_development_is_not_blocked_by_support_in_body():
    labels = classify(
        _job("Desenvolvedor Java Junior", "Java e Spring Boot; suporte às aplicações"),
        _profile(),
    ).match_labels
    assert "FIT:READY" in labels


def test_recommended_dotnet_course_does_not_block_a_fullstack_internship():
    labels = classify(
        _job(
            "Estágio Full Stack",
            "Desenvolvimento com React. Dicas importantes: curso de .NET e C#",
        ),
        _profile(),
    ).match_labels
    assert "FIT:READY" in labels


def test_rejected_dotnet_stack_also_blocks_aspnet_in_internship_body():
    labels = classify(
        _job("Estágio Full Stack", "Desenvolvimento web ASP.NET e SQL Server"),
        _profile(),
    ).match_labels
    assert "FIT:EXCLUDE" in labels
    assert "KEYWORD_BLOCKED:.net" in labels


@pytest.mark.parametrize(
    "onsite_scopes,wanted",
    [
        (("sao-carlos-sp",), "CONDITIONAL"),
        (("sp",), "READY"),
    ],
)
def test_multiple_workplace_models_only_ready_when_every_regional_option_fits(
    onsite_scopes, wanted
):
    profile = replace(
        _profile(),
        location_scopes=("brasil",),
        workplace_models=(
            WorkplaceModel.REMOTE,
            WorkplaceModel.HYBRID,
            WorkplaceModel.ONSITE,
        ),
        workplace_location_scopes=(("HYBRID", ("sp",)), ("ONSITE", onsite_scopes)),
    )
    job = replace(
        _job(
            "Estágio em Desenvolvimento e IA",
            "Local São Paulo - SP; Presencial ou Híbrido",
        ),
        location="São Paulo, SP",
        workplace_model=WorkplaceModel.UNKNOWN,
    )
    labels = classify(job, profile).match_labels
    assert f"FIT:{wanted}" in labels
    assert "WORKPLACE_UNCLEAR:multiple" in labels


@pytest.mark.parametrize('body', [
    'Desenvolvimento Java e Spring. Nível de exigência de atuação Pleno.',
    'Java e Spring. Vaga afirmativa para mulheres. Remoto no Brasil.',
])
def test_explicit_restriction_in_description_needs_review(body):
    result = classify(_job('Desenvolvedor Java Júnior', body), _profile())
    assert 'FIT:CONDITIONAL' in result.match_labels
