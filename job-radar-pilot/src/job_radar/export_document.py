from __future__ import annotations

from html import escape as escape_html
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from job_radar.fit import fit_state


_MARKDOWN_SPECIALS = "\\`*{}[]<>()#+-.!|"

# Razões de parada da coleta: texto amigável + se é um limite esperado (False)
# ou algo a verificar (True). Códigos desconhecidos contam como "a verificar".
_COVERAGE_REASONS: dict[str, tuple[str, bool]] = {
    "EXHAUSTED": ("fim da lista de vagas", False),
    "PAGE_LIMIT": ("atingiu o limite de páginas configurado", False),
    "EMPTY_PAGE_AFTER_RECORDS": ("fim dos resultados", False),
    "STOPPED_BY_USER": ("interrompido por você", False),
    # Toda varredura tem consultas que o portal rejeita: estrutural, não alarme.
    "QUERY_SWEEP_PARTIAL": ("varredura de consultas incompleta", False),
    "PAGINATION_UNVERIFIED": ("paginação não confirmada", True),
    "SELECTOR_RELOCATED": ("seletor fora do lugar", True),
    "NO_RESULTS": ("nenhum resultado", True),
    "LAYOUT_CHANGED": ("layout do portal mudou", True),
    # O "próxima página" do portal apontou para uma página já visitada: fim
    # detectado por repetição, não há o que corrigir no coletor.
    "PAGINATION_LOOP": ("paginação repetida no portal", False),
}


def _coverage_reason(stop_reason: str, status: str) -> tuple[str, bool]:
    """(texto, precisa_verificar) de uma razão de parada."""

    text, attention = _COVERAGE_REASONS.get(stop_reason, ("", True))
    if status not in {"SUCCESS", "EMPTY", "PARTIAL"}:
        attention = True
    return text, attention


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
    preserve_order: bool = False,
) -> str:
    groups: dict[str, list[Mapping[str, Any]]] = {
        "ready": [],
        "conditional": [],
        "ambiguous": [],
        "other_stack": [],
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
        attention = 0
        rendered: list[str] = []
        for source in sources:
            source_name = _safe_text(source.get("source"), "Portal nao informado")
            status = str(source.get("status") or "DESCONHECIDO")
            stop_reason = str(source.get("stop_reason") or "EXHAUSTED")
            reason_text, needs_check = _coverage_reason(stop_reason, status)
            if needs_check:
                attention += 1
            detail = f"{stop_reason} — {reason_text}" if reason_text else stop_reason
            suffix = " (verificar)" if needs_check and status == "PARTIAL" else ""
            source_state = _safe_text(f"{status} ({detail}){suffix}", "DESCONHECIDO")
            rendered.append(f"- {source_name}: {source_state}")
        partial_note = ""
        if partial_count:
            expected = partial_count - sum(
                1
                for source in sources
                if str(source.get("status")) == "PARTIAL"
                and _coverage_reason(
                    str(source.get("stop_reason") or ""), "PARTIAL"
                )[1]
            )
            partial_note = f" ({expected} no limite esperado, {partial_count - expected} a verificar)"
        lines.append(
            f"Completos: {complete_count}; parciais: {partial_count}{partial_note}; "
            f"sem vagas: {empty_count}; bloqueados ou com erro: {problem_count}."
        )
        lines.extend(rendered)
    else:
        lines.append("Cobertura detalhada nao disponivel.")

    headings = (
        ("ready", "Mais compativeis"),
        ("conditional", "A revisar"),
        ("ambiguous", "Dados insuficientes"),
        ("other_stack", "Outra stack"),
        ("exclude", "Fora do perfil"),
    )
    if preserve_order:
        groups = {"selection": list(jobs)}
        headings = (("selection", "Vagas na ordem da tabela"),)
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
