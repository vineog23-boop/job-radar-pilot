from __future__ import annotations

import pytest

from job_radar.classifier import classify
from job_radar.models import SearchProfile, VacancyRecord, WorkplaceModel


PROFILE = SearchProfile(
    positive_keywords=("java", "spring boot", "api rest"),
    seniority_levels=("estagio", "junior"),
    location_scopes=("remoto-brasil", "sao-carlos-sp"),
    excluded_terms=("senior", "especialista"),
)

BACKEND_PROFILE = SearchProfile(
    positive_keywords=("backend",),
    seniority_levels=("junior",),
    location_scopes=("sao-carlos-sp",),
    excluded_terms=("senior",),
)

SQL_PROFILE = SearchProfile(
    positive_keywords=("sql",),
    seniority_levels=("junior",),
    location_scopes=("sao-carlos-sp",),
    excluded_terms=("senior",),
)


def _record(**overrides: object) -> VacancyRecord:
    values: dict[str, object] = {
        "source": "example",
        "source_job_id": "123",
        "canonical_url": "https://jobs.example.com/123",
        "title": "Estágio em Desenvolvimento Java",
        "company": "Acme",
        "description_summary": "APIs com Spring Boot",
        "location": "São Carlos, SP",
        "workplace_model": WorkplaceModel.HYBRID,
        "evidence_snippets": ("Conhecimento em Java",),
        "published_at": None,
        "application_deadline": None,
    }
    values.update(overrides)
    return VacancyRecord(**values)  # type: ignore[arg-type]


def test_classify_matches_utf8_technology_seniority_and_location() -> None:
    original = _record()

    classified = classify(original, PROFILE)

    assert "TECH_MATCH:java" in classified.match_labels
    assert "TECH_MATCH:spring boot" in classified.match_labels
    assert "SENIORITY_MATCH:estagio" in classified.match_labels
    assert "LOCATION_MATCH:sao-carlos-sp" in classified.match_labels
    assert "FIT:READY" in classified.match_labels
    assert "FIT_SCORE:3" in classified.match_labels
    assert classified.evidence_snippets == original.evidence_snippets
    assert not any(label.startswith("SCORE:") for label in classified.match_labels)


def test_classify_marks_incompatible_seniority() -> None:
    classified = classify(
        _record(title="Pessoa Desenvolvedora Java Sênior"),
        PROFILE,
    )

    assert "SENIORITY_MISMATCH:senior" in classified.match_labels
    assert "FIT:EXCLUDE" in classified.match_labels
    assert "FIT_SCORE:-1" in classified.match_labels


def test_classify_recognizes_sr_as_senior_mismatch() -> None:
    classified = classify(_record(title="Desenvolvedor Java Sr."), PROFILE)

    assert "SENIORITY_MISMATCH:senior" in classified.match_labels
    assert "FIT:EXCLUDE" in classified.match_labels


def test_classify_keeps_remote_without_country_uncertain() -> None:
    classified = classify(
        _record(
            title="Java Junior remoto",
            location=None,
            workplace_model=WorkplaceModel.REMOTE,
            remote_scope=None,
        ),
        PROFILE,
    )

    assert "SENIORITY_MATCH:junior" in classified.match_labels
    assert "LOCATION_UNCLEAR:remote_scope" in classified.match_labels
    assert "LOCATION_MATCH:remote_brazil" not in classified.match_labels
    assert "FIT:CONDITIONAL" in classified.match_labels
    assert "FIT:READY" not in classified.match_labels


def test_classify_uses_brazilian_source_default_for_remote_without_country() -> None:
    classified = classify(
        _record(
            title="Java Junior remoto",
            location="Remoto",
            workplace_model=WorkplaceModel.REMOTE,
            remote_scope=None,
        ),
        PROFILE,
        default_country="BR",
    )

    assert "LOCATION_MATCH:remote_brazil" in classified.match_labels
    assert "LOCATION_UNCLEAR:remote_scope" not in classified.match_labels
    assert "FIT:READY" in classified.match_labels


def test_classify_does_not_use_brazilian_default_for_explicit_foreign_country() -> None:
    classified = classify(
        _record(
            title="Java Junior remoto",
            location="Remoto - Portugal",
            workplace_model=WorkplaceModel.REMOTE,
            remote_scope="Portugal",
        ),
        PROFILE,
        default_country="BR",
    )

    assert "LOCATION_MATCH:remote_brazil" not in classified.match_labels
    assert "LOCATION_UNCLEAR:remote_scope" in classified.match_labels
    assert "FIT:READY" not in classified.match_labels


