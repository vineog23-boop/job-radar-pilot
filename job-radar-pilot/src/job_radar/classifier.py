from __future__ import annotations

from dataclasses import replace
import re
import unicodedata

from job_radar.models import SearchProfile, VacancyRecord, WorkplaceModel


_TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "backend": ("backend", "back end"),
    "estagio": ("estagio", "estagiario", "estagiaria", "intern"),
    "junior": ("junior", "jr"),
    "senior": ("senior", "sr"),
}

_CANONICAL_TERMS = {
    alias: canonical
    for canonical, aliases in _TERM_ALIASES.items()
    for alias in aliases
}
_CURATED_ARTICLE_SOURCES = {
    "companhia-de-estagios",
    "estagiotrainee",
    "otrainee",
    "seja-trainee",
}
_CORE_TECH_TERMS = {"java", "spring boot", "backend", "api rest", "jpa", "hibernate"}
_CONDITIONAL_ELIGIBILITY_MARKERS = (
    "pcd",
    "pessoa com deficiencia",
    "pessoas com deficiencia",
    "exclusiva para mulheres",
    "exclusivo para mulheres",
)
_REMOTE_SCOPE_NEUTRAL_TERMS = (
    "apenas",
    "integralmente",
    "modalidade",
    "modelo",
    "nacional",
    "somente",
    "totalmente",
    "trabalho",
    "vaga",
    "work",
)

_WORKPLACE_MARKERS: tuple[tuple[WorkplaceModel, tuple[str, ...]], ...] = (
    (WorkplaceModel.HYBRID, ("hibrido", "hybrid")),
    (WorkplaceModel.REMOTE, ("remoto", "remote", "home office", "teletrabalho")),
    (WorkplaceModel.ONSITE, ("presencial", "on site", "onsite")),
)

_BRAZIL_STATE_UFS = {
    "acre": "ac",
    "alagoas": "al",
    "amapa": "ap",
    "amazonas": "am",
    "bahia": "ba",
    "ceara": "ce",
    "distrito federal": "df",
    "espirito santo": "es",
    "goias": "go",
    "maranhao": "ma",
    "mato grosso": "mt",
    "mato grosso do sul": "ms",
    "minas gerais": "mg",
    "para": "pa",
    "paraiba": "pb",
    "parana": "pr",
    "pernambuco": "pe",
    "piaui": "pi",
    "rio de janeiro": "rj",
    "rio grande do norte": "rn",
    "rio grande do sul": "rs",
    "rondonia": "ro",
    "roraima": "rr",
    "santa catarina": "sc",
    "sao paulo": "sp",
    "sergipe": "se",
    "tocantins": "to",
}
_UF_STATE_NAMES = {uf: state_name for state_name, uf in _BRAZIL_STATE_UFS.items()}


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        "".join(character for character in decomposed if not unicodedata.combining(character)).split()
    )


def _canonical_term(value: str) -> str:
    normalized = _normalize(value)
    return _CANONICAL_TERMS.get(normalized, normalized)


def _contains_term(searchable_text: str, term: str) -> bool:
    canonical = _canonical_term(term)
    aliases = _TERM_ALIASES.get(canonical, (canonical,))

    for alias in aliases:
        parts = [re.escape(part) for part in re.split(r"[\s-]+", alias) if part]
        pattern = r"[\s-]+".join(parts)
        if pattern and re.search(rf"(?<!\w){pattern}(?!\w)", searchable_text):
            return True
    return False


def _infer_workplaces(record: VacancyRecord) -> frozenset[WorkplaceModel]:
    if record.workplace_model is not WorkplaceModel.UNKNOWN:
        return frozenset((record.workplace_model,))
    factual_text = _normalize(
        " ".join(
            part
            for part in (record.title, record.location, record.description_summary)
            if part
        )
    )
    return frozenset(
        model
        for model, markers in _WORKPLACE_MARKERS
        if any(_contains_term(factual_text, marker) for marker in markers)
    )


def _has_brazilian_location_context(normalized_scope: str) -> bool:
    return any(
        _contains_term(normalized_scope, reference)
        for reference in (
            *_BRAZIL_STATE_UFS.keys(),
            *_BRAZIL_STATE_UFS.values(),
        )
    )


def _brazilian_default_applies_to_remote_scope(normalized_scope: str) -> bool:
    if not normalized_scope or _has_brazilian_location_context(normalized_scope):
        return True

    remaining = normalized_scope
    remote_markers = next(
        markers
        for model, markers in _WORKPLACE_MARKERS
        if model is WorkplaceModel.REMOTE
    )
    for term in (*remote_markers, "teletrabalho", *_REMOTE_SCOPE_NEUTRAL_TERMS):
        parts = [re.escape(part) for part in re.split(r"[\s-]+", term) if part]
        pattern = r"[\s-]+".join(parts)
        remaining = re.sub(rf"(?<!\w){pattern}(?!\w)", " ", remaining)
    return not re.sub(r"[\W\d_]+", "", remaining)


