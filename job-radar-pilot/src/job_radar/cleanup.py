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

REASON_OFF_TOPIC = "off_topic"
REASON_EXCLUDED = "excluded"
REASON_EXPIRED = "expired"
REASON_STALE = "stale"

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
    if active.excluded and "FIT:EXCLUDE" in labels:
        return REASON_EXCLUDED
    deadline = _parse_datetime(job.get("application_deadline"))
    if active.expired and deadline is not None and deadline < now:
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
    rules: CleanupRules | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Separa as vagas úteis das descartáveis. Retorna (mantidas, contagem)."""

    moment = now or datetime.now(timezone.utc)
    kept: list[dict[str, Any]] = []
    removed: dict[str, int] = {}
    for job in payloads:
        if str(job.get("canonical_url")) in keep_urls:
            kept.append(job)
            continue
        reason = discard_reason(
            job, now=moment, max_age_days=max_age_days, rules=rules
        )
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
    rules: CleanupRules | None = None,
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
        payloads,
        keep_urls=keep_urls,
        now=now,
        max_age_days=max_age_days,
        rules=rules,
    )
    if not dry_run and removed:
        rewrite_payloads(output_dir, kept)
    return {
        "before": len(payloads),
        "after": len(kept),
        "removed": removed,
        "removed_labels": {
            reason: REASON_NAMES.get(reason, reason) for reason in removed
        },
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