def test_classify_preserves_adaptive_extraction_with_brazilian_remote_match() -> None:
    classified = classify(
        _record(
            title="Java Junior remoto",
            location="Remoto",
            workplace_model=WorkplaceModel.REMOTE,
            match_labels=("EXTRACTION:ADAPTIVE", "FIT:EXCLUDE", "TECH_MATCH:go"),
        ),
        PROFILE,
        default_country="BR",
    )

    assert "EXTRACTION:ADAPTIVE" in classified.match_labels
    assert "LOCATION_MATCH:remote_brazil" in classified.match_labels
    assert "FIT:READY" in classified.match_labels
    assert "FIT:EXCLUDE" not in classified.match_labels
    assert "TECH_MATCH:go" not in classified.match_labels


def test_classify_preserves_adaptive_extraction_with_foreign_scope_unclear() -> None:
    classified = classify(
        _record(
            title="Java Junior remoto",
            location="Remoto - Portugal",
            remote_scope="Portugal",
            workplace_model=WorkplaceModel.REMOTE,
            match_labels=("EXTRACTION:ADAPTIVE",),
        ),
        PROFILE,
        default_country="BR",
    )

    assert "EXTRACTION:ADAPTIVE" in classified.match_labels
    assert "LOCATION_UNCLEAR:remote_scope" in classified.match_labels
    assert "LOCATION_MATCH:remote_brazil" not in classified.match_labels


@pytest.mark.parametrize("remote_scope", ("Remoto", "Brasil"))
def test_classify_keeps_conflicting_foreign_location_unclear(
    remote_scope: str,
) -> None:
    classified = classify(
        _record(
            title="Java Junior remoto",
            location="Portugal",
            workplace_model=WorkplaceModel.REMOTE,
            remote_scope=remote_scope,
        ),
        PROFILE,
        default_country="BR",
    )

    assert "LOCATION_MATCH:remote_brazil" not in classified.match_labels
    assert "LOCATION_UNCLEAR:remote_scope" in classified.match_labels
    assert "FIT:READY" not in classified.match_labels


def test_classify_does_not_use_brazilian_default_for_usa_alias() -> None:
    classified = classify(
        _record(
            title="Java Junior remoto",
            location="Remote - USA",
            workplace_model=WorkplaceModel.REMOTE,
            remote_scope="USA",
        ),
        PROFILE,
        default_country="BR",
    )

    assert "LOCATION_MATCH:remote_brazil" not in classified.match_labels
    assert "LOCATION_UNCLEAR:remote_scope" in classified.match_labels
    assert "FIT:READY" not in classified.match_labels


@pytest.mark.parametrize(
    "foreign_country",
    ("Suíça", "Noruega", "África do Sul", "Romênia"),
)
def test_classify_keeps_unknown_geographic_scope_unclear(
    foreign_country: str,
) -> None:
    classified = classify(
        _record(
            title="Java Junior remoto",
            location=f"Remote - {foreign_country}",
            workplace_model=WorkplaceModel.REMOTE,
            remote_scope=foreign_country,
        ),
        PROFILE,
        default_country="BR",
    )

    assert "LOCATION_MATCH:remote_brazil" not in classified.match_labels
    assert "LOCATION_UNCLEAR:remote_scope" in classified.match_labels
    assert "FIT:READY" not in classified.match_labels


@pytest.mark.parametrize("location", ("Recife, PE", "Vitória, ES"))
def test_classify_does_not_confuse_brazilian_state_with_foreign_country_code(
    location: str,
) -> None:
    classified = classify(
        _record(
            title="Java Junior remoto",
            location=location,
            workplace_model=WorkplaceModel.REMOTE,
            remote_scope=None,
        ),
        PROFILE,
        default_country="BR",
    )

    assert "LOCATION_MATCH:remote_brazil" in classified.match_labels
    assert "FIT:READY" in classified.match_labels


def test_classify_infers_remote_brazil_from_explicit_location_text() -> None:
    classified = classify(
        _record(
            title="Desenvolvedor Java Jr",
            location="Remoto - Brasil",
            workplace_model=WorkplaceModel.UNKNOWN,
            remote_scope=None,
        ),
        PROFILE,
    )

    assert "LOCATION_MATCH:remote_brazil" in classified.match_labels
    assert "FIT:READY" in classified.match_labels