def _is_generic_brazilian_location(normalized_location: str) -> bool:
    return normalized_location in {
        "brasil",
        "diversas",
        "diversas localidades",
        "localidade: diversas",
        "qualquer cidade do brasil",
    } or (
        "aceita candidaturas de qualquer cidade do brasil" in normalized_location
    )


def _matches_location_scope(normalized_location: str, scope: str) -> bool:
    normalized_scope = _normalize(scope.replace("-", " "))
    if not normalized_scope or normalized_scope == "remoto brasil":
        return False
    city_and_state = re.fullmatch(r"(.+?)\s+([a-z]{2})", normalized_scope)
    if city_and_state is not None:
        city, state = city_and_state.groups()
        city_pattern = r"[\s-]+".join(
            re.escape(part) for part in city.split() if part
        )
        state_patterns = [re.escape(state)]
        state_name = _UF_STATE_NAMES.get(state)
        if state_name:
            state_patterns.append(
                r"[\s-]+".join(
                    re.escape(part) for part in state_name.split() if part
                )
            )
        state_pattern = "(?:" + "|".join(state_patterns) + ")"
        if re.search(
            rf"(?<!\w){city_pattern}(?:\s*[,/\-]\s*|\s+){state_pattern}(?!\w)",
            normalized_location,
        ):
            return True
        truncated_city = re.search(
            rf"(?:^|[;,|]\s*)(?P<prefix>[a-z][a-z\s-]{{2,}}?)"
            rf"(?:\.{{3}}|…)(?:\s*[,/\-]\s*|\s+){state_pattern}(?!\w)",
            normalized_location,
        )
        if truncated_city is None:
            return False
        city_prefix = " ".join(
            truncated_city.group("prefix").replace("-", " ").split()
        )
        return city.startswith(city_prefix)

    state = _BRAZIL_STATE_UFS.get(normalized_scope)
    if state is None and re.fullmatch(r"[a-z]{2}", normalized_scope):
        state = normalized_scope
    if normalized_scope in {"brasil", "brazil"}:
        return _contains_term(normalized_location, normalized_scope) or any(
            _contains_term(normalized_location, state_reference)
            for state_reference in (
                *_BRAZIL_STATE_UFS.keys(),
                *_BRAZIL_STATE_UFS.values(),
            )
        )
    if state is not None:
        state_name = _UF_STATE_NAMES.get(state)
        return any(
            _contains_term(normalized_location, reference)
            for reference in (state, state_name)
            if reference
        )
    return _contains_term(normalized_location, normalized_scope)


