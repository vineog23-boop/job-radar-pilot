"""Stacks pré-definidas e sugestão de termos de busca para o perfil.

Serve para qualquer pessoa montar um perfil sem conhecer o YAML: escolhe níveis
e stacks e o Radar sugere tecnologias (para pontuar) e termos de busca (para os
portais).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Iterable
import unicodedata

MAX_SEARCH_TERMS = 20


@dataclass(frozen=True, slots=True)
class StackPreset:
    id: str
    label: str
    technologies: tuple[str, ...]
    queries: tuple[str, ...]


# Ordem = ordem de exibição no painel.
STACKS: tuple[StackPreset, ...] = (
    StackPreset(
        "java", "Java / Spring",
        ("java", "spring boot", "jpa", "hibernate", "api rest", "maven", "junit", "sql", "docker"),
        ("java", "spring boot"),
    ),
    StackPreset(
        "python", "Python",
        ("python", "django", "flask", "fastapi", "pandas", "api rest", "sql", "docker"),
        ("python", "django"),
    ),
    StackPreset(
        "node", "Node.js / TypeScript",
        ("node", "typescript", "javascript", "nestjs", "express", "api rest", "sql", "docker"),
        ("node", "typescript"),
    ),
    StackPreset(
        "frontend", "Front-end (React, Angular, Vue)",
        ("react", "next.js", "angular", "vue", "typescript", "javascript", "html", "css", "tailwind"),
        ("react", "frontend"),
    ),
    StackPreset(
        "dotnet", ".NET / C#",
        ("c#", ".net", "asp.net", "entity framework", "sql server", "api rest", "azure"),
        (".net", "c#"),
    ),
    StackPreset(
        "php", "PHP / Laravel",
        ("php", "laravel", "symfony", "mysql", "api rest"),
        ("php", "laravel"),
    ),
    StackPreset(
        "go", "Go",
        ("golang", "api rest", "docker", "kubernetes", "postgresql"),
        ("golang", "backend go"),
    ),
    StackPreset(
        "mobile", "Mobile",
        ("android", "kotlin", "ios", "swift", "flutter", "react native", "dart"),
        ("mobile", "flutter"),
    ),
    StackPreset(
        "dados", "Dados / BI",
        ("sql", "python", "power bi", "etl", "spark", "bigquery", "dbt", "engenheiro de dados"),
        ("analista de dados", "engenheiro de dados"),
    ),
    StackPreset(
        "devops", "DevOps / Cloud",
        ("devops", "docker", "kubernetes", "terraform", "aws", "azure", "ci/cd", "linux"),
        ("devops", "sre"),
    ),
    StackPreset(
        "qa", "QA / Testes",
        ("qa", "testes automatizados", "selenium", "cypress", "jest", "postman"),
        ("qa", "analista de testes"),
    ),
    StackPreset(
        "fullstack", "Full stack",
        ("full stack", "javascript", "typescript", "react", "node", "api rest", "sql"),
        ("full stack", "fullstack"),
    ),
    StackPreset(
        "kotlin", "Kotlin (back-end)",
        ("kotlin", "spring boot", "ktor", "api rest", "jvm", "sql"),
        ("kotlin", "backend kotlin"),
    ),
    StackPreset(
        "ruby", "Ruby on Rails",
        ("ruby", "rails", "rspec", "postgresql", "api rest"),
        ("ruby on rails", "ruby"),
    ),
    StackPreset(
        "rust", "Rust",
        ("rust", "tokio", "webassembly", "linux", "api rest"),
        ("rust", "desenvolvedor rust"),
    ),
    StackPreset(
        "cpp", "C / C++ / Embarcados",
        ("c++", "linguagem c", "embarcados", "firmware", "iot", "rtos", "linux"),
        ("c++", "sistemas embarcados"),
    ),
    StackPreset(
        "ia", "IA / Machine Learning",
        ("machine learning", "python", "pytorch", "tensorflow", "scikit-learn", "llm", "nlp", "mlops"),
        ("machine learning", "cientista de dados"),
    ),
    StackPreset(
        "seguranca", "Segurança da informação",
        ("seguranca da informacao", "pentest", "soc", "siem", "iso 27001", "cybersecurity", "owasp"),
        ("seguranca da informacao", "analista soc"),
    ),
    StackPreset(
        "infra", "Suporte / Infraestrutura",
        ("suporte tecnico", "help desk", "redes", "windows server", "active directory", "linux", "itil"),
        ("suporte tecnico", "infraestrutura ti"),
    ),
    StackPreset(
        "salesforce", "Salesforce",
        ("salesforce", "apex", "lightning", "visualforce", "crm"),
        ("salesforce", "desenvolvedor salesforce"),
    ),
    StackPreset(
        "sap", "SAP / ABAP",
        ("sap", "abap", "fiori", "s/4hana", "sap hana"),
        ("sap", "abap"),
    ),
    StackPreset(
        "lowcode", "Low-code / RPA",
        ("rpa", "uipath", "power automate", "power apps", "outsystems", "blue prism"),
        ("rpa", "outsystems"),
    ),
    StackPreset(
        "games", "Games",
        ("unity", "c#", "unreal", "game design", "3d"),
        ("desenvolvedor de jogos", "unity"),
    ),
    StackPreset(
        "produto", "Produto / Agilidade",
        ("product owner", "scrum", "kanban", "jira", "metricas", "agile"),
        ("product owner", "scrum master"),
    ),
    StackPreset(
        "ux", "UX / UI Design",
        ("ux", "ui", "figma", "design system", "prototipacao", "pesquisa com usuarios"),
        ("ux designer", "ui designer"),
    ),
)

MAX_CUSTOM_STACKS = 30
CUSTOM_STACKS_FILE = "custom-stacks.json"

# Palavra usada na busca de texto dos portais para cada nível.
LEVEL_WORDS = {
    "estagio": "estagio",
    "junior": "junior",
    "pleno": "pleno",
    "senior": "senior",
}
LEVELS: tuple[tuple[str, str], ...] = (
    ("estagio", "Estágio"),
    ("junior", "Júnior"),
    ("pleno", "Pleno"),
    ("senior", "Sênior"),
)


class StackError(ValueError):
    """Stack personalizada fora do contrato."""


def custom_stacks_path(preferences_path: Path) -> Path:
    return preferences_path.parent / CUSTOM_STACKS_FILE


def _clean_items(values: object, *, field: str, maximum: int, minimum: int = 0) -> tuple[str, ...]:
    if isinstance(values, str):
        values = re.split(r"[,\n;]", values)
    if not isinstance(values, (list, tuple)):
        raise StackError(f"{field} deve ser uma lista de textos.")
    items: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise StackError(f"{field} deve conter apenas textos.")
        cleaned = " ".join(value.split()).casefold()
        if not cleaned:
            continue
        if len(cleaned) > 60:
            raise StackError(f"{field}: '{cleaned[:20]}…' passa de 60 caracteres.")
        if cleaned not in items:
            items.append(cleaned)
    if not minimum <= len(items) <= maximum:
        raise StackError(f"{field} deve ter de {minimum} a {maximum} itens.")
    return tuple(items)


def _slug(label: str) -> str:
    ascii_label = "".join(
        char
        for char in unicodedata.normalize("NFKD", label.casefold())
        if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_label).strip("-")[:40]


def make_custom_stack(label: object, technologies: object, queries: object = ()) -> StackPreset:
    if not isinstance(label, str) or not 1 <= len(" ".join(label.split())) <= 40:
        raise StackError("O nome da stack deve ter de 1 a 40 caracteres.")
    clean_label = " ".join(label.split())
    slug = _slug(clean_label)
    if not slug:
        raise StackError("O nome da stack precisa ter letras ou números.")
    techs = _clean_items(technologies, field="Tecnologias", maximum=30, minimum=1)
    terms = _clean_items(queries, field="Termos de busca", maximum=6)
    return StackPreset(f"custom-{slug}", clean_label, techs, terms or techs[:2])


def load_custom_stacks(preferences_path: Path | None) -> tuple[StackPreset, ...]:
    if preferences_path is None:
        return ()
    try:
        raw = json.loads(custom_stacks_path(preferences_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    stacks: list[StackPreset] = []
    for item in raw if isinstance(raw, list) else []:
        try:
            stacks.append(
                make_custom_stack(item["label"], item["technologies"], item.get("queries", ()))
            )
        except (KeyError, TypeError, StackError):
            continue
    return tuple(stacks[:MAX_CUSTOM_STACKS])


def _write_custom_stacks(preferences_path: Path, stacks: Iterable[StackPreset]) -> None:
    path = custom_stacks_path(preferences_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {"label": stack.label, "technologies": list(stack.technologies), "queries": list(stack.queries)}
        for stack in stacks
    ]
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def save_custom_stack(preferences_path: Path, stack: StackPreset) -> tuple[StackPreset, ...]:
    """Cria ou substitui (mesmo nome) uma stack personalizada."""

    if any(_slug(stack.label) == preset.id for preset in STACKS):
        raise StackError("Já existe uma stack pronta com esse nome.")
    current = [item for item in load_custom_stacks(preferences_path) if item.id != stack.id]
    if len(current) >= MAX_CUSTOM_STACKS:
        raise StackError(f"Limite de {MAX_CUSTOM_STACKS} stacks personalizadas.")
    stacks = (*current, stack)
    _write_custom_stacks(preferences_path, stacks)
    return stacks


def delete_custom_stack(preferences_path: Path, stack_id: object) -> tuple[StackPreset, ...]:
    current = load_custom_stacks(preferences_path)
    remaining = tuple(item for item in current if item.id != stack_id)
    if len(remaining) == len(current):
        raise StackError("Stack personalizada não encontrada.")
    _write_custom_stacks(preferences_path, remaining)
    return remaining


def _stack_payload(stack: StackPreset, *, custom: bool) -> dict[str, object]:
    return {
        "id": stack.id,
        "label": stack.label,
        "technologies": list(stack.technologies),
        "queries": list(stack.queries),
        "custom": custom,
    }


def presets_payload(custom: Iterable[StackPreset] = ()) -> dict[str, object]:
    return {
        "levels": [{"id": key, "label": label} for key, label in LEVELS],
        "stacks": [_stack_payload(stack, custom=False) for stack in STACKS]
        + [_stack_payload(stack, custom=True) for stack in custom],
    }


def _stack_by_id(stack_id: str, custom: Iterable[StackPreset] = ()) -> StackPreset | None:
    return next((stack for stack in (*STACKS, *custom) if stack.id == stack_id), None)


# --- termos de busca da área -----------------------------------------------------
# Recrutador escreve o cargo de vários jeitos ("Desenvolvedor Java Jr",
# "Programador Java Júnior", "Estagiário Java"). O catálogo combina, para cada
# stack, a tecnologia principal, os cargos mais usados e os sinônimos de nível, e
# ordena por prioridade: o que mais traz vaga boa vem primeiro.

LEVEL_SYNONYMS: dict[str, tuple[str, ...]] = {
    "estagio": ("estagio", "estagiario"),
    "junior": ("junior", "jr"),
    "pleno": ("pleno",),
    "senior": ("senior", "sr"),
}
DEV_ROLES = ("desenvolvedor", "programador", "dev")
# Cargos (sem nível) mais usados em cada área.
ROLE_TITLES: dict[str, tuple[str, ...]] = {
    "java": ("desenvolvedor java", "programador java", "dev java", "backend java"),
    "python": ("desenvolvedor python", "programador python", "dev python", "backend python"),
    "node": ("desenvolvedor node", "desenvolvedor javascript", "dev node", "backend node"),
    "frontend": ("desenvolvedor front end", "desenvolvedor react", "programador front end", "dev frontend"),
    "dotnet": ("desenvolvedor .net", "desenvolvedor c#", "programador c#", "dev .net"),
    "php": ("desenvolvedor php", "programador php", "dev php"),
    "go": ("desenvolvedor go", "desenvolvedor golang", "dev golang"),
    "mobile": ("desenvolvedor mobile", "desenvolvedor android", "desenvolvedor ios", "desenvolvedor flutter"),
    "dados": ("analista de dados", "engenheiro de dados", "analista de bi", "cientista de dados"),
    "devops": ("analista devops", "engenheiro devops", "engenheiro de cloud", "analista de infraestrutura cloud"),
    "qa": ("analista de testes", "analista de qa", "qa automacao", "testador"),
    "fullstack": ("desenvolvedor full stack", "desenvolvedor fullstack", "programador full stack", "dev full stack"),
    "kotlin": ("desenvolvedor kotlin", "dev kotlin", "backend kotlin"),
    "ruby": ("desenvolvedor ruby", "desenvolvedor ruby on rails"),
    "rust": ("desenvolvedor rust", "dev rust"),
    "cpp": ("desenvolvedor c++", "programador c++", "desenvolvedor embarcados", "engenheiro de firmware"),
    "ia": ("engenheiro de machine learning", "cientista de dados", "engenheiro de ia", "analista de ia"),
    "seguranca": ("analista de seguranca da informacao", "analista soc", "analista de ciberseguranca", "pentester"),
    "infra": ("analista de suporte", "tecnico de suporte", "analista de infraestrutura", "analista de redes", "help desk"),
    "salesforce": ("desenvolvedor salesforce", "consultor salesforce", "analista salesforce"),
    "sap": ("consultor sap", "desenvolvedor abap", "analista sap"),
    "lowcode": ("desenvolvedor rpa", "desenvolvedor outsystems", "analista rpa", "desenvolvedor power platform"),
    "games": ("desenvolvedor de jogos", "desenvolvedor unity", "programador de jogos"),
    "produto": ("product owner", "scrum master", "analista de produto", "product manager"),
    "ux": ("ux designer", "ui designer", "product designer", "ux ui designer"),
}
# Áreas de desenvolvimento: ganham os termos gerais "desenvolvedor junior" etc.
_DEV_STACKS = {
    "java", "python", "node", "frontend", "dotnet", "php", "go", "mobile", "fullstack",
    "kotlin", "ruby", "rust", "cpp", "salesforce", "lowcode", "games",
}
GENERAL_TERMS: dict[str, tuple[str, ...]] = {
    "estagio": ("estagio ti", "estagio desenvolvimento", "estagio programacao", "trainee ti"),
    "junior": ("desenvolvedor junior", "programador junior", "analista de sistemas junior"),
    "pleno": ("desenvolvedor pleno", "analista de sistemas pleno"),
    "senior": ("desenvolvedor senior", "analista de sistemas senior"),
}
GENERAL_IT_TERMS: dict[str, tuple[str, ...]] = {
    "estagio": ("estagio ti", "estagio tecnologia"),
    "junior": ("analista de ti junior",),
    "pleno": ("analista de ti pleno",),
    "senior": ("analista de ti senior",),
}


def _roles_for(stack: StackPreset) -> tuple[str, ...]:
    roles = ROLE_TITLES.get(stack.id)
    if roles:
        return roles
    core = stack.queries[0] if stack.queries else stack.label.casefold()
    return tuple(f"{role} {core}" for role in DEV_ROLES)


def _stack_terms(stack: StackPreset, levels: list[str]) -> list[tuple[int, str]]:
    """(prioridade, termo) de uma stack; 1 = mais importante."""

    queries = list(stack.queries) or [stack.label.casefold()]
    roles = list(_roles_for(stack))
    core = queries[0]
    terms: list[tuple[int, str]] = []
    if not levels:
        terms += [(1, query) for query in queries]
        terms += [(2, role) for role in roles]
        return terms
    for level in levels:
        primary, *synonyms = LEVEL_SYNONYMS[level]
        terms.append((1, f"{core} {primary}"))
        terms.append((2, f"{roles[0]} {primary}"))
        terms += [(3, f"{query} {primary}") for query in queries[1:]]
        terms += [(3, f"{role} {primary}") for role in roles[1:]]
        for synonym in synonyms:
            if level == "estagio":
                terms.append((4, f"{synonym} {core}"))  # "estagiario java"
            else:
                terms.append((4, f"{core} {synonym}"))  # "java jr"
                terms.append((4, f"{roles[0]} {synonym}"))
    terms += [(5, query) for query in queries]
    return terms


def term_catalog(
    stack_ids: Iterable[str],
    levels: Iterable[str],
    custom: Iterable[StackPreset] = (),
) -> list[dict[str, object]]:
    """Grupos de termos sugeridos (um por stack + gerais), já com prioridade."""

    custom = tuple(custom)
    stacks = [
        stack
        for stack_id in dict.fromkeys(stack_ids)
        if (stack := _stack_by_id(stack_id, custom))
    ]
    valid_levels = [level for level in dict.fromkeys(levels) if level in LEVEL_SYNONYMS]
    groups: list[dict[str, object]] = []
    for stack in stacks:
        seen: set[str] = set()
        items = []
        for priority, term in _stack_terms(stack, valid_levels):
            if term not in seen:
                seen.add(term)
                items.append({"term": term, "priority": priority})
        groups.append({"id": stack.id, "label": stack.label, "terms": items})
    if stacks and valid_levels:
        dev = any(stack.id in _DEV_STACKS or stack.id.startswith("custom-") for stack in stacks)
        source = GENERAL_TERMS if dev else GENERAL_IT_TERMS
        items = []
        seen = set()
        for level in valid_levels:
            for index, term in enumerate(source[level]):
                if term not in seen:
                    seen.add(term)
                    items.append({"term": term, "priority": 2 if index == 0 else 4})
        groups.append({"id": "geral", "label": "Gerais da área", "terms": items})
    return groups


def recommended_terms(groups: list[dict[str, object]], limit: int = MAX_SEARCH_TERMS) -> list[str]:
    """Escolhe os melhores termos alternando entre os grupos, por prioridade."""

    ranked: list[tuple[int, int, int, str]] = []
    for group_index, group in enumerate(groups):
        position: dict[int, int] = {}
        for item in group["terms"]:  # type: ignore[index]
            priority = int(item["priority"])
            order = position.get(priority, 0)
            position[priority] = order + 1
            ranked.append((priority, order, group_index, str(item["term"])))
    picked: list[str] = []
    for *_, term in sorted(ranked):
        if term not in picked:
            picked.append(term)
        if len(picked) == limit:
            break
    return picked


def suggest(
    stack_ids: Iterable[str],
    levels: Iterable[str],
    custom: Iterable[StackPreset] = (),
) -> dict[str, list[str]]:
    """Tecnologias e termos de busca recomendados para as stacks/níveis escolhidos."""

    custom = tuple(custom)
    stack_ids = list(dict.fromkeys(stack_ids))
    stacks = [stack for stack_id in stack_ids if (stack := _stack_by_id(stack_id, custom))]
    technologies: list[str] = []
    for stack in stacks:
        for technology in stack.technologies:
            if technology not in technologies:
                technologies.append(technology)
    groups = term_catalog(stack_ids, levels, custom)
    return {
        "technologies": technologies[:40],
        "search_terms": recommended_terms(groups),
    }