def test_classify_marks_missing_location_without_inventing_dates() -> None:
    classified = classify(_record(location=None), PROFILE)

    assert "LOCATION_UNCLEAR:missing" in classified.match_labels
    assert classified.published_at is None
    assert classified.application_deadline is None


@pytest.mark.parametrize(
    "location",
    (
        "Brasil",
        "Localidade: Diversas",
        "São Paulo / SP A empresa aceita candidaturas de qualquer cidade do Brasil",
    ),
)
def test_classify_keeps_generic_brazilian_location_unclear(location: str) -> None:
    classified = classify(
        _record(title="Desenvolvedor Java Junior", location=location),
        PROFILE,
    )

    assert "LOCATION_UNCLEAR:multiple" in classified.match_labels
    assert "LOCATION_MISMATCH:outside_scope" not in classified.match_labels
    assert "FIT:EXCLUDE" not in classified.match_labels


def test_classify_keeps_diversas_location_unclear() -> None:
    classified = classify(
        _record(title="Desenvolvedor Java Junior", location="Diversas"),
        PROFILE,
    )

    assert "LOCATION_UNCLEAR:multiple" in classified.match_labels
    assert "LOCATION_MISMATCH:outside_scope" not in classified.match_labels


def test_classify_keeps_diversas_localidades_location_unclear() -> None:
    classified = classify(
        _record(
            title="Desenvolvedor Java Junior",
            location="Diversas localidades",
        ),
        PROFILE,
    )

    assert "LOCATION_UNCLEAR:multiple" in classified.match_labels
    assert "LOCATION_MISMATCH:outside_scope" not in classified.match_labels


def test_classify_keeps_any_brazilian_city_location_unclear() -> None:
    classified = classify(
        _record(
            title="Desenvolvedor Java Junior",
            location="Qualquer cidade do Brasil",
        ),
        PROFILE,
    )

    assert "LOCATION_UNCLEAR:multiple" in classified.match_labels
    assert "LOCATION_MISMATCH:outside_scope" not in classified.match_labels


def test_classify_does_not_match_java_inside_javascript() -> None:
    classified = classify(
        _record(
            title="Desenvolvedor JavaScript Junior",
            description_summary=None,
            evidence_snippets=(),
        ),
        PROFILE,
    )

    assert "TECH_MATCH:java" not in classified.match_labels
    assert "FIT:AMBIGUOUS" in classified.match_labels


def test_classify_does_not_match_sql_inside_nosql() -> None:
    classified = classify(
        _record(
            title="Desenvolvedor NoSQL Junior",
            description_summary=None,
            evidence_snippets=(),
        ),
        SQL_PROFILE,
    )

    assert "TECH_MATCH:sql" not in classified.match_labels
    assert "FIT:AMBIGUOUS" in classified.match_labels


def test_classify_recognizes_backend_and_junior_aliases() -> None:
    aliases = (
        ("Back-End", "Jr."),
        ("Back End", "Júnior"),
        ("Backend", "Junior"),
    )

    for backend_alias, junior_alias in aliases:
        classified = classify(
            _record(
                title=f"Desenvolvedor {backend_alias} {junior_alias}",
                description_summary=None,
                evidence_snippets=(),
            ),
            BACKEND_PROFILE,
        )

        assert "TECH_MATCH:backend" in classified.match_labels
        assert "SENIORITY_MATCH:junior" in classified.match_labels
        assert "FIT:READY" in classified.match_labels


def test_classify_marks_technology_without_all_gates_conditional() -> None:
    classified = classify(
        _record(
            title="Desenvolvedor Java",
            description_summary=None,
            location=None,
            evidence_snippets=(),
        ),
        PROFILE,
    )

    assert "TECH_MATCH:java" in classified.match_labels
    assert "FIT:CONDITIONAL" in classified.match_labels


def test_classify_marks_android_title_without_positive_technology_ambiguous() -> None:
    classified = classify(
        _record(
            title="Desenvolvedor Android Junior",
            description_summary=None,
            evidence_snippets=(),
        ),
        PROFILE,
    )

    assert "SENIORITY_MATCH:junior" in classified.match_labels
    assert not any(label.startswith("TECH_MATCH:") for label in classified.match_labels)
    assert "FIT:AMBIGUOUS" in classified.match_labels


