from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import re
from typing import Iterable
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from job_radar.models import VacancyRecord


_SENSITIVE_OR_TRACKING_PARAMETERS = {
    "apitoken",
    "auth",
    "authorization",
    "iauid",
    "jobboardsource",
    "session",
    "sessionid",
    "token",
}

_GENERIC_TITLES = {
    "aprendiz",
    "estagio",
    "estagiario",
    "pcd",
    "programa de estagio",
}


@dataclass(frozen=True, slots=True)
class DeduplicationResult:
    unique: tuple[VacancyRecord, ...]
    ambiguous: tuple[VacancyRecord, ...]
    duplicate_count: int


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlsplit(url.strip())
    host = (parsed.hostname or "").casefold()
    if not host:
        return url.strip()
    port = parsed.port
    netloc = host
    if port and not (
        (parsed.scheme.casefold() == "https" and port == 443)
        or (parsed.scheme.casefold() == "http" and port == 80)
    ):
        netloc = f"{host}:{port}"

    kept_parameters = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        normalized_key = key.casefold()
        if normalized_key.startswith("utm_"):
            continue
        if normalized_key in _SENSITIVE_OR_TRACKING_PARAMETERS:
            continue
        kept_parameters.append((key, value))
    kept_parameters.sort(key=lambda item: (item[0].casefold(), item[1]))

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            netloc,
            path,
            urlencode(kept_parameters, doseq=True),
            "",
        )
    )


def identity_key(record: VacancyRecord) -> tuple[str, str]:
    if record.source_job_id and record.source_job_id.strip():
        return "SOURCE_JOB_ID", f"{record.source}:{record.source_job_id.strip()}"
    canonical_url = canonicalize_url(record.canonical_url)
    if canonical_url:
        return "CANONICAL_URL", canonical_url
    fallback_material = "|".join(
        (record.company or "", record.title or "", record.location or "")
    ).casefold()
    return "FALLBACK_HASH", sha256(fallback_material.encode("utf-8")).hexdigest()


def _semantic_text(value: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", (value or "").casefold())
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"[a-z0-9]+", without_accents))


def _semantic_key(record: VacancyRecord) -> tuple[str, str, str] | None:
    title = _semantic_text(record.title)
    company = _semantic_text(record.company)
    location = _semantic_text(record.location)
    if not title or not company or not location or title in _GENERIC_TITLES:
        return None
    return title, company, location


def _source_priority(record: VacancyRecord) -> int:
    """Menor = mais confiável: ATS/site da empresa antes de agregadores."""
    host = (urlsplit(record.canonical_url).hostname or "").casefold()
    if record.source == "gupy" or host.endswith(".gupy.io"):
        return 0
    return 1


def _merge_cross_source_semantic_duplicates(
    records: list[VacancyRecord],
) -> tuple[list[VacancyRecord], int]:
    """Une a mesma vaga vista em portais diferentes (cargo+empresa+local iguais).

    Mantém o registro da fonte mais confiável (empate: o primeiro observado) e
    registra as demais fontes em ALSO_SEEN_IN:<fonte>.
    """
    groups: dict[tuple[str, str, str], list[int]] = {}
    for index, record in enumerate(records):
        key = _semantic_key(record)
        if key is not None:
            groups.setdefault(key, []).append(index)

    dropped: set[int] = set()
    replacements: dict[int, VacancyRecord] = {}
    for indexes in groups.values():
        if len({records[index].source for index in indexes}) < 2:
            continue
        keeper = min(indexes, key=lambda index: (_source_priority(records[index]), index))
        kept = records[keeper]
        other_sources = sorted(
            {records[index].source for index in indexes} - {kept.source}
        )
        merged_indexes = [
            index for index in indexes
            if index != keeper and records[index].source != kept.source
        ]
        labels = dict.fromkeys(
            (
                *kept.match_labels,
                *(f"ALSO_SEEN_IN:{source}" for source in other_sources),
            )
        )
        replacements[keeper] = replace(kept, match_labels=tuple(sorted(labels)))
        dropped.update(merged_indexes)

    merged = [
        replacements.get(index, record)
        for index, record in enumerate(records)
        if index not in dropped
    ]
    return merged, len(dropped)


def _merge_labels(first: VacancyRecord, duplicate: VacancyRecord) -> VacancyRecord:
    labels = tuple(
        dict.fromkeys(
            (
                *first.match_labels,
                *(
                    label
                    for label in duplicate.match_labels
                    if label.startswith("EXTRACTION:")
                ),
            )
        )
    )
    return first if labels == first.match_labels else replace(first, match_labels=labels)


def _replace_retained(
    records: list[VacancyRecord],
    previous: VacancyRecord,
    updated: VacancyRecord,
    seen_primary: dict[tuple[str, str], VacancyRecord],
    seen_url: dict[str, VacancyRecord],
) -> None:
    if updated is previous:
        return
    for index, record in enumerate(records):
        if record is previous:
            records[index] = updated
            break
    for key, record in tuple(seen_primary.items()):
        if record is previous:
            seen_primary[key] = updated
    for key, record in tuple(seen_url.items()):
        if record is previous:
            seen_url[key] = updated


def deduplicate(records: Iterable[VacancyRecord]) -> DeduplicationResult:
    unique: list[VacancyRecord] = []
    ambiguous: list[VacancyRecord] = []
    seen_primary: dict[tuple[str, str], VacancyRecord] = {}
    seen_url: dict[str, VacancyRecord] = {}
    duplicate_count = 0

    for original in records:
        canonical_url = canonicalize_url(original.canonical_url)
        existing_url = seen_url.get(canonical_url) if canonical_url else None
        if (
            existing_url is not None
            and existing_url.source_job_id
            and original.source_job_id
            and existing_url.source_job_id != original.source_job_id
        ):
            if existing_url in unique:
                unique.remove(existing_url)
            if existing_url not in ambiguous:
                ambiguous.append(existing_url)
            ambiguous.append(original)
            continue
        if existing_url is not None:
            _replace_retained(
                unique,
                existing_url,
                _merge_labels(existing_url, original),
                seen_primary,
                seen_url,
            )
            duplicate_count += 1
            continue

        key = identity_key(original)
        if key in seen_primary:
            existing_primary = seen_primary[key]
            _replace_retained(
                unique,
                existing_primary,
                _merge_labels(existing_primary, original),
                seen_primary,
                seen_url,
            )
            duplicate_count += 1
            continue

        record = (
            replace(original, identity_strength="WEAK")
            if key[0] == "FALLBACK_HASH"
            else original
        )
        seen_primary[key] = record
        if canonical_url:
            seen_url[canonical_url] = record
        unique.append(record)

    unique, merged_count = _merge_cross_source_semantic_duplicates(unique)
    return DeduplicationResult(
        tuple(unique),
        tuple(ambiguous),
        duplicate_count + merged_count,
    )
