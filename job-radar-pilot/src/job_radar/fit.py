"""Faixa de aderência (rótulo ``FIT:``) de uma vaga, num lugar só.

O classificador grava exatamente um ``FIT:<estado>``; painel, exportações,
limpeza, enriquecimento e reclassificação leem esse estado. Antes cada módulo
tinha a própria leitura; agora todos usam ``fit_state`` e, ao criar uma faixa
nova, basta acrescentá-la aqui (e em ``web/app.js``).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

# Ordem de leitura quando, por algum motivo, houver mais de um rótulo FIT:.
FIT_STATES = ("READY", "CONDITIONAL", "EXCLUDE", "AMBIGUOUS")
DEFAULT_FIT = "AMBIGUOUS"
FIT_NAMES = {
    "READY": "Mais compatível",
    "CONDITIONAL": "Condicional",
    "AMBIGUOUS": "Dados insuficientes",
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