def test_classify_does_not_promote_supporting_skill_without_backend_anchor() -> None:
    profile = SearchProfile(
        positive_keywords=("testes", "docker"),
        seniority_levels=("junior",),
        location_scopes=("sao-carlos-sp",),
    )

    classified = classify(
        _record(
            title="Desenvolvedor de Software Junior",
            description_summary="Testes automatizados e Docker",
        ),
        profile,
    )

    assert "TECH_MATCH:testes" in classified.match_labels
    assert "FIT:AMBIGUOUS" in classified.match_labels
    assert "FIT:CONDITIONAL" not in classified.match_labels


def test_classify_keeps_restricted_audience_role_conditional_without_profile_evidence() -> None:
    classified = classify(
        _record(title="Desenvolvedor Java Júnior - PCD"),
        PROFILE,
    )

    assert "ELIGIBILITY_UNCLEAR:restricted_audience" in classified.match_labels
    assert "FIT:CONDITIONAL" in classified.match_labels
    assert "FIT:READY" not in classified.match_labels
    assert "FIT:READY" not in classified.match_labels


def test_classify_never_promotes_editorial_article_without_detail_validation() -> None:
    classified = classify(
        _record(
            source="otrainee",
            title="Programa Java Junior remoto Brasil",
            location="Remoto - Brasil",
            workplace_model=WorkplaceModel.UNKNOWN,
        ),
        PROFILE,
    )

    assert "SOURCE_TYPE:CURATED_ARTICLE" in classified.match_labels
    assert "FIT:AMBIGUOUS" in classified.match_labels
    assert "FIT:READY" not in classified.match_labels


def test_classify_adds_exactly_one_fit_and_one_integer_score() -> None:
    classified = classify(_record(), PROFILE)

    fit_labels = [label for label in classified.match_labels if label.startswith("FIT:")]
    score_labels = [label for label in classified.match_labels if label.startswith("FIT_SCORE:")]

    assert fit_labels == ["FIT:READY"]
    assert len(score_labels) == 1
    assert score_labels[0].removeprefix("FIT_SCORE:").lstrip("-").isdigit()


def test_classify_confirms_selected_remote_model_from_factual_text() -> None:
    profile = SearchProfile(
        positive_keywords=PROFILE.positive_keywords,
        seniority_levels=PROFILE.seniority_levels,
        location_scopes=PROFILE.location_scopes,
        excluded_terms=PROFILE.excluded_terms,
        workplace_models=(WorkplaceModel.REMOTE,),
    )

    classified = classify(
        _record(
            title="Desenvolvedor Java Junior",
            description_summary="Trabalho 100% remoto em todo o Brasil",
            location="Remoto - Brasil",
            workplace_model=WorkplaceModel.UNKNOWN,
        ),
        profile,
    )

    assert "WORKPLACE_MATCH:REMOTE" in classified.match_labels
    assert "FIT:READY" in classified.match_labels
    assert "FIT_SCORE:4" in classified.match_labels


def test_classify_excludes_confirmed_workplace_mismatch() -> None:
    profile = SearchProfile(
        positive_keywords=PROFILE.positive_keywords,
        seniority_levels=PROFILE.seniority_levels,
        location_scopes=PROFILE.location_scopes,
        excluded_terms=PROFILE.excluded_terms,
        workplace_models=(WorkplaceModel.REMOTE,),
    )

    classified = classify(
        _record(
            title="Desenvolvedor Java Junior",
            description_summary="Atuacao presencial no escritorio",
            workplace_model=WorkplaceModel.UNKNOWN,
        ),
        profile,
    )

    assert "WORKPLACE_MISMATCH:ONSITE" in classified.match_labels
    assert "FIT:EXCLUDE" in classified.match_labels
    assert "FIT:READY" not in classified.match_labels


def test_classify_does_not_promote_when_selected_workplace_is_unclear() -> None:
    profile = SearchProfile(
        positive_keywords=PROFILE.positive_keywords,
        seniority_levels=PROFILE.seniority_levels,
        location_scopes=PROFILE.location_scopes,
        excluded_terms=PROFILE.excluded_terms,
        workplace_models=(WorkplaceModel.HYBRID,),
    )

    classified = classify(
        _record(
            title="Desenvolvedor Java Junior",
            description_summary="APIs com Spring Boot",
            workplace_model=WorkplaceModel.UNKNOWN,
        ),
        profile,
    )

    assert "WORKPLACE_UNCLEAR:missing" in classified.match_labels
    assert "FIT:CONDITIONAL" in classified.match_labels
    assert "FIT:READY" not in classified.match_labels


