"""Reaplica o perfil às vagas já salvas, sem consultar os portais de novo.

Mudou as palavras-chave, a empresa a evitar ou o tipo de contrato? A coleta
anterior já tem tudo o que o classificador precisa (título, descrição, local…),
então dá para recalcular a aderência na hora. Nada é apagado: só os rótulos de
aderência mudam (a limpeza continua sendo uma ação separada).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import fields
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from job_radar.classifier import (
    PREFERENCE_BLOCK_PREFIXES,
    SOURCE_ONLY_TECHNOLOGIES,
    _canonical_term,
    classify,
)
from job_radar.fit import fit_state
from job_radar.models import CollectionStatus, SearchProfile, VacancyRecord, WorkplaceModel

# Rótulos que o classificador recalcula; os demais (STATUS:NEW, ALSO_SEEN_IN:,
# IMPORT:, EXTRACTION:, ENRICHED:, WORKPLACE_INFERRED:) são preservados.
_CLASSIFIER_PREFIXES = (
    "PRIMARY_TECH_MISSING:",
    "ELIGIBILITY_UNCLEAR:",
    "TECH_MATCH:",
    "SENIORITY_",
    "LOCATION_",
    "WORKPLACE_MATCH:",
    "WORKPLACE_MISMATCH:",
    "WORKPLACE_UNCLEAR:",
    "SOURCE_TYPE:",
    "RELEVANCE:",
    "FIT:",
    "FIT_SCORE:",
    "COMPANY_",
    "KEYWORD_",
    "BONUS_MATCH:",
    "CONTRACT:",
    "CONTRACT_MISMATCH:",
    "LANGUAGE:",
    "LANGUAGE_MISMATCH:",
    "TITLE_EXCLUDED:",
    "OTHER_STACK:",
    "TECHNOLOGIES:",
)
_TUPLE_FIELDS = {
    "technologies",
    "requirements",
    "eligibility_notes",
    "evidence_snippets",
    "match_labels",
}
_RECORD_FIELDS = {field.name for field in fields(VacancyRecord)}


def record_from_payload(payload: Mapping[str, Any]) -> VacancyRecord:
    values: dict[str, Any] = {}
    for name in _RECORD_FIELDS:
        if name not in payload:
            continue
        value = payload[name]
        if name in _TUPLE_FIELDS:
            value = tuple(value or ())
        elif name == "workplace_model":
            value = WorkplaceModel(value or "UNKNOWN")
        elif name == "collection_status":
            value = CollectionStatus(value or "SUCCESS")
        values[name] = value
    values.setdefault("source_job_id", None)
    values.setdefault("title", None)
    values.setdefault("company", None)
    return VacancyRecord(**values)


def _fit(labels: Iterable[str]) -> str:
    return fit_state(list(labels))


def reclassify_payloads(
    payloads: Iterable[Mapping[str, Any]],
    profile: SearchProfile,
    default_countries: Mapping[str, str | None] | None = None,
) -> list[dict[str, Any]]:
    from job_radar.output import _record_payload

    countries = default_countries or {}
    updated: list[dict[str, Any]] = []
    for payload in payloads:
        try:
            record = record_from_payload(_without_legacy_guesses(payload))
        except (TypeError, ValueError):
            updated.append(dict(payload))
            continue
        kept = tuple(
            label for label in record.match_labels if not label.startswith(_CLASSIFIER_PREFIXES)
        )
        classified = classify(
            record,
            profile,
            default_country=countries.get(record.source),
        )
        labels = tuple(sorted(set(classified.match_labels) | set(kept)))
        new_payload = _record_payload(
            VacancyRecord(**{**_as_kwargs(classified), "match_labels": labels})
        )
        updated.append(new_payload)
    return updated


def _without_legacy_guesses(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Vaga gravada pela versão antiga: tira de `technologies` os palpites anexados.

    O classificador antigo acrescentava ao FIM de `technologies` os termos dos
    seus TECH_MATCH (em ordem alfabética). Sem a marca SOURCE_ONLY, a sequência
    final de itens iguais a esses termos é palpite, não dado do portal.
    """

    labels = [str(label) for label in payload.get("match_labels") or ()]
    if SOURCE_ONLY_TECHNOLOGIES in labels:
        return payload
    guesses = {label.removeprefix("TECH_MATCH:") for label in labels if label.startswith("TECH_MATCH:")}
    technologies = list(payload.get("technologies") or ())
    while technologies and technologies[-1] in guesses:
        technologies.pop()
    return {**payload, "technologies": technologies}


def _as_kwargs(record: VacancyRecord) -> dict[str, Any]:
    return {name: getattr(record, name) for name in _RECORD_FIELDS}


