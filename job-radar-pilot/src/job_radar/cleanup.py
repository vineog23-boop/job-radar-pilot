"""Descarte de vagas inúteis: fora da área, fora do perfil, vencidas ou velhas.

A mesma regra vale na coleta (as inúteis nem entram no arquivo) e no botão
"Limpar" do painel (que limpa o que já foi salvo). Vagas que a pessoa marcou como
salva/aplicada/descartada nunca são apagadas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any, Collection, Iterable, Mapping
from uuid import uuid4

from job_radar.dates import parse_iso_datetime
from job_radar.fit import fit_state

REASON_OFF_TOPIC = "off_topic"
REASON_EXCLUDED = "excluded"
REASON_EXPIRED = "expired"
REASON_STALE = "stale"
REASON_USER_DISCARDED = "user_discarded"
BACKUP_NAME = "vagas.antes-da-limpeza.jsonl"
# Vagas que a coleta descartou (fora do perfil/da área, vencidas): ficam aqui
# para voltar à lista se o perfil ficar mais amplo (ver reclassify_output).
DISCARDED_NAME = "vagas-descartadas-na-coleta.jsonl"
MAX_DISCARDED = 20_000
MAX_SAMPLES = 25


class CleanupError(ValueError):
    """Regras de limpeza fora do contrato aceito."""


@dataclass(frozen=True, slots=True)
class CleanupRules:
    """O que descartar. Padrão: tudo que é claramente inútil, sem limite de idade."""

    off_topic: bool = True
    excluded: bool = True
    expired: bool = True
    max_age_days: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "off_topic": self.off_topic,
            "excluded": self.excluded,
            "expired": self.expired,
            "max_age_days": self.max_age_days,
        }


_RULE_KEYS = {"off_topic", "excluded", "expired", "max_age_days"}


def rules_from_dict(payload: Mapping[str, Any]) -> CleanupRules:
    if not isinstance(payload, Mapping):
        raise CleanupError("Regras de limpeza devem ser um objeto JSON.")
    unknown = set(payload) - _RULE_KEYS
    if unknown:
        raise CleanupError(f"Regras desconhecidas: {sorted(unknown)}.")
    values: dict[str, Any] = {}
    for key in ("off_topic", "excluded", "expired"):
        if key in payload:
            if not isinstance(payload[key], bool):
                raise CleanupError(f"{key} deve ser verdadeiro ou falso.")
            values[key] = payload[key]
    age = payload.get("max_age_days")
    if age is not None:
        if isinstance(age, bool) or not isinstance(age, int) or not 1 <= age <= 3650:
            raise CleanupError("max_age_days deve ser um inteiro de 1 a 3650.")
        values["max_age_days"] = age
    return CleanupRules(**values)


def rules_path(preferences_path: Path) -> Path:
    return preferences_path.parent / "cleanup-rules.json"


def load_rules(preferences_path: Path) -> CleanupRules:
    """Regras salvas; arquivo ausente ou inválido volta ao padrão seguro."""

    try:
        return rules_from_dict(
            json.loads(rules_path(preferences_path).read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError, CleanupError):
        return CleanupRules()


def save_rules(preferences_path: Path, rules: CleanupRules) -> None:
    path = rules_path(preferences_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    replace_atomically(path, json.dumps(rules.to_dict(), indent=2) + "\n")


REASON_NAMES = {
    REASON_OFF_TOPIC: "fora da área de tecnologia",
    REASON_EXCLUDED: "fora do seu perfil (nível, local ou modelo)",
    REASON_EXPIRED: "inscrições encerradas",
    REASON_STALE: "publicadas há muito tempo",
    REASON_USER_DISCARDED: "marcadas por você como descartadas",
}


def discard_reason(
    job: dict[str, Any],
    *,
    now: datetime,
    max_age_days: int | None = None,
    rules: CleanupRules | None = None,
) -> str | None:
    """Motivo para descartar a vaga, ou ``None`` se ela deve ficar."""

    active = rules or CleanupRules()
    if max_age_days is not None:
        active = CleanupRules(
            active.off_topic, active.excluded, active.expired, max_age_days
        )
    max_age_days = active.max_age_days
    labels = job.get("match_labels") or []
    if active.off_topic and "RELEVANCE:OFF_TOPIC" in labels:
        return REASON_OFF_TOPIC
    if active.excluded and fit_state(labels) == "EXCLUDE":
        return REASON_EXCLUDED
    deadline = parse_iso_datetime(job.get("application_deadline"))
    if active.expired and deadline is not None and deadline < now:
        return REASON_EXPIRED
    if max_age_days is not None:
        published = parse_iso_datetime(job.get("published_at"))
        if published is not None and published < now - timedelta(days=max_age_days):
            return REASON_STALE
    return None


def prune_payloads(
    payloads: Iterable[dict[str, Any]],
    *,
    keep_urls: Collection[str] = (),
    now: datetime | None = None,
    max_age_days: int | None = None,
    rules: CleanupRules | None = None,
    remove_urls: Collection[str] = (),
    samples: list[dict[str, Any]] | None = None,
    removed_jobs: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Separa as vagas úteis das descartáveis. Retorna (mantidas, contagem).

    ``remove_urls`` força a remoção (vagas que a pessoa marcou como descartadas);
    ``samples`` recebe até ``MAX_SAMPLES`` vagas removidas com o motivo;
    ``removed_jobs`` recebe as vagas removidas inteiras.
    """

    moment = now or datetime.now(timezone.utc)
    kept: list[dict[str, Any]] = []
    removed: dict[str, int] = {}
    for job in payloads:
        url = str(job.get("canonical_url"))
        if url in remove_urls:
            reason: str | None = REASON_USER_DISCARDED
        elif url in keep_urls:
            kept.append(job)
            continue
        else:
            reason = discard_reason(
                job, now=moment, max_age_days=max_age_days, rules=rules
            )
        if reason is None:
            kept.append(job)
            continue
        removed[reason] = removed.get(reason, 0) + 1
        if removed_jobs is not None:
            removed_jobs.append(job)
        if samples is not None and len(samples) < MAX_SAMPLES:
            samples.append(
                {
                    "title": job.get("title") or "Cargo não informado",
                    "company": job.get("company") or "",
                    "source": job.get("source") or "",
                    "reason": REASON_NAMES.get(reason, reason),
                }
            )
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
    rules: CleanupRules | None = None,
    remove_urls: Collection[str] = (),
) -> dict[str, Any]:
    """Limpa ``vagas.jsonl``/``vagas.csv`` já salvos (sem nova coleta).

    Antes de gravar, guarda uma cópia (``BACKUP_NAME``) para ``undo_cleanup``.
    """

    from job_radar.output import rewrite_payloads

    jobs_path = output_dir / "vagas.jsonl"
    if not jobs_path.exists():
        return {"before": 0, "after": 0, "removed": {}, "dry_run": dry_run, "samples": []}
    payloads = _read_payloads(jobs_path)
    samples: list[dict[str, Any]] = []
    kept, removed = prune_payloads(
        payloads,
        keep_urls=keep_urls,
        now=now,
        max_age_days=max_age_days,
        rules=rules,
        remove_urls=remove_urls,
        samples=samples,
    )
    if not dry_run and removed:
        kept_ids = {id(job) for job in kept}
        removed_jobs = [job for job in payloads if id(job) not in kept_ids]
        _write_backup(output_dir, removed_jobs)
        rewrite_payloads(output_dir, kept)
    return {
        "before": len(payloads),
        "after": len(kept),
        "removed": removed,
        "samples": samples,
        "backup": backup_info(output_dir),
        "removed_labels": {
            reason: REASON_NAMES.get(reason, reason) for reason in removed
        },
        "dry_run": dry_run,
        "summary": describe_removed(removed),
    }


