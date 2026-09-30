"""Descarte de vagas inúteis: fora da área, fora do perfil, vencidas ou velhas.

A mesma regra vale na coleta (as inúteis nem entram no arquivo) e no botão
"Limpar" do painel (que limpa o que já foi salvo). Vagas que a pessoa marcou como
salva/aplicada/descartada nunca são apagadas.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any, Collection, Iterable
from uuid import uuid4

REASON_OFF_TOPIC = "off_topic"
REASON_EXCLUDED = "excluded"
REASON_EXPIRED = "expired"
REASON_STALE = "stale"

REASON_NAMES = {
    REASON_OFF_TOPIC: "fora da área de tecnologia",
    REASON_EXCLUDED: "fora do seu perfil (nível, local ou modelo)",
    REASON_EXPIRED: "inscrições encerradas",
    REASON_STALE: "publicadas há muito tempo",
}


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def discard_reason(
    job: dict[str, Any],
    *,
    now: datetime,
    max_age_days: int | None = None,
) -> str | None:
    """Motivo para descartar a vaga, ou ``None`` se ela deve ficar."""

    labels = job.get("match_labels") or []
    if "RELEVANCE:OFF_TOPIC" in labels:
        return REASON_OFF_TOPIC
    if "FIT:EXCLUDE" in labels:
        return REASON_EXCLUDED
    deadline = _parse_datetime(job.get("application_deadline"))
    if deadline is not None and deadline < now:
        return REASON_EXPIRED
    if max_age_days is not None:
        published = _parse_datetime(job.get("published_at"))
        if published is not None and published < now - timedelta(days=max_age_days):
            return REASON_STALE
    return None


def prune_payloads(
    payloads: Iterable[dict[str, Any]],
    *,
    keep_urls: Collection[str] = (),
    now: datetime | None = None,
    max_age_days: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Separa as vagas úteis das descartáveis. Retorna (mantidas, contagem)."""

    moment = now or datetime.now(timezone.utc)
    kept: list[dict[str, Any]] = []
    removed: dict[str, int] = {}
    for job in payloads:
        if str(job.get("canonical_url")) in keep_urls:
            kept.append(job)
            continue
        reason = discard_reason(job, now=moment, max_age_days=max_age_days)
        if reason is None:
            kept.append(job)
        else:
            removed[reason] = removed.get(reason, 0) + 1
    return kept, removed


def describe_removed(removed: dict[str, int]) -> str:
    if not removed:
        return "Nada para limpar."
    parts = [f"{count} {REASON_NAMES.get(reason, reason)}" for reason, count in removed.items()]
    return "Removidas: " + "; ".join(parts) + "."


def clean_output(
    output_dir: Path,
    *,
    keep_urls: Collection[str] = (),
    max_age_days: int | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Limpa ``vagas.jsonl``/``vagas.csv`` já salvos (sem nova coleta)."""

    from job_radar.output import rewrite_payloads

    jobs_path = output_dir / "vagas.jsonl"
    if not jobs_path.exists():
        return {"before": 0, "after": 0, "removed": {}, "dry_run": dry_run}
    payloads = [
        json.loads(line)
        for line in jobs_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    kept, removed = prune_payloads(
        payloads, keep_urls=keep_urls, now=now, max_age_days=max_age_days
    )
    if not dry_run and removed:
        rewrite_payloads(output_dir, kept)
    return {
        "before": len(payloads),
        "after": len(kept),
        "removed": removed,
        "dry_run": dry_run,
        "summary": describe_removed(removed),
    }


def _temp_name(directory: Path, name: str) -> Path:
    return directory / f".{name}.{uuid4().hex}.tmp"


def replace_atomically(target: Path, content: str) -> None:
    temporary = _temp_name(target.parent, target.name)
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
