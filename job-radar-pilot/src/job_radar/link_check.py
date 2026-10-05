"""Verificação real de disponibilidade: refaz o fetch do link no momento da checagem.

``activity.py`` infere a situação da vaga só pelas datas salvas (sem acessar a
rede de novo); isso não prova que a vaga ainda está no ar — um agregador pode
continuar listando uma vaga removida, ou a página pode ter sido tirada do ar
depois da coleta. Este módulo faz a prova real: busca o ``canonical_url`` de
novo, agora, e classifica a página em LIVE/DEAD/UNKNOWN.

Os rótulos ficam em ``match_labels`` (``LINK:LIVE`` / ``LINK:DEAD`` /
``LINK:UNKNOWN`` + ``LINK_CHECKED_AT:<iso>``), seguindo a mesma convenção dos
demais rótulos do classificador. Nenhum campo novo entra no schema.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from job_radar.fetching import FetchPolicy, _visible_response_text
from job_radar.fit import fit_state
from job_radar.models import CollectionStatus, SourceConfig, SourceKind, VacancyRecord

LINK_LIVE = "LINK:LIVE"
LINK_DEAD = "LINK:DEAD"
LINK_UNKNOWN = "LINK:UNKNOWN"
_LINK_PREFIX = "LINK:"
_CHECKED_AT_PREFIX = "LINK_CHECKED_AT:"

# Mensagens típicas de "vaga removida" nos portais já vistos (soft-404: a
# página responde 200, mas o conteúdo diz que a vaga não existe mais).
_DEAD_MARKERS: tuple[str, ...] = (
    "vaga não encontrada",
    "vaga nao encontrada",
    "vaga não encontrada ou erro",
    "vaga expirada",
    "vaga encerrada",
    "esta vaga não está mais disponível",
    "esta vaga nao esta mais disponivel",
    "vaga removida",
    "vaga foi encerrada",
    "oferta expirada",
    "position has been filled",
    "position is no longer available",
    "job not found",
    "job no longer available",
    "this job is no longer available",
    "página não encontrada",
    "pagina nao encontrada",
    "page not found",
    "404 not found",
)

# Texto visível mínimo para considerar a página "com conteúdo" (abaixo disso,
# pode ser um shell vazio de SPA que nossa busca estática não renderiza).
_MIN_LIVE_TEXT_CHARS = 120

DEFAULT_VERIFY_LIMIT = 80
_SKIP_SOURCES = {"indeed"}  # bloqueia scraping direto (403); checagem fica UNKNOWN.


def classify_page_text(text: str | None) -> str:
    """LIVE/DEAD/UNKNOWN a partir do texto visível já buscado agora."""

    if not text:
        return LINK_UNKNOWN
    folded = " ".join(text.split()).casefold()
    for marker in _DEAD_MARKERS:
        if marker in folded:
            return LINK_DEAD
    if len(folded) >= _MIN_LIVE_TEXT_CHARS:
        return LINK_LIVE
    return LINK_UNKNOWN


def check_canonical_url(
    url: str,
    source: SourceConfig,
    fetcher: FetchPolicy,
) -> str:
    """Busca ``url`` agora (sem navegador pesado) e classifica o resultado."""

    static_source = replace(source, kind=SourceKind.GENERIC, adaptive=False)
    try:
        fetched = fetcher.fetch(url, static_source)
    except Exception:
        return LINK_UNKNOWN
    if fetched.status is CollectionStatus.BLOCKED:
        return LINK_UNKNOWN
    if fetched.status is not CollectionStatus.SUCCESS or fetched.response is None:
        return LINK_UNKNOWN
    text = _visible_response_text(fetched.response)
    return classify_page_text(text)


def _is_best_fit(record: VacancyRecord) -> bool:
    return fit_state(record.match_labels) in {"READY", "CONDITIONAL"}


def _without_link_labels(labels: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        label
        for label in labels
        if not label.startswith(_LINK_PREFIX) and not label.startswith(_CHECKED_AT_PREFIX)
    )


def verify_records(
    records: Sequence[VacancyRecord],
    sources: Sequence[SourceConfig],
    *,
    limit: int | None = DEFAULT_VERIFY_LIMIT,
    only_best_fit: bool = True,
    fetcher_factory: Callable[[], FetchPolicy] = FetchPolicy,
    now: datetime | None = None,
) -> tuple[tuple[VacancyRecord, ...], dict[str, int]]:
    """Reconfirma, agora, se cada vaga candidata ainda está no ar.

    Só refaz o fetch de registros com ``canonical_url`` https; fontes que
    bloqueiam scraping direto (``indeed``) ficam ``LINK:UNKNOWN`` sem gastar
    requisição. ``limit`` None ou <= 0 verifica todas as candidatas. Devolve
    os registros atualizados (rótulo ``LINK:*`` + ``LINK_CHECKED_AT:<iso>``) e
    um resumo de contagens.
    """

    moment = now or datetime.now(timezone.utc)
    checked_at = moment.isoformat(timespec="seconds")
    by_code = {source.code: source for source in sources}
    candidates: list[int] = []
    for index, record in enumerate(records):
        if only_best_fit and not _is_best_fit(record):
            continue
        if not (record.canonical_url or "").startswith("https://"):
            continue
        candidates.append(index)
    picked = candidates if not limit or limit <= 0 else candidates[:limit]

    updated = list(records)
    counts = {LINK_LIVE: 0, LINK_DEAD: 0, LINK_UNKNOWN: 0}
    with fetcher_factory() as fetcher:
        for index in picked:
            record = records[index]
            source = by_code.get(record.source)
            if source is None or record.source in _SKIP_SOURCES:
                status = LINK_UNKNOWN
            else:
                status = check_canonical_url(record.canonical_url, source, fetcher)
            counts[status] += 1
            labels = (
                *_without_link_labels(record.match_labels),
                status,
                f"{_CHECKED_AT_PREFIX}{checked_at}",
            )
            updated[index] = replace(record, match_labels=labels)
    return tuple(updated), counts


def link_status(labels: Sequence[str]) -> str | None:
    for label in labels:
        if label in (LINK_LIVE, LINK_DEAD, LINK_UNKNOWN):
            return label
    return None


def verify_output(
    output_dir: Path,
    sources: Sequence[SourceConfig],
    *,
    limit: int | None = DEFAULT_VERIFY_LIMIT,
    only_best_fit: bool = True,
    fetcher_factory: Callable[[], FetchPolicy] = FetchPolicy,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Relê ``vagas.jsonl``, reconfirma os links candidatos e regrava o arquivo.

    Só os rótulos ``LINK:*``/``LINK_CHECKED_AT:`` mudam; nada é descartado e
    nenhum outro campo é tocado (mesmo padrão de ``reclassify_output``).
    """

    from job_radar.output import _record_payload, rewrite_payloads
    from job_radar.reclassify import read_payloads, record_from_payload

    payloads = read_payloads(output_dir)
    if not payloads:
        return {"total": 0, LINK_LIVE: 0, LINK_DEAD: 0, LINK_UNKNOWN: 0, "checked": 0}

    records: list[VacancyRecord] = []
    positions: list[int] = []
    for position, payload in enumerate(payloads):
        try:
            records.append(record_from_payload(payload))
        except (TypeError, ValueError):
            continue
        positions.append(position)

    updated_records, counts = verify_records(
        records,
        sources,
        limit=limit,
        only_best_fit=only_best_fit,
        fetcher_factory=fetcher_factory,
        now=now,
    )

    final_payloads = list(payloads)
    changed = 0
    for record, position in zip(updated_records, positions):
        if link_status(record.match_labels) is None:
            continue
        final_payloads[position] = _record_payload(record)
        changed += 1
    if changed:
        rewrite_payloads(output_dir, final_payloads)
    return {
        "total": len(payloads),
        "checked": sum(counts.values()),
        **counts,
    }