def classify(
    record: VacancyRecord,
    profile: SearchProfile,
    *,
    default_country: str | None = None,
) -> VacancyRecord:
    searchable_text = _normalize(
        " ".join(
            part
            for part in (
                record.title,
                record.description_summary,
                record.seniority,
                record.location,
                " ".join(record.technologies),
                " ".join(record.requirements),
                " ".join(record.evidence_snippets),
            )
            if part
        )
    )
    explicit_seniority_text = _normalize(
        " ".join(part for part in (record.title, record.seniority) if part)
    )
    eligibility_text = _normalize(
        " ".join(
            part
            for part in (
                record.title,
                record.description_summary,
                " ".join(record.eligibility_notes),
                " ".join(record.requirements),
                " ".join(record.evidence_snippets),
            )
            if part
        )
    )
    labels: set[str] = set()

    if any(
        _contains_term(eligibility_text, marker)
        for marker in _CONDITIONAL_ELIGIBILITY_MARKERS
    ):
        labels.add("ELIGIBILITY_UNCLEAR:restricted_audience")

    for keyword in profile.positive_keywords:
        canonical = _canonical_term(keyword)
        if canonical and _contains_term(searchable_text, canonical):
            labels.add(f"TECH_MATCH:{canonical}")

    selected_seniority = {
        _canonical_term(seniority) for seniority in profile.seniority_levels
    }
    detected_entry_levels = {
        canonical
        for canonical in ("estagio", "junior")
        if _contains_term(explicit_seniority_text, canonical)
    }
    matching_entry_levels = detected_entry_levels.intersection(selected_seniority)
    for canonical in matching_entry_levels:
        labels.add(f"SENIORITY_MATCH:{canonical}")
    if detected_entry_levels and not matching_entry_levels:
        for canonical in detected_entry_levels:
            labels.add(f"SENIORITY_MISMATCH:{canonical}")

    for excluded in profile.excluded_terms:
        canonical = _canonical_term(excluded)
        if canonical and _contains_term(explicit_seniority_text, canonical):
            labels.add(f"SENIORITY_MISMATCH:{canonical}")

    normalized_location = _normalize(record.location)
    explicit_remote_location = any(
        _contains_term(normalized_location, marker)
        for marker in ("remoto", "remote", "home office")
    )
    inferred_workplaces = _infer_workplaces(record)
    is_remote = (
        WorkplaceModel.REMOTE in inferred_workplaces or explicit_remote_location
    )
    if is_remote:
        normalized_scopes = tuple(
            scope
            for scope in (
                _normalize(record.remote_scope),
                normalized_location,
            )
            if scope
        )
        has_explicit_brazil = any(
            _contains_term(scope, "brasil") or _contains_term(scope, "brazil")
            for scope in normalized_scopes
        )
        all_scopes_support_brazil = all(
            _contains_term(scope, "brasil")
            or _contains_term(scope, "brazil")
            or _brazilian_default_applies_to_remote_scope(scope)
            for scope in normalized_scopes
        )
        if (
            all_scopes_support_brazil
            and (has_explicit_brazil or default_country == "BR")
        ):
            labels.add("LOCATION_MATCH:remote_brazil")
        else:
            labels.add("LOCATION_UNCLEAR:remote_scope")
    if not normalized_location and not is_remote:
        labels.add("LOCATION_UNCLEAR:missing")
    elif _is_generic_brazilian_location(normalized_location):
        labels.add("LOCATION_UNCLEAR:multiple")
    elif normalized_location:
        for scope in profile.location_scopes:
            if _matches_location_scope(normalized_location, scope):
                labels.add(f"LOCATION_MATCH:{scope}")
        if (
            not is_remote
            and not any(label.startswith("LOCATION_MATCH:") for label in labels)
            and normalized_location not in {"nao informado", "n/a", "a definir"}
        ):
            labels.add("LOCATION_MISMATCH:outside_scope")

    has_technology = any(label.startswith("TECH_MATCH:") for label in labels)
    has_core_technology = any(
        label == f"TECH_MATCH:{term}" for label in labels for term in _CORE_TECH_TERMS
    )
    has_seniority = any(label.startswith("SENIORITY_MATCH:") for label in labels)
    has_seniority_mismatch = any(
        label.startswith("SENIORITY_MISMATCH:") for label in labels
    )
    has_location = any(label.startswith("LOCATION_MATCH:") for label in labels)
    has_location_mismatch = any(
        label.startswith("LOCATION_MISMATCH:") for label in labels
    )
    has_eligibility_unclear = any(
        label.startswith("ELIGIBILITY_UNCLEAR:") for label in labels
    )

    has_workplace_match = False
    has_workplace_mismatch = False
    has_workplace_unclear = False
    if profile.workplace_models:
        if not inferred_workplaces:
            labels.add("WORKPLACE_UNCLEAR:missing")
        else:
            if len(inferred_workplaces) > 1:
                labels.add("WORKPLACE_UNCLEAR:multiple")
                has_workplace_unclear = not inferred_workplaces.issubset(
                    frozenset(profile.workplace_models)
                )
            compatible = inferred_workplaces.intersection(profile.workplace_models)
            if compatible:
                for workplace in compatible:
                    labels.add(f"WORKPLACE_MATCH:{workplace.value}")
                has_workplace_match = True
            else:
                for workplace in inferred_workplaces:
                    labels.add(f"WORKPLACE_MISMATCH:{workplace.value}")
                has_workplace_mismatch = True

    if record.source in _CURATED_ARTICLE_SOURCES:
        labels.add("SOURCE_TYPE:CURATED_ARTICLE")
        fit = "AMBIGUOUS"
        score = 0
    elif has_seniority_mismatch or has_location_mismatch or has_workplace_mismatch:
        fit = "EXCLUDE"
        score = -1
    else:
        score = sum(
            (
                has_technology,
                has_seniority,
                has_location,
                has_workplace_match,
            )
        )
        workplace_confirmed = not profile.workplace_models or (
            has_workplace_match and not has_workplace_unclear
        )
        if (
            has_core_technology
            and has_seniority
            and has_location
            and workplace_confirmed
            and not has_eligibility_unclear
        ):
            fit = "READY"
        elif has_core_technology:
            fit = "CONDITIONAL"
        else:
            fit = "AMBIGUOUS"

    labels.add(f"FIT:{fit}")
    labels.add(f"FIT_SCORE:{score}")

    return replace(record, match_labels=tuple(sorted(labels)))
