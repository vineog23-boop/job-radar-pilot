from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
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
    # Apelidos de tecnologia (1.2): o perfil e a vaga podem usar qualquer forma.
    "spring boot": ("spring boot", "springboot"),
    "node": ("node", "node.js", "nodejs"),
    "javascript": ("javascript", "js"),
    "kubernetes": ("kubernetes", "k8s"),
    "postgresql": ("postgresql", "postgres"),
    "c#": ("c#", "csharp", "c sharp"),
    ".net": (".net", "dotnet"),
    "golang": ("golang", "go"),
}
# Termos de até 2 letras ("go", "js", "r", "c", "c#") colidem com siglas e
# palavras comuns: exigem limites mais rígidos que \w (ver _alias_pattern).
_SHORT_ALIAS_LENGTH = 2
# Contextos em que o termo curto não é a tecnologia.
_SHORT_ALIAS_NOT_AFTER = {
    # UF de Goiás: "Goiânia - GO", "Goiânia, GO", "Goiânia/GO", "(GO)".
    "go": ("- ", ", ", "/ ", "-", ",", "/", "("),
}
_SHORT_ALIAS_NOT_BEFORE = {
    "go": r"\s*-?\s*(?:live|to)\b",  # go-live, go live, go-to-market
    "r": r"\.",  # "R. Augusta" (rua)
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
# Função/área, não stack: "Backend Python" e "Backend Java" têm o mesmo termo.
# Só contam como stack principal quando o perfil não tem nenhuma tecnologia
# específica (ex.: perfil montado apenas com "backend").
_GENERIC_ROLE_TERMS = {
    "backend", "back end", "frontend", "front end", "full stack", "fullstack",
    "api rest", "rest api", "mobile", "desenvolvedor", "programador", "software",
}

# Linguagens/frameworks que definem a stack de uma vaga. Quando a vaga cita
# alguma delas e nenhuma do perfil, ela é de outra stack (FIT:OTHER_STACK), e
# não "dados insuficientes". Chave = nome mostrado; valor = como aparece.
_STACK_SIGNALS: dict[str, tuple[str, ...]] = {
    "java": ("java",),
    "kotlin": ("kotlin",),
    "scala": ("scala",),
    "python": ("python", "django", "flask", "fastapi"),
    "node.js": ("node", "node.js", "nodejs", "nestjs"),
    "javascript": ("javascript",),
    "typescript": ("typescript",),
    "react": ("react", "reactjs", "react.js", "next.js", "nextjs"),
    "angular": ("angular", "angularjs"),
    "vue": ("vue", "vue.js", "vuejs", "nuxt"),
    ".net": (".net", "dotnet", "c#", "csharp", "asp.net"),
    "php": ("php", "laravel", "symfony"),
    "golang": ("golang",),
    "ruby": ("ruby", "rails"),
    "rust": ("rust",),
    "c++": ("c++",),
    "flutter": ("flutter", "dart"),
    "react native": ("react native",),
    "swift": ("swift",),
    "android": ("android",),
    "ios": ("ios",),
    "delphi": ("delphi",),
    "cobol": ("cobol",),
    "elixir": ("elixir",),
    "abap": ("abap",),
    "salesforce": ("salesforce", "apex"),
    "outsystems": ("outsystems",),
    "power bi": ("power bi",),
}
MAX_OTHER_STACK_LABELS = 3


def _core_terms(profile: SearchProfile) -> set[str]:
    """Stack principal do perfil: tecnologias que não são apoio nem função genérica."""

    candidates = {
        canonical
        for canonical in (_canonical_term(keyword) for keyword in profile.positive_keywords)
        if canonical and canonical not in _SECONDARY_TERMS
    }
    specific = candidates - _GENERIC_ROLE_TERMS
    return specific or candidates


def _other_stacks(profile: SearchProfile, searchable_text: str) -> list[str]:
    """Stacks citadas na vaga que não são do perfil (na ordem de _STACK_SIGNALS)."""

    own = {_canonical_term(keyword) for keyword in profile.positive_keywords}
    found: list[str] = []
    for name, aliases in _STACK_SIGNALS.items():
        if own.intersection({_canonical_term(alias) for alias in (name, *aliases)}):
            continue
        if any(_contains_term(searchable_text, alias) for alias in aliases):
            found.append(name)
    return found
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
    r"sistemas?|infraestrutura|redes(?! sociais)|seguranca da informacao|ciberseguranca|mobile|"
    r"android|ios|python|java|javascript|typescript|node|react|angular|sql|php|golang|"
    r"kotlin|scrum|product owner|suporte tecnico|help ?desk|service desk|automacao|"
    r"rpa|sap|erp|totvs|protheus|salesforce|servicenow|engenheir\w* de software|"
    r"analista de testes?|analista de requisitos|cientista de dados|"
    r"c#|\.net|dotnet|golang|flutter|react native|power ?bi|etl|terraform|aws|azure|"
    r"kubernetes|docker|linux|spring|django|laravel|vue|next\.?js|nestjs|spark|"
    r"machine learning|engenheir\w* de dados|analista de bi|arquiteto de software|"
    r"analista programador|tech lead|rust|ruby|rails|c\+\+|embarcad\w*|firmware|unity|unreal|"
    r"abap|outsystems|uipath|power apps|power automate|ux|figma|pentest|cybersecurity|"
    r"seguranca cibernetica|swift|llm|mlops|desenvolvedor de jogos|game developer)(?!\w)"
)