def test_classify_preserves_previous_contract_without_workplace_preference() -> None:
    classified = classify(
        _record(
            title="Desenvolvedor Java Junior",
            description_summary="Atuacao presencial no escritorio",
            workplace_model=WorkplaceModel.ONSITE,
        ),
        PROFILE,
    )

    assert not any(label.startswith("WORKPLACE_") for label in classified.match_labels)
    assert "FIT:READY" in classified.match_labels
    assert "FIT_SCORE:3" in classified.match_labels


def test_classify_does_not_exclude_junior_role_when_summary_mentions_senior_mentor() -> None:
    classified = classify(
        _record(
            title="Desenvolvedor Java Junior",
            seniority="Junior",
            description_summary="Mentoria semanal com desenvolvedores senior",
        ),
        PROFILE,
    )

    assert "SENIORITY_MATCH:junior" in classified.match_labels
    assert "SENIORITY_MISMATCH:senior" not in classified.match_labels
    assert "FIT:READY" in classified.match_labels
    assert "FIT:EXCLUDE" not in classified.match_labels


def test_classify_treats_hybrid_and_remote_text_as_unclear_with_remote_only_filter() -> None:
    profile = SearchProfile(
        positive_keywords=PROFILE.positive_keywords,
        seniority_levels=PROFILE.seniority_levels,
        location_scopes=PROFILE.location_scopes,
        excluded_terms=PROFILE.excluded_terms,
        workplace_models=(WorkplaceModel.REMOTE,),
    )

    classified = classify(
        _record(
            title="Desenvolvedor Java Junior",
            description_summary="Modelo híbrido com possibilidade de trabalho remoto",
            workplace_model=WorkplaceModel.UNKNOWN,
        ),
        profile,
    )

    assert "WORKPLACE_MATCH:REMOTE" in classified.match_labels
    assert "WORKPLACE_UNCLEAR:multiple" in classified.match_labels
    assert not any(
        label.startswith("WORKPLACE_MISMATCH:") for label in classified.match_labels
    )
    assert "FIT:CONDITIONAL" in classified.match_labels
    assert "FIT:EXCLUDE" not in classified.match_labels


def test_classify_accepts_hybrid_and_remote_text_when_both_models_are_selected() -> None:
    profile = SearchProfile(
        positive_keywords=PROFILE.positive_keywords,
        seniority_levels=PROFILE.seniority_levels,
        location_scopes=PROFILE.location_scopes,
        excluded_terms=PROFILE.excluded_terms,
        workplace_models=(WorkplaceModel.REMOTE, WorkplaceModel.HYBRID),
    )

    classified = classify(
        _record(
            title="Desenvolvedor Java Junior",
            description_summary="Modelo híbrido com possibilidade de trabalho remoto",
            workplace_model=WorkplaceModel.UNKNOWN,
        ),
        profile,
    )

    assert "WORKPLACE_MATCH:REMOTE" in classified.match_labels
    assert "WORKPLACE_MATCH:HYBRID" in classified.match_labels
    assert "FIT:READY" in classified.match_labels


def test_classify_remote_role_also_matches_preferred_city() -> None:
    classified = classify(
        _record(
            title="Desenvolvedor Java Junior",
            location="São Carlos, SP",
            workplace_model=WorkplaceModel.REMOTE,
            remote_scope=None,
        ),
        PROFILE,
    )

    assert "LOCATION_MATCH:sao-carlos-sp" in classified.match_labels
    assert "FIT:READY" in classified.match_labels


def test_classify_remote_title_is_not_excluded_by_offsite_city() -> None:
    classified = classify(
        _record(
            title="Java Junior - Remote Work",
            location="São Bernardo do Campo, SP",
            workplace_model=WorkplaceModel.UNKNOWN,
            remote_scope=None,
        ),
        PROFILE,
    )

    assert "LOCATION_UNCLEAR:remote_scope" in classified.match_labels
    assert "LOCATION_MISMATCH:outside_scope" not in classified.match_labels
    assert "FIT:CONDITIONAL" in classified.match_labels


def test_classify_requires_city_and_state_to_match_same_location_scope() -> None:
    profile = SearchProfile(
        positive_keywords=("java",),
        seniority_levels=("junior",),
        location_scopes=("sao-jose-sc",),
        excluded_terms=("senior",),
    )

    classified = classify(
        _record(
            title="Desenvolvedor Java Junior",
            description_summary=None,
            location="São José dos Campos - SP",
            evidence_snippets=(),
        ),
        profile,
    )

    assert "LOCATION_MATCH:sao-jose-sc" not in classified.match_labels
    assert "LOCATION_MISMATCH:outside_scope" in classified.match_labels
    assert "FIT:EXCLUDE" in classified.match_labels
    assert "FIT:READY" not in classified.match_labels


