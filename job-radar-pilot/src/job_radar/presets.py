"""Stacks pré-definidas e sugestão de termos de busca para o perfil.

Serve para qualquer pessoa montar um perfil sem conhecer o YAML: escolhe níveis
e stacks e o Radar sugere tecnologias (para pontuar) e termos de busca (para os
portais).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

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
)

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


def presets_payload() -> dict[str, object]:
    return {
        "levels": [{"id": key, "label": label} for key, label in LEVELS],
        "stacks": [
            {
                "id": stack.id,
                "label": stack.label,
                "technologies": list(stack.technologies),
                "queries": list(stack.queries),
            }
            for stack in STACKS
        ],
    }


def _stack_by_id(stack_id: str) -> StackPreset | None:
    return next((stack for stack in STACKS if stack.id == stack_id), None)


def suggest(
    stack_ids: Iterable[str], levels: Iterable[str]
) -> dict[str, list[str]]:
    """Tecnologias e termos de busca para as stacks/níveis escolhidos.

    Os termos combinam consulta × nível ("java junior", "spring boot estagio"),
    alternando entre as stacks para não deixar uma só ocupar o limite de 12.
    """

    stacks = [
        stack for stack_id in dict.fromkeys(stack_ids) if (stack := _stack_by_id(stack_id))
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