# Tipo de contrato citado na vaga (texto já normalizado, sem acento).
_CONTRACT_MARKERS: dict[str, tuple[str, ...]] = {
    "CLT": ("clt", "regime clt", "carteira assinada"),
    "PJ": ("pj", "pessoa juridica", "cnpj", "contrato pj"),
    "FREELANCE": ("freelancer", "freelance", "freela", "temporario", "temporaria", "por projeto"),
}
# Inglês avançado/fluente pedido na vaga; perto de "diferencial" vira só um plus.
_ADVANCED_ENGLISH = re.compile(
    r"(?<!\w)(?:ingles|english)\s*[(:\-]?\s*(?:nivel\s+)?"
    r"(?:fluente|avancado|fluent|advanced|c1|c2|proficiente)(?!\w)"
    r"|(?<!\w)(?:fluencia|fluente|avancado|proficiencia)\s+(?:(?:em|no|de)\s+)?(?:ingles|english)(?!\w)"
    r"|(?<!\w)(?:fluent|advanced|proficient)\s+(?:in\s+)?english(?!\w)"
    r"|(?<!\w)english fluency(?!\w)"
)
_SENTENCE_END = re.compile(r"[.;!?\n]")
_NICE_TO_HAVE = re.compile(r"diferencia|desejavel|nice to have|\bplus\b|bonus|nao obrigatorio")
# Prefixos dos rótulos que o perfil do painel pode gerar e que tiram a vaga do perfil.
PREFERENCE_BLOCK_PREFIXES = (
    "COMPANY_EXCLUDED:",
    "KEYWORD_BLOCKED:",
    "KEYWORD_MISSING:",
    "CONTRACT_MISMATCH:",
    "LANGUAGE_MISMATCH:",
    "TITLE_EXCLUDED:",
)


# "Não aceitamos PJ", "sem CLT", "(não CLT)": negação logo antes do contrato.
_NEGATION_BEFORE = re.compile(r"(?<!\w)(?:nao|sem|exceto|nem)(?:\s+[\w-]+){0,2}\s*$")
# "PJ não aceito", "CLT: não", "PJ não é aceita": negação logo depois do contrato.
_NEGATION_AFTER = re.compile(
    r"^\s*[:(-]?\s*nao(?:\s+(?:e|sera|serao|sao))?(?:\s+(?:aceit|permitid|possivel|considerad)\w*)?\s*(?:$|[).;,])"
)


def _mentions_contract(text: str, marker: str) -> bool:
    """Contrato citado de forma afirmativa (ignora "não aceitamos PJ")."""

    for pattern in _term_patterns(marker):
        for match in pattern.finditer(text):
            before = _SENTENCE_END.split(text[max(0, match.start() - 30) : match.start()])[-1]
            before = re.split(r"[,(]", before)[-1]
            after = re.split(r"[.;!?\n,]", text[match.end() : match.end() + 40])[0]
            if not _NEGATION_BEFORE.search(before) and not _NEGATION_AFTER.search(after):
                return True
    return False


def _english_requirement(text: str) -> str | None:
    """'required', 'plus' (diferencial) ou None quando a vaga não fala disso."""

    found = None
    for match in _ADVANCED_ENGLISH.finditer(text):
        # "diferencial" só vale na mesma frase: "English: advanced. Bonus points
        # for Docker" continua exigindo inglês.
        before = _SENTENCE_END.split(text[max(0, match.start() - 40) : match.start()])[-1]
        after = _SENTENCE_END.split(text[match.end() : match.end() + 60])[0]
        if _NICE_TO_HAVE.search(f"{before} {after}"):
            found = found or "plus"
        else:
            return "required"
    return found


