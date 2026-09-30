from __future__ import annotations

from dataclasses import replace
import re
import unicodedata

from job_radar.models import SearchProfile, VacancyRecord, WorkplaceModel


_TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "backend": ("backend", "back end"),
    "estagio": (
        "estagio",
        "estagiario",
        "estagiaria",
        "intern",
        "internship",
        "trainee",
        "aprendiz",
    ),
    "junior": ("junior", "jr", "nivel 1", "entry level", "iniciante"),
    "pleno": ("pleno", "plena", "mid level", "mid-level"),
    "senior": ("senior", "sr"),
}

# Níveis que o perfil pode escolher, do mais júnior ao mais sênior.
SENIORITY_LEVELS = ("estagio", "junior", "pleno", "senior")
# Termos de liderança/especialidade: só entram como exclusão automática quando o
# perfil NÃO pediu vagas sênior.
LEADERSHIP_TERMS = (
    "staff",
    "principal",
    "especialista",
    "lider tecnico",
    "tech lead",
    "arquiteto",
    "arquiteta",
    "architect",
)
# Ferramentas de apoio: aparecem em quase toda vaga e sozinhas não indicam a
# stack principal do perfil (não contam como "tecnologia central").
_SECONDARY_TERMS = {
    "docker", "sql", "maven", "gradle", "junit", "mockito", "testes", "git",
    "linux", "aws", "azure", "gcp", "kubernetes", "ci/cd", "scrum", "agile",
    "postgresql", "mysql", "redis", "jira", "rest", "api",
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


def _core_terms(profile: SearchProfile) -> set[str]:
    """Stack principal do perfil: palavras-chave que não são ferramentas de apoio."""

    core = {
        canonical
        for canonical in (_canonical_term(keyword) for keyword in profile.positive_keywords)
        if canonical and canonical not in _SECONDARY_TERMS
    }
    return core | (_CORE_TECH_TERMS & {_canonical_term(k) for k in profile.positive_keywords})
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
    (
        WorkplaceModel.REMOTE,
        ("remoto", "remota", "remote", "home office", "teletrabalho"),
    ),
    (WorkplaceModel.ONSITE, ("presencial", "on site", "onsite")),
)

# "usa" fica de fora de propósito: em português é o verbo ("o time usa Java").
_FOREIGN_REGION_TERMS = (
    "eua",
    "estados unidos",
    "united states",
    "canada",
    "europa",
    "europe",
    "portugal",
    "reino unido",
)
# "Junior/Pleno", "Jr ou Pl": faixa que inclui nível de entrada, não é exclusão.
_RANGE_ENTRY = r"(?:junior|jr|estagio|estagiario|estagiaria)\.?"
_RANGE_MID = r"(?:pleno|pl)(?![\w/])"
_RANGE_SEPARATOR = r"\s*(?:/|-|,|\||\bou\b|\be\b|\ba\b|\bate\b)\s*"
_ENTRY_MID_RANGE = re.compile(
    rf"(?<!\w){_RANGE_ENTRY}{_RANGE_SEPARATOR}{_RANGE_MID}"
    rf"|(?<!\w){_RANGE_MID}{_RANGE_SEPARATOR}{_RANGE_ENTRY}(?!\w)"
)
# Algarismo romano isolado depois do cargo ("Desenvolvedor Java I"), sem pegar "I/O".
_ROMAN_ONE_LEVEL = re.compile(r"(?<=\w )i(?=\s*(?:$|[-|,(]))")

