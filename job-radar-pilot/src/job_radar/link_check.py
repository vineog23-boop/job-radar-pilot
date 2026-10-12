"""Verificação real de disponibilidade: refaz o fetch do link no momento da checagem.

``activity.py`` infere a situação pelas datas e evidências salvas (sem acessar a
rede de novo); uma listagem recente não prova que a vaga ainda está no ar — um agregador pode
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

from job_radar.fetching import (
    FetchPolicy,
    _detect_block_signal,
    _visible_response_text,
    page_html,
)
from urllib.parse import urlsplit
import json
import re
import unicodedata
from job_radar.dates import parse_deadline
from job_radar.fit import fit_state, is_off_topic
from job_radar.models import CollectionStatus, SourceConfig, SourceKind, VacancyRecord

LINK_LIVE = "LINK:LIVE"
LINK_DEAD = "LINK:DEAD"
LINK_UNKNOWN = "LINK:UNKNOWN"
_LINK_PREFIX = "LINK:"
_CHECKED_AT_PREFIX = "LINK_CHECKED_AT:"
_METHOD_PREFIX = "LINK_CHECK_METHOD:"
LINK_METHOD = "LINK_CHECK_METHOD:JOB_DETAIL_V2"
VerificationProgress = Callable[[int, int, dict[str, int]], None]

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

DEFAULT_VERIFY_LIMIT = 80
_SKIP_SOURCES = {"indeed", "linkedin"}


def _fold(text: str) -> str:
    return " ".join(
        "".join(
            char
            for char in unicodedata.normalize("NFKD", text.casefold())
            if not unicodedata.combining(char)
        ).split()
    )


def _identity_matches(text: str, expected_title: str | None) -> bool:
    return not expected_title or _fold(expected_title) in _fold(text)


def _blocked_text(text: str) -> bool:
    folded = _fold(text)
    return any(
        marker in folded
        for marker in (
            "captcha",
            "confirme que voce e humano",
            "verify you are human",
            "faca login",
            "login para",
            "sign in to",
            "log in to",
            "acesso restrito",
        )
    )


def classify_page_text(text: str | None, expected_title: str | None = None) -> str:
    """Confirma apenas página de vaga com detalhes, candidatura e identidade."""
    if not text:
        return LINK_UNKNOWN
    folded = _fold(text)
    if _blocked_text(text):
        return LINK_UNKNOWN
    if any(_fold(marker) in folded for marker in _DEAD_MARKERS):
        return LINK_DEAD
    specific = any(
        marker in folded for marker in ("vaga", "job", "position", "oportunidade")
    )
    details = any(
        marker in folded
        for marker in (
            "requisitos",
            "responsabilidades",
            "requirements",
            "responsibilities",
            "qualificacoes",
        )
    )
    apply = any(
        marker in folded
        for marker in (
            "candidate-se",
            "candidatar",
            "candidatura",
            "apply now",
            "apply for",
            "inscreva-se",
        )
    )
    if specific and details and apply and _identity_matches(text, expected_title):
        return LINK_LIVE
    return LINK_UNKNOWN


def _job_posting_live(html: str, expected_title: str | None) -> bool:
    def contains_job(value: Any) -> bool:
        if isinstance(value, list):
            return any(contains_job(item) for item in value)
        if not isinstance(value, dict):
            return False
        kind = value.get("@type")
        if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
            return bool(
                value.get("title") and value.get("description")
            ) and _identity_matches(str(value["title"]), expected_title)
        return contains_job(value.get("@graph"))

    for body in re.findall(
        r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        html,
        re.I | re.S,
    ):
        try:
            if contains_job(json.loads(body)):
                return True
        except (ValueError, TypeError):
            continue
    return False


_NEXT_DATA = re.compile(
    r"<script[^>]+id=[\"']__NEXT_DATA__[\"'][^>]*>(.*?)</script>", re.I | re.S
)


def _gupy_job_status(html: str, expected_title: str | None) -> str | None:
    """Status estruturado da Gupy (``pageProps.job``): ``status`` e ``expiresAt``.

    A página é montada por JavaScript e o script traz textos de interface
    ("Candidaturas encerradas") em toda vaga, então o texto não serve de prova.
    """

    match = _NEXT_DATA.search(html)
    if not match:
        return None
    try:
        job = json.loads(match.group(1))["props"]["pageProps"]["job"]
    except (ValueError, TypeError, KeyError):
        return None
    if not isinstance(job, dict) or "status" not in job:
        return None
    if not _identity_matches(str(job.get("name") or job.get("title") or ""), expected_title):
        return None
    if job.get("status") != "published":
        return LINK_DEAD
    expires = parse_deadline(job.get("expiresAt"))
    if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        return LINK_DEAD
    return LINK_LIVE


def check_canonical_url(
    url: str,
    source: SourceConfig,
    fetcher: FetchPolicy,
    expected_title: str | None = None,
) -> str:
    """Busca ``url`` agora (sem navegador pesado) e classifica o resultado."""

    if not source.fetch_details:
        return LINK_UNKNOWN
    static_source = replace(source, kind=SourceKind.GENERIC, adaptive=False)
    try:
        fetched = fetcher.fetch(url, static_source)
    except Exception:
        return LINK_UNKNOWN
    if fetched.status is CollectionStatus.BLOCKED:
        return LINK_UNKNOWN
    if fetched.status is not CollectionStatus.SUCCESS or fetched.response is None:
        return LINK_UNKNOWN
    response = fetched.response
    if _detect_block_signal(response)[0] is not None:
        return LINK_UNKNOWN
    if getattr(response, "status", None) in {404, 410}:
        return LINK_DEAD
    if getattr(response, "status", None) != 200:
        return LINK_UNKNOWN
    final_url = str(getattr(response, "url", url))
    original, final = urlsplit(url), urlsplit(final_url)
    home_paths = {
        "",
        "home",
        "index",
        "index.html",
        "index.php",
        "careers",
        "carreiras",
        "jobs",
        "vagas",
    }
    final_segments = [
        segment.casefold() for segment in final.path.split("/") if segment
    ]
    listing_destination = (
        not final_segments
        or final_segments[-1] in home_paths
        or bool({"search", "busca"} & set(final_segments))
    )
    if original.path.rstrip("/") != final.path.rstrip("/") and listing_destination:
        return LINK_UNKNOWN
    text = _visible_response_text(response)
    status = classify_page_text(text, expected_title)
    # Bloqueios e remoções visíveis prevalecem sobre metadados antigos.
    if status != LINK_UNKNOWN:
        return status
    if _blocked_text(text):
        return LINK_UNKNOWN
    structured = _gupy_job_status(page_html(response), expected_title)
    if structured is not None:
        return structured
    return (
        LINK_LIVE
        if _job_posting_live(page_html(response), expected_title)
        else LINK_UNKNOWN
    )


def _is_best_fit(record: VacancyRecord) -> bool:
    return fit_state(record.match_labels) in {"READY", "CONDITIONAL"}


def _without_link_labels(labels: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        label
        for label in labels
        if not label.startswith(_LINK_PREFIX)
        and not label.startswith(_CHECKED_AT_PREFIX)
        and not label.startswith(_METHOD_PREFIX)
    )


def verify_records(
    records: Sequence[VacancyRecord],
    sources: Sequence[SourceConfig],
    *,
    limit: int | None = DEFAULT_VERIFY_LIMIT,
    only_best_fit: bool = True,
    fetcher_factory: Callable[[], FetchPolicy] = FetchPolicy,
    now: datetime | None = None,
    on_progress: VerificationProgress | None = None,
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
        if only_best_fit and (
            not _is_best_fit(record) or is_off_topic(record.match_labels)
        ):
            continue
        if not (record.canonical_url or "").startswith("https://"):
            continue
        candidates.append(index)
    from job_radar.output import _record_payload
    from job_radar.xlsx_export import job_score

    candidates.sort(
        key=lambda index: -job_score(_record_payload(records[index]), moment)
    )
    picked = candidates if not limit or limit <= 0 else candidates[:limit]

    updated = list(records)
    counts = {LINK_LIVE: 0, LINK_DEAD: 0, LINK_UNKNOWN: 0}
    if on_progress:
        on_progress(0, len(picked), dict(counts))
    with fetcher_factory() as fetcher:
        for index in picked:
            record = records[index]
            source = by_code.get(record.source)
            if (
                source is None
                or not source.enabled
                or source.requires_auth
                or not source.fetch_details
                or record.source in _SKIP_SOURCES
            ):
                status = LINK_UNKNOWN
            else:
                status = check_canonical_url(
                    record.canonical_url, source, fetcher, expected_title=record.title
                )
            counts[status] += 1
            labels = (
                *_without_link_labels(record.match_labels),
                status,
                f"{_CHECKED_AT_PREFIX}{checked_at}",
                LINK_METHOD,
            )
            updated[index] = replace(record, match_labels=labels)
            if on_progress:
                on_progress(sum(counts.values()), len(picked), dict(counts))
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
    on_progress: VerificationProgress | None = None,
) -> dict[str, Any]:
    """Relê ``vagas.jsonl``, reconfirma os links candidatos e regrava o arquivo.

    Só os rótulos ``LINK:*``/``LINK_CHECKED_AT:`` mudam; nada é descartado e
    nenhum outro campo é tocado (mesmo padrão de ``reclassify_output``).
    O chamador deve segurar OutputLock; a CLI e o painel já fazem isso.
    """

    from job_radar.output import _record_payload, rewrite_payloads
    from job_radar.reclassify import record_from_payload
    from job_radar.cleanup import read_jobs_for_rewrite

    path = output_dir / "vagas.jsonl"
    payloads = read_jobs_for_rewrite(path) if path.exists() else []
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
        on_progress=on_progress,
    )

    final_payloads = list(payloads)
    changed = 0
    for record, position in zip(updated_records, positions):
        if list(record.match_labels) == list(
            payloads[position].get("match_labels", [])
        ):
            continue
        final_payloads[position] = {
            **payloads[position],
            "match_labels": list(record.match_labels),
            "content_hash": _record_payload(record)["content_hash"],
        }
        changed += 1
    if changed:
        rewrite_payloads(output_dir, final_payloads)
    return {
        "total": len(payloads),
        "checked": sum(counts.values()),
        **counts,
    }