def summarize(
    payloads: Iterable[Mapping[str, Any]],
    previous: Iterable[Mapping[str, Any]] = (),
) -> dict[str, int]:
    payloads = list(payloads)
    before = {
        item.get("canonical_url"): _fit(item.get("match_labels") or ()) for item in previous
    }
    counts = Counter()
    for payload in payloads:
        labels = payload.get("match_labels") or ()
        if "RELEVANCE:OFF_TOPIC" in labels:
            counts["off_topic"] += 1
            continue
        fit = _fit(labels)
        counts[fit.casefold()] += 1
        if any(label.startswith(PREFERENCE_BLOCK_PREFIXES) for label in labels):
            counts["by_preferences"] += 1
        if any(label.startswith(("BONUS_MATCH:", "COMPANY_FAVORITE:")) for label in labels):
            counts["boosted"] += 1
        old = before.get(payload.get("canonical_url"))
        if old is not None and old != fit:
            counts["changed"] += 1
    return {
        "total": len(payloads),
        "ready": counts["ready"],
        "conditional": counts["conditional"],
        "ambiguous": counts["ambiguous"],
        "other_stack": counts["other_stack"],
        "exclude": counts["exclude"],
        "off_topic": counts["off_topic"],
        "by_preferences": counts["by_preferences"],
        "boosted": counts["boosted"],
        "changed": counts["changed"],
    }


def read_payloads(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / "vagas.jsonl"
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return []
    payloads: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def reclassify_output(
    output_dir: Path,
    profile: SearchProfile,
    default_countries: Mapping[str, str | None] | None = None,
    *,
    dry_run: bool = False,
    rules: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Reaplica o perfil às vagas salvas e às que a coleta descartou.

    Descartadas que passam nas regras de limpeza (``rules``) com o perfil novo
    voltam para a lista (``recovered``); as demais continuam no cesto.
    """

    from job_radar.cleanup import (
        CleanupRules,
        discard_reason,
        job_identity,
        read_discarded,
        read_jobs_for_rewrite,
        write_discarded,
    )
    from job_radar.output import rewrite_payloads

    jobs_path = output_dir / "vagas.jsonl"
    previous = read_jobs_for_rewrite(jobs_path) if jobs_path.exists() else []
    updated = reclassify_payloads(previous, profile, default_countries)
    present = {job_identity(payload) for payload in updated}
    active_rules = rules or CleanupRules()
    moment = now or datetime.now(timezone.utc)
    discarded = read_discarded(output_dir)
    recovered: list[dict[str, Any]] = []
    still_discarded: list[dict[str, Any]] = []
    for payload in reclassify_payloads(discarded, profile, default_countries):
        if job_identity(payload) in present:
            continue
        if discard_reason(payload, now=moment, rules=active_rules) is None:
            recovered.append(payload)
        else:
            still_discarded.append(payload)
    final = updated + recovered
    if not dry_run:
        if final:
            rewrite_payloads(output_dir, final)
        if discarded:
            write_discarded(output_dir, still_discarded)
    return {**summarize(final, previous), "recovered": len(recovered), "dry_run": dry_run}


def insights(
    payloads: Iterable[Mapping[str, Any]],
    profile: SearchProfile,
    *,
    limit: int = 20,
) -> dict[str, list[dict[str, Any]]]:
    """Tecnologias e empresas que mais aparecem nas vagas de TI já salvas.

    As tecnologias já presentes no perfil ficam de fora: a ideia é sugerir o que
    falta (para Tecnologias ou Diferenciais).
    """

    known = {_canonical_term(term) for term in profile.positive_keywords}
    known |= {_canonical_term(term) for term in profile.bonus_keywords}
    technologies: Counter[str] = Counter()
    companies: Counter[str] = Counter()
    for payload in payloads:
        labels = payload.get("match_labels") or ()
        if "RELEVANCE:OFF_TOPIC" in labels:
            continue
        seen: set[str] = set()
        for technology in payload.get("technologies") or ():
            canonical = _canonical_term(str(technology))
            if 1 < len(canonical) <= 40 and canonical not in known and canonical not in seen:
                seen.add(canonical)
                technologies[canonical] += 1
        company = " ".join(str(payload.get("company") or "").split())
        if company and _fit(labels) in {"READY", "CONDITIONAL"}:
            companies[company] += 1
    return {
        "technologies": [
            {"term": term, "count": count}
            for term, count in technologies.most_common(limit)
            if count >= 2
        ],
        "companies": [
            {"name": name, "count": count} for name, count in companies.most_common(limit)
        ],
    }