# Sinais de que o cargo é da área de tecnologia (título já normalizado, sem
# acento). Sem nenhum deles, sem stack principal do perfil e fora dos artigos
# curados, a vaga é marcada RELEVANCE:OFF_TOPIC e some das listas por padrão.
_IT_TITLE_SIGNALS = re.compile(
    r"(?<!\w)(?:desenvolv\w*|developer|dev|programador\w*|software|backend|back end|"
    r"frontend|front end|full ?stack|devops|devsecops|sre|dba|qa|quality assurance|"
    r"dados|data|bi|machine learning|ia|inteligencia artificial|cloud|ti|tecnologia|"
    r"sistemas?|infraestrutura|redes|seguranca da informacao|ciberseguranca|mobile|"
    r"android|ios|python|java|javascript|typescript|node|react|angular|sql|php|golang|"
    r"kotlin|scrum|product owner|suporte tecnico|help ?desk|service desk|automacao|"
    r"rpa|sap|erp|totvs|protheus|salesforce|servicenow|engenheir\w* de software|"
    r"analista de testes?|analista de requisitos|cientista de dados|"
    r"c#|\.net|dotnet|golang|flutter|react native|power ?bi|etl|terraform|aws|azure|"
    r"kubernetes|docker|linux|spring|django|laravel|vue|next\.?js|nestjs|spark|"
    r"machine learning|engenheir\w* de dados|analista de bi|arquiteto de software|"
    r"analista programador|tech lead)(?!\w)"
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


def _is_entry_mid_range(explicit_seniority_text: str) -> bool:
    return _ENTRY_MID_RANGE.search(explicit_seniority_text) is not None


def _has_roman_one_level(explicit_seniority_text: str) -> bool:
    return _ROMAN_ONE_LEVEL.search(explicit_seniority_text) is not None


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
    labels: set[str] = {
        label for label in record.match_labels if label.startswith(("EXTRACTION:", "ENRICHED:"))
    }

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
    if _has_roman_one_level(explicit_seniority_text):
        detected_entry_levels.add("junior")
    detected_levels = set(detected_entry_levels) | {
        canonical
        for canonical in ("pleno", "senior")
        if _contains_term(explicit_seniority_text, canonical)
    }
    matching_levels = detected_levels.intersection(selected_seniority)
    for canonical in matching_levels:
        labels.add(f"SENIORITY_MATCH:{canonical}")
    if detected_entry_levels and not matching_levels:
        # Nível de entrada explícito que o perfil não quer (ex.: quer pleno).
        for canonical in detected_entry_levels:
            labels.add(f"SENIORITY_MISMATCH:{canonical}")

    entry_mid_range = bool(detected_entry_levels) and _is_entry_mid_range(
        explicit_seniority_text
    )
    if entry_mid_range:
        labels.add("SENIORITY_UNCLEAR:range")
    for excluded in profile.excluded_terms:
        canonical = _canonical_term(excluded)
        if canonical in selected_seniority:
            # O perfil pediu esse nível: não pode ser exclusão.
            continue
        if entry_mid_range and canonical == "pleno":
            continue
        if canonical and _contains_term(explicit_seniority_text, canonical):
            labels.add(f"SENIORITY_MISMATCH:{canonical}")
    if not matching_levels:
        # Nível explícito de meio/topo que o perfil não escolheu.
        for canonical in ("pleno", "senior"):
            if canonical in detected_levels and canonical not in selected_seniority:
                if canonical == "pleno" and entry_mid_range:
                    continue
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
    factual_text = _normalize(
        " ".join(part for part in (record.title, record.description_summary) if part)
    )
    remote_abroad = any(
        _contains_term(factual_text, region) for region in _FOREIGN_REGION_TERMS
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
            and not remote_abroad
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
    core_terms = _core_terms(profile)
    has_core_technology = any(
        label == f"TECH_MATCH:{term}" for label in labels for term in core_terms
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
            and not entry_mid_range
        ):
            fit = "READY"
        elif has_core_technology:
            fit = "CONDITIONAL"
        else:
            fit = "AMBIGUOUS"

    workplace_model = record.workplace_model
    if workplace_model is WorkplaceModel.UNKNOWN and len(inferred_workplaces) == 1:
        (workplace_model,) = inferred_workplaces
        labels.add(f"WORKPLACE_INFERRED:{workplace_model.value}")

    if (
        not has_core_technology
        and record.source not in _CURATED_ARTICLE_SOURCES
        and not _IT_TITLE_SIGNALS.search(_normalize(record.title))
        and not any(
            _IT_TITLE_SIGNALS.search(_normalize(technology))
            for technology in record.technologies
        )
    ):
        labels.add("RELEVANCE:OFF_TOPIC")

    labels.add(f"FIT:{fit}")
    labels.add(f"FIT_SCORE:{score}")

    seniority = record.seniority
    if not seniority and detected_levels:
        seniority = next(
            level for level in SENIORITY_LEVELS if level in detected_levels
        )
    known_technologies = {technology.casefold() for technology in record.technologies}
    technologies = record.technologies + tuple(
        technology
        for technology in sorted(
            label.removeprefix("TECH_MATCH:")
            for label in labels
            if label.startswith("TECH_MATCH:")
        )
        if technology.casefold() not in known_technologies
    )

    return replace(
        record,
        match_labels=tuple(sorted(labels)),
        workplace_model=workplace_model,
        seniority=seniority,
        technologies=technologies,
    )