def test_classify_excludes_explicit_internship_when_only_junior_is_selected() -> None:
    profile = SearchProfile(
        positive_keywords=("java",),
        seniority_levels=("junior",),
        location_scopes=("sao-carlos-sp",),
    )

    classified = classify(
        _record(title="Estágio Java", seniority="Estágio"),
        profile,
    )

    assert "SENIORITY_MISMATCH:estagio" in classified.match_labels
    assert "FIT:EXCLUDE" in classified.match_labels


def test_classify_matches_brazilian_state_name_to_uf_location() -> None:
    profile = SearchProfile(
        positive_keywords=("java",),
        seniority_levels=("junior",),
        location_scopes=("minas-gerais",),
    )

    classified = classify(
        _record(title="Java Junior", location="Belo Horizonte, MG"),
        profile,
    )

    assert "LOCATION_MATCH:minas-gerais" in classified.match_labels
    assert "FIT:READY" in classified.match_labels


@pytest.mark.parametrize("alias", ["Estagiário", "Estagiária", "Intern"])
def test_classify_recognizes_internship_seniority_aliases(alias: str) -> None:
    classified = classify(
        _record(
            title=f"{alias} de Desenvolvimento Java",
            description_summary=None,
            evidence_snippets=(),
        ),
        PROFILE,
    )

    assert "SENIORITY_MATCH:estagio" in classified.match_labels


def test_classify_reads_restricted_audience_from_description_summary() -> None:
    classified = classify(
        _record(
            title="Desenvolvedor Java Junior",
            description_summary="Vaga exclusiva para PCD.",
        ),
        PROFILE,
    )

    assert "ELIGIBILITY_UNCLEAR:restricted_audience" in classified.match_labels
    assert "FIT:CONDITIONAL" in classified.match_labels
    assert "FIT:READY" not in classified.match_labels


def test_classify_matches_city_uf_scope_to_full_state_name() -> None:
    profile = SearchProfile(
        positive_keywords=("java",),
        seniority_levels=("junior",),
        location_scopes=("florianopolis-sc",),
    )

    classified = classify(
        _record(
            title="Desenvolvedor Java Junior",
            location="Florianópolis, Santa Catarina",
        ),
        profile,
    )

    assert "LOCATION_MATCH:florianopolis-sc" in classified.match_labels
    assert "FIT:READY" in classified.match_labels


@pytest.mark.parametrize("location", ("Florianóp... - SC", "Florianóp… - SC"))
def test_classify_matches_truncated_city_prefix_with_compatible_state(
    location: str,
) -> None:
    profile = SearchProfile(
        positive_keywords=("java",),
        seniority_levels=("junior",),
        location_scopes=("florianopolis-sc",),
    )

    classified = classify(
        _record(title="Desenvolvedor Java Junior", location=location),
        profile,
    )

    assert "LOCATION_MATCH:florianopolis-sc" in classified.match_labels
    assert "FIT:READY" in classified.match_labels


@pytest.mark.parametrize("location", ("Florianóp...", "Florianóp... - SP"))
def test_classify_does_not_promote_truncated_city_without_compatible_state(
    location: str,
) -> None:
    profile = SearchProfile(
        positive_keywords=("java",),
        seniority_levels=("junior",),
        location_scopes=("florianopolis-sc",),
    )

    classified = classify(
        _record(title="Desenvolvedor Java Junior", location=location),
        profile,
    )

    assert "LOCATION_MATCH:florianopolis-sc" not in classified.match_labels
    assert "FIT:READY" not in classified.match_labels


def test_classify_accepts_selected_entry_level_when_title_mentions_two_entry_levels() -> None:
    profile = SearchProfile(
        positive_keywords=("java",),
        seniority_levels=("estagio",),
        location_scopes=("sao-carlos-sp",),
    )

    classified = classify(
        _record(title="Estágio ou Desenvolvedor Java Junior"),
        profile,
    )

    assert "SENIORITY_MATCH:estagio" in classified.match_labels
    assert "SENIORITY_MISMATCH:junior" not in classified.match_labels
    assert "FIT:READY" in classified.match_labels