def _preference_labels(
    record: VacancyRecord, profile: SearchProfile, searchable_text: str
) -> set[str]:
    """Rótulos dos refinos do painel: palavras-chave, empresas, contrato, inglês."""

    labels: set[str] = set()
    company = _normalize(record.company)
    if company:
        for name in profile.excluded_companies:
            if _contains_term(company, _normalize(name)):
                labels.add(f"COMPANY_EXCLUDED:{_normalize(name)}")
        for name in profile.favorite_companies:
            if _contains_term(company, _normalize(name)):
                labels.add(f"COMPANY_FAVORITE:{_normalize(name)}")
    for term in profile.blocked_keywords:
        if _contains_term(searchable_text, term):
            labels.add(f"KEYWORD_BLOCKED:{_canonical_term(term)}")
    if profile.required_keywords:
        matched = [
            _canonical_term(term)
            for term in profile.required_keywords
            if _contains_term(searchable_text, term)
        ]
        labels.update(f"KEYWORD_MATCH:{term}" for term in matched)
        if not matched:
            labels.add("KEYWORD_MISSING:required")
    for term in profile.bonus_keywords:
        if _contains_term(searchable_text, term):
            labels.add(f"BONUS_MATCH:{_canonical_term(term)}")

    contract_text = " ".join(
        part for part in (_normalize(record.employment_type), searchable_text) if part
    )
    detected = {
        kind
        for kind, markers in _CONTRACT_MARKERS.items()
        if any(_mentions_contract(contract_text, marker) for marker in markers)
    }
    labels.update(f"CONTRACT:{kind}" for kind in detected)
    if profile.contract_types and detected and detected.isdisjoint(profile.contract_types):
        labels.update(f"CONTRACT_MISMATCH:{kind}" for kind in detected)

    english = _english_requirement(searchable_text)
    if english == "required":
        labels.add("LANGUAGE:english_advanced")
        if profile.avoid_advanced_english:
            labels.add("LANGUAGE_MISMATCH:english")
    elif english == "plus":
        labels.add("LANGUAGE:english_plus")
    return labels


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


@lru_cache(maxsize=8192)
def _canonical_term(value: str) -> str:
    normalized = _normalize(value)
    return _CANONICAL_TERMS.get(normalized, normalized)


_LEADERSHIP_CANONICAL = frozenset(_canonical_term(term) for term in LEADERSHIP_TERMS)


@lru_cache(maxsize=4096)
def _alias_pattern(alias: str) -> re.Pattern[str] | None:
    """Padrão de um apelido: espaço e hífen intercambiáveis, palavra inteira."""

    parts = [re.escape(part) for part in re.split(r"[\s-]+", alias) if part]
    body = r"[\s-]+".join(parts)
    if not body:
        return None
    if len(alias) > _SHORT_ALIAS_LENGTH:
        return re.compile(rf"(?<!\w){body}(?!\w)")
    # Curto: não pode estar colado a "." ("node.js" não é "js"), "#"/"+" ("c#",
    # "c++" não são "c"), nem ser seguido de "$" ("R$") ou "-palavra"/".palavra".
    before = "".join(f"(?<!{re.escape(text)})" for text in _SHORT_ALIAS_NOT_AFTER.get(alias, ()))
    after = _SHORT_ALIAS_NOT_BEFORE.get(alias)
    extra = f"(?!{after})" if after else ""
    return re.compile(rf"(?<![\w.#+-]){before}{body}(?![\w#+$]|[-.]\w){extra}")


@lru_cache(maxsize=4096)
def _term_patterns(term: str) -> tuple[re.Pattern[str], ...]:
    canonical = _canonical_term(term)
    aliases = _TERM_ALIASES.get(canonical, (canonical,))
    return tuple(pattern for alias in aliases if (pattern := _alias_pattern(alias)))


def _contains_term(searchable_text: str, term: str) -> bool:
    return any(pattern.search(searchable_text) for pattern in _term_patterns(term))


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
            is_level = canonical in SENIORITY_LEVELS or canonical in _LEADERSHIP_CANONICAL
            labels.add(f"{'SENIORITY_MISMATCH' if is_level else 'TITLE_EXCLUDED'}:{canonical}")
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
    labels |= _preference_labels(record, profile, searchable_text)
    has_preference_block = any(
        label.startswith(PREFERENCE_BLOCK_PREFIXES) for label in labels
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

    other_stacks: list[str] = []
    if record.source in _CURATED_ARTICLE_SOURCES:
        labels.add("SOURCE_TYPE:CURATED_ARTICLE")
        fit = "AMBIGUOUS"
        score = 0
    elif (
        has_seniority_mismatch
        or has_location_mismatch
        or has_workplace_mismatch
        or has_preference_block
    ):
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
            # Sem stack principal no perfil (só ferramentas de apoio) não existe
            # "outra stack": a vaga continua com poucos dados.
            other_stacks = _other_stacks(profile, searchable_text) if core_terms else []
            if other_stacks:
                # Vaga de TI de outra stack: "backend"/"docker" não valem como
                # ponto de tecnologia para ela.
                fit = "OTHER_STACK"
                score -= int(has_technology)
                labels.update(
                    f"OTHER_STACK:{name}"
                    for name in other_stacks[:MAX_OTHER_STACK_LABELS]
                )
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
    return replace(
        record,
        match_labels=tuple(sorted(labels)),
        workplace_model=workplace_model,
        seniority=seniority,
    )
