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

MAX_SEARCH_TERMS = 12


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


def suggest(
    stack_ids: Iterable[str],
    levels: Iterable[str],
    custom: Iterable[StackPreset] = (),
) -> dict[str, list[str]]:
    """Tecnologias e termos de busca para as stacks/níveis escolhidos.

    Os termos combinam consulta × nível ("java junior", "spring boot estagio"),
    alternando entre as stacks para não deixar uma só ocupar o limite de 12.
    """

    custom = tuple(custom)
    stacks = [
        stack
        for stack_id in dict.fromkeys(stack_ids)
        if (stack := _stack_by_id(stack_id, custom))
    ]
    words = [LEVEL_WORDS[level] for level in dict.fromkeys(levels) if level in LEVEL_WORDS]

    technologies: list[str] = []
    for stack in stacks:
        for technology in stack.technologies:
            if technology not in technologies:
                technologies.append(technology)

    terms: list[str] = []
    depth = max((len(stack.queries) for stack in stacks), default=0)
    for position in range(depth):
        for stack in stacks:
            if position >= len(stack.queries):
                continue
            query = stack.queries[position]
            for word in words or [""]:
                term = f"{query} {word}".strip()
                if term not in terms:
                    terms.append(term)
    return {
        "technologies": technologies[:40],
        "search_terms": terms[:MAX_SEARCH_TERMS],
    }
