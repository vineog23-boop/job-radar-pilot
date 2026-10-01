"""Faixa de aderência (rótulo ``FIT:``) de uma vaga, num lugar só.

O classificador grava exatamente um ``FIT:<estado>``; painel, exportações,
limpeza, enriquecimento e reclassificação leem esse estado. Antes cada módulo
tinha a própria leitura; agora todos usam ``fit_state`` e, ao criar uma faixa
nova, basta acrescentá-la aqui (e em ``web/app.js``).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

# Ordem de leitura quando, por algum motivo, houver mais de um rótulo FIT:.
FIT_STATES = ("READY", "CONDITIONAL", "EXCLUDE", "OTHER_STACK", "AMBIGUOUS")
DEFAULT_FIT = "AMBIGUOUS"
FIT_NAMES = {
    "READY": "Mais compatível",
    "CONDITIONAL": "Condicional",
    "AMBIGUOUS": "Dados insuficientes",
    "OTHER_STACK": "Outra stack",
    "EXCLUDE": "Fora do perfil",
}


def labels_of(job_or_labels: Mapping[str, Any] | Iterable[Any] | None) -> list[str]:
    """Rótulos de uma vaga (payload/dicionário) ou de uma lista de rótulos."""

    if job_or_labels is None:
        return []
    if isinstance(job_or_labels, Mapping):
        raw = job_or_labels.get("match_labels") or ()
    else:
        raw = job_or_labels
    if isinstance(raw, (str, bytes)):
        return []
    try:
        return [str(label) for label in raw]
    except TypeError:
        return []


def fit_state(job_or_labels: Mapping[str, Any] | Iterable[Any] | None) -> str:
    """``READY``, ``CONDITIONAL``, ``EXCLUDE`` ou ``AMBIGUOUS`` (padrão)."""

    labels = set(labels_of(job_or_labels))
    for state in FIT_STATES:
        if f"FIT:{state}" in labels:
            return state
    return DEFAULT_FIT


def fit_name(job_or_labels: Mapping[str, Any] | Iterable[Any] | None) -> str:
    return FIT_NAMES[fit_state(job_or_labels)]


# Motivos em português para a vaga não ser "Mais compatível" (painel, CSV, xlsx).
REASON_LABELS = (
    ("RELEVANCE:OFF_TOPIC", "fora da área de tecnologia"),
    ("SENIORITY_MISMATCH:", "nível acima do desejado"),
    ("LOCATION_MISMATCH:", "fora das localidades escolhidas"),
    ("WORKPLACE_MISMATCH:", "modelo de trabalho diferente"),
    ("LOCATION_UNCLEAR:", "local não confirmado"),
    ("WORKPLACE_UNCLEAR:", "modelo de trabalho não confirmado"),
    ("SENIORITY_UNCLEAR:", "faixa de nível ampla (júnior/pleno)"),
    ("ELIGIBILITY_UNCLEAR:", "vaga com público restrito"),
    ("TITLE_EXCLUDED:", "cargo com um termo que você não quer"),
    ("KEYWORD_BLOCKED:", "cita uma palavra proibida"),
    ("KEYWORD_MISSING:", "não cita nenhuma palavra obrigatória"),
    ("COMPANY_EXCLUDED:", "empresa que você quer evitar"),
    ("CONTRACT_MISMATCH:", "tipo de contrato diferente"),
    ("LANGUAGE_MISMATCH:", "exige inglês avançado"),
)


def is_off_topic(job_or_labels: Mapping[str, Any] | Iterable[Any] | None) -> bool:
    return "RELEVANCE:OFF_TOPIC" in labels_of(job_or_labels)


def fit_reasons(job_or_labels: Mapping[str, Any] | Iterable[Any] | None) -> list[str]:
    """Explica em português por que a vaga não é 'Mais compatível'."""

    labels = labels_of(job_or_labels)
    reasons = [
        text
        for prefix, text in REASON_LABELS
        if any(label.startswith(prefix) for label in labels)
    ]
    stacks = [label.removeprefix("OTHER_STACK:") for label in labels if label.startswith("OTHER_STACK:")]
    if stacks:
        reasons.append(f"stack diferente da sua ({', '.join(stacks)})")
    if not reasons and fit_state(labels) == "AMBIGUOUS":
        reasons.append("poucos dados para avaliar")
    return reasons