def test_classify_reads_plural_restricted_audience_from_description_summary() -> None:
    classified = classify(
        _record(
            title="Desenvolvedor Java Junior",
            description_summary="Vaga exclusiva para pessoas com deficiência.",
        ),
        PROFILE,
    )

    assert "ELIGIBILITY_UNCLEAR:restricted_audience" in classified.match_labels
    assert "FIT:CONDITIONAL" in classified.match_labels
    assert "FIT:READY" not in classified.match_labels


def test_classify_matches_full_state_scope_to_full_state_location() -> None:
    profile = SearchProfile(
        positive_keywords=("java",),
        seniority_levels=("junior",),
        location_scopes=("santa-catarina",),
    )

    classified = classify(
        _record(
            title="Desenvolvedor Java Junior",
            location="Florianópolis, Santa Catarina",
        ),
        profile,
    )

    assert "LOCATION_MATCH:santa-catarina" in classified.match_labels
    assert "FIT:READY" in classified.match_labels


ENTRY_PROFILE = SearchProfile(
    positive_keywords=("java", "backend"),
    seniority_levels=("estagio", "junior"),
    location_scopes=("remoto-brasil", "sao-carlos-sp"),
    excluded_terms=("pleno", "senior"),
)


def _labels(**overrides: object) -> tuple[str, ...]:
    base: dict[str, object] = {
        "title": "Desenvolvedor Java Júnior",
        "description_summary": None,
        "location": None,
        "workplace_model": WorkplaceModel.UNKNOWN,
        "evidence_snippets": (),
    }
    base.update(overrides)
    return classify(_record(**base), ENTRY_PROFILE, default_country="BR").match_labels


@pytest.mark.parametrize(
    "summary",
    [
        "Vaga 100% remota para todo o Brasil",
        "Vaga 100% remoto",
        "Atuação em home office",
        "Trabalho remoto",
        "Modalidade: remoto (Brasil)",
    ],
)
def test_remote_text_overrides_headquarters_city_in_location(summary: str) -> None:
    labels = _labels(location="Curitiba, PR", description_summary=summary)

    assert "LOCATION_MATCH:remote_brazil" in labels
    assert "LOCATION_MISMATCH:outside_scope" not in labels
    assert "FIT:EXCLUDE" not in labels


def test_onsite_vacancy_in_other_city_is_still_excluded() -> None:
    labels = _labels(location="Lajeado, RS", description_summary="Vaga presencial - Lajeado/RS")

    assert "LOCATION_MISMATCH:outside_scope" in labels
    assert "FIT:EXCLUDE" in labels


def test_remote_abroad_is_not_remote_brazil() -> None:
    labels = _labels(location="Curitiba, PR", description_summary="Remoto EUA/Canadá")

    assert "LOCATION_MATCH:remote_brazil" not in labels
    assert "LOCATION_UNCLEAR:remote_scope" in labels


@pytest.mark.parametrize(
    "title",
    [
        "Desenvolvedor Java I",
        "Desenvolvedor Java - Nível 1",
        "Java Developer Entry Level",
        "Desenvolvedor Java Jr.",
        "Desenvolvedor Java Iniciante",
        "Programa Trainee Java",
        "Jovem Aprendiz Java",
    ],
)
def test_entry_level_synonyms_are_recognized(title: str) -> None:
    labels = _labels(title=title, location="São Carlos, SP")

    assert any(label.startswith("SENIORITY_MATCH:") for label in labels)
    assert "FIT:EXCLUDE" not in labels


@pytest.mark.parametrize(
    "title", ["Desenvolvedor Java Júnior/Pleno", "Desenvolvedor Java Jr/Pl", "Java Junior ou Pleno"]
)
def test_junior_pleno_range_is_conditional_not_excluded(title: str) -> None:
    labels = _labels(title=title, location="São Carlos, SP")

    assert "SENIORITY_MATCH:junior" in labels
    assert not any(label.startswith("SENIORITY_MISMATCH:") for label in labels)
    assert "FIT:CONDITIONAL" in labels


@pytest.mark.parametrize(
    "title",
    [
        "Desenvolvedor Java Pleno",
        "Desenvolvedor Java Sênior",
        "Analista Java II",
        "Engenheiro Java I/O Senior",
        "PL/SQL Developer Pleno",
    ],
)
def test_non_entry_titles_do_not_become_junior(title: str) -> None:
    labels = _labels(title=title, location="São Carlos, SP")

    assert not any(label.startswith("SENIORITY_MATCH:") for label in labels)


@pytest.mark.parametrize("title", ["Desenvolvedor Java Pleno", "Desenvolvedor Java Sênior"])
def test_pleno_and_senior_alone_stay_excluded(title: str) -> None:
    assert "FIT:EXCLUDE" in _labels(title=title, location="São Carlos, SP")