def _read_payloads(path: Path) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            payloads.append(item)
    return payloads


def read_discarded(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / DISCARDED_NAME
    try:
        return _read_payloads(path)
    except OSError:
        return []


def write_discarded(output_dir: Path, payloads: list[dict[str, Any]]) -> None:
    """Grava o cesto de descartadas (sem duplicar URL, no máximo MAX_DISCARDED)."""

    unique: dict[str, dict[str, Any]] = {}
    for job in payloads:
        unique.setdefault(str(job.get("canonical_url")), job)
    kept = list(unique.values())[-MAX_DISCARDED:]
    content = "".join(
        json.dumps(job, ensure_ascii=False, sort_keys=True) + "\n" for job in kept
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    replace_atomically(output_dir / DISCARDED_NAME, content)


def _write_backup(output_dir: Path, removed_jobs: list[dict[str, Any]]) -> None:
    """Guarda só as vagas removidas (a limpeza seguinte sobrescreve a cópia)."""

    content = "".join(
        json.dumps(job, ensure_ascii=False, sort_keys=True) + "\n" for job in removed_jobs
    )
    replace_atomically(output_dir / BACKUP_NAME, content)


def backup_info(output_dir: Path) -> dict[str, Any] | None:
    path = output_dir / BACKUP_NAME
    try:
        jobs = len(_read_payloads(path))
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None
    return {"jobs": jobs, "at": modified.isoformat()}


def undo_cleanup(output_dir: Path) -> dict[str, Any]:
    """Devolve à lista as vagas removidas na última limpeza (sem duplicar)."""

    from job_radar.output import rewrite_payloads

    backup_path = output_dir / BACKUP_NAME
    if not backup_path.exists():
        raise CleanupError("Não há limpeza para desfazer.")
    current_path = output_dir / "vagas.jsonl"
    current = _read_payloads(current_path) if current_path.exists() else []
    present = {str(job.get("canonical_url")) for job in current}
    restored = [
        job
        for job in _read_payloads(backup_path)
        if str(job.get("canonical_url")) not in present
    ]
    if restored:
        output_dir.mkdir(parents=True, exist_ok=True)
        rewrite_payloads(output_dir, current + restored)
    backup_path.unlink(missing_ok=True)
    return {"restored": len(restored), "total": len(current) + len(restored)}


def _temp_name(directory: Path, name: str) -> Path:
    return directory / f".{name}.{uuid4().hex}.tmp"


def replace_atomically(target: Path, content: str) -> None:
    temporary = _temp_name(target.parent, target.name)
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
