from __future__ import annotations

from html import escape as escape_html
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from job_radar.fit import fit_state


_MARKDOWN_SPECIALS = "\\`*{}[]<>()#+-.!|"


def _safe_text(value: Any, fallback: str) -> str:
    text = " ".join(str(value or "").split()) or fallback
    escaped = escape_html(text, quote=False)
    for character in _MARKDOWN_SPECIALS:
        escaped = escaped.replace(character, f"\\{character}")
    return escaped


def _safe_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if any(character.isspace() or ord(character) < 32 for character in text):
        return None
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return text.replace("(", "%28").replace(")", "%29")


def _fit_group(job: Mapping[str, Any]) -> str:
    return fit_state(job).casefold()


def build_markdown_report(
    jobs: Sequence[Mapping[str, Any]],
    *,
    generated_at: str,
    sources: Sequence[Mapping[str, Any]] = (),
    applied_filters: Mapping[str, str] | None = None,
) -> str:
    groups: dict[str, list[Mapping[str, Any]]] = {
        "ready": [],
        "conditional": [],
        "ambiguous": [],
        "exclude": [],
    }
    for job in jobs:
        groups[_fit_group(job)].append(job)

    lines = [
        "# Relatorio de vagas",
        "",
        f"Gerado em {_safe_text(generated_at, 'data nao informada')}.",
        "",
        f"Total: {len(jobs)} vagas.",
    ]
    active_filters = {
        key: value
        for key, value in (applied_filters or {}).items()
        if value
    }
    if active_filters:
        filter_labels = {"text": "texto", "source": "portal", "match": "aderencia"}
        rendered_filters = ", ".join(
            f"{filter_labels.get(key, key)}={_safe_text(value, '-') }"
            for key, value in active_filters.items()
        )
        lines.extend(("", f"Filtros aplicados: {rendered_filters}."))

    lines.extend(("", "## Cobertura da coleta", ""))
    if sources:
        statuses = [str(source.get("status") or "DESCONHECIDO") for source in sources]
        complete_count = statuses.count("SUCCESS")
        partial_count = statuses.count("PARTIAL")
        empty_count = statuses.count("EMPTY")
        problem_count = len(statuses) - complete_count - partial_count - empty_count
        lines.append(
            f"Completos: {complete_count}; parciais: {partial_count}; "
            f"sem vagas: {empty_count}; bloqueados ou com erro: {problem_count}."
        )
        for source in sources:
            source_name = _safe_text(source.get("source"), "Portal nao informado")
            status = str(source.get("status") or "DESCONHECIDO")
            stop_reason = str(source.get("stop_reason") or "EXHAUSTED")
            source_state = _safe_text(f"{status} ({stop_reason})", "DESCONHECIDO")
            lines.append(f"- {source_name}: {source_state}")
    else:
        lines.append("Cobertura detalhada nao disponivel.")

    headings = (
        ("ready", "Mais compativeis"),
        ("conditional", "A revisar"),
        ("ambiguous", "Dados insuficientes"),
        ("exclude", "Fora do perfil"),
    )
    for key, label in headings:
        group = groups[key]
        lines.extend(("", f"## {label} ({len(group)})", ""))
        if not group:
            lines.append("Nenhuma vaga neste grupo.")
            continue
        for job in group:
            lines.extend(
                (
                    f"### {_safe_text(job.get('title'), 'Cargo nao informado')}",
                    "",
                    f"- Empresa: {_safe_text(job.get('company'), 'Empresa nao informada')}",
                    f"- Local: {_safe_text(job.get('location'), 'Local nao informado')}",
                    f"- Origem: {_safe_text(job.get('source'), 'Origem nao informada')}",
                )
            )
            url = _safe_url(job.get("canonical_url"))
            lines.append(f"- [Abrir vaga]({url})" if url else "- Link indisponivel")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