def test_pl_sql_is_not_treated_as_pleno_in_junior_title() -> None:
    labels = _labels(title="Desenvolvedor PL/SQL Júnior", location="São Carlos, SP")

    assert "SENIORITY_MATCH:junior" in labels
    assert not any(label.startswith("SENIORITY_MISMATCH:") for label in labels)


@pytest.mark.parametrize(
    ("title", "location", "summary", "expected"),
    [
        ("Dev Java", "CLT • Senior • Home Office", None, WorkplaceModel.REMOTE),
        ("Dev Java", "Remoto (Sede em Campinas, SP)", None, WorkplaceModel.REMOTE),
        ("Dev Java", "Presencial (39)", None, WorkplaceModel.ONSITE),
        ("Dev Java", "São Paulo, SP", "Modelo híbrido, 3 dias no escritório", WorkplaceModel.HYBRID),
        ("Dev Java", "São Paulo, SP", "Híbrido ou totalmente remoto", WorkplaceModel.UNKNOWN),
        ("Dev Java", "São Paulo, SP", None, WorkplaceModel.UNKNOWN),
    ],
)
def test_classify_fills_workplace_model_only_with_unambiguous_evidence(
    title: str, location: str, summary: str | None, expected: WorkplaceModel
) -> None:
    record = _record(
        title=title,
        location=location,
        description_summary=summary,
        workplace_model=WorkplaceModel.UNKNOWN,
    )

    classified = classify(record, ENTRY_PROFILE, default_country="BR")

    assert classified.workplace_model is expected
    inferred = "WORKPLACE_INFERRED:" + expected.value
    assert (inferred in classified.match_labels) is (expected is not WorkplaceModel.UNKNOWN)


def test_classify_keeps_workplace_model_declared_by_source() -> None:
    record = _record(
        workplace_model=WorkplaceModel.HYBRID,
        description_summary="Vaga 100% remota",
    )

    classified = classify(record, ENTRY_PROFILE, default_country="BR")

    assert classified.workplace_model is WorkplaceModel.HYBRID
    assert not any(label.startswith("WORKPLACE_INFERRED:") for label in classified.match_labels)


def test_inferred_workplace_counts_toward_workplace_confirmed() -> None:
    profile = SearchProfile(
        positive_keywords=("java",),
        seniority_levels=("junior",),
        location_scopes=("remoto-brasil",),
        workplace_models=(WorkplaceModel.REMOTE,),
    )
    record = _record(
        title="Desenvolvedor Java Júnior",
        location="Brasil",
        description_summary="Trabalho remoto",
        workplace_model=WorkplaceModel.UNKNOWN,
    )

    labels = classify(record, profile, default_country="BR").match_labels

    assert "WORKPLACE_MATCH:REMOTE" in labels
    assert "FIT:READY" in labels


def test_classify_fills_seniority_and_technologies_from_evidence() -> None:
    record = _record(
        title="Desenvolvedor Java Júnior",
        description_summary="Spring Boot e API REST",
        seniority=None,
        technologies=(),
    )

    classified = classify(record, PROFILE)

    assert classified.seniority == "junior"
    assert classified.technologies == ("api rest", "java", "spring boot")


def test_classify_does_not_invent_seniority_or_technologies() -> None:
    record = _record(
        title="Analista de Suporte",
        description_summary="Atendimento",
        evidence_snippets=(),
        seniority=None,
        technologies=(),
    )

    classified = classify(record, PROFILE)

    assert classified.seniority is None
    assert classified.technologies == ()


def test_classify_keeps_source_seniority_and_merges_technologies() -> None:
    record = _record(
        title="Dev Java",
        description_summary=None,
        evidence_snippets=(),
        seniority="Trainee",
        technologies=("Kotlin",),
    )

    classified = classify(record, PROFILE)

    assert classified.seniority == "Trainee"
    assert classified.technologies == ("Kotlin", "java")


def test_portuguese_verb_usa_is_not_read_as_united_states() -> None:
    labels = _labels(
        location="Curitiba, PR",
        description_summary="Vaga 100% remota; o time usa Java e Spring",
    )

    assert "LOCATION_MATCH:remote_brazil" in labels


def test_remote_united_states_in_english_is_not_remote_brazil() -> None:
    labels = _labels(location="Curitiba, PR", description_summary="Remote - United States")

    assert "LOCATION_MATCH:remote_brazil" not in labels
