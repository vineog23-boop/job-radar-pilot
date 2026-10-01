from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import re
from typing import Collection, Iterable
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from job_radar.dates import parse_iso_datetime
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


# Palavras do cargo que dizem onde/como é a vaga, não qual é a vaga.
_TITLE_NOISE = {
    "remoto", "remota", "remote", "home", "office", "hibrido", "hibrida", "hybrid",
    "presencial", "onsite", "100", "vaga", "brasil", "brazil", "pessoa", "a", "o",
}
_TITLE_SYNONYMS = {
    "desenvolvedora": "desenvolvedor",
    "developer": "desenvolvedor",
    "dev": "desenvolvedor",
    "engenheira": "engenheiro",
    "programadora": "programador",
    "jr": "junior",
    "sr": "senior",
    "pl": "pleno",
    "estagiario": "estagio",
    "estagiaria": "estagio",
}
_TITLE_JOINED = (("back end", "backend"), ("front end", "frontend"), ("full stack", "fullstack"))
# Sufixos de razão social e de país que mudam de portal para portal.
_COMPANY_SUFFIXES = {"ltda", "sa", "s", "a", "me", "eireli", "inc", "brasil", "br", "do", "group"}
_REMOTE_MARKERS = ("remoto", "remota", "remote", "home office", "teletrabalho")


def _title_key(title: str | None) -> str:
    text = f" {_semantic_text(title)} "
    for spaced, joined in _TITLE_JOINED:
        text = text.replace(f" {spaced} ", f" {joined} ")
    words = [_TITLE_SYNONYMS.get(word, word) for word in text.split()]
    return " ".join(word for word in words if word not in _TITLE_NOISE)


def _company_key(company: str | None) -> str:
    words = _semantic_text(company).split()
    while len(words) > 1 and words[-1] in _COMPANY_SUFFIXES:
        words.pop()
    return "".join(words)  # "Baires Dev" e "BairesDev" são a mesma empresa


def _semantic_key(record: VacancyRecord) -> tuple[str, str] | None:
    title = _title_key(record.title)
    company = _company_key(record.company)
    if not title or not company or _semantic_text(record.title) in _GENERIC_TITLES:
        return None
    return title, company


def _is_remote(record: VacancyRecord) -> bool:
    if record.workplace_model.value == "REMOTE":
        return True
    text = _semantic_text(" ".join(part for part in (record.title, record.location) if part))
    return any(marker in text for marker in _REMOTE_MARKERS)


def _locations_compatible(first: VacancyRecord, second: VacancyRecord) -> bool:
    """Mesma vaga se o local bate, se uma é remota ou se uma não diz o local."""

    first_location = _semantic_text(first.location)
    second_location = _semantic_text(second.location)
    if not first_location or not second_location or first_location == second_location:
        return True
    return _is_remote(first) or _is_remote(second)


def _source_priority(record: VacancyRecord) -> int:
    """Menor = mais confiável: ATS/site da empresa antes de agregadores."""
    host = (urlsplit(record.canonical_url).hostname or "").casefold()
    if record.source == "gupy" or host.endswith(".gupy.io"):
        return 0
    return 1


def _published(record: VacancyRecord) -> datetime:
    return parse_iso_datetime(record.published_at) or datetime.min.replace(tzinfo=timezone.utc)


def _choose_keeper(records: list[VacancyRecord], cluster: list[int], preferred: set[str]) -> int:
    """Qual anúncio fica: o que a pessoa acompanha; depois a fonte mais confiável;
    numa republicação (mesmo portal), o mais recente; entre portais, o primeiro visto."""

    tracked = [index for index in cluster if canonicalize_url(records[index].canonical_url) in preferred]
    candidates = tracked or cluster
    best = min(_source_priority(records[index]) for index in candidates)
    candidates = [index for index in candidates if _source_priority(records[index]) == best]
    if len({records[index].source for index in cluster}) == 1:
        return max(candidates, key=lambda index: (_published(records[index]), -index))
    return min(candidates)


def _merge_cross_source_semantic_duplicates(
    records: list[VacancyRecord],
    preferred_urls: Collection[str] = (),
) -> tuple[list[VacancyRecord], int]:
    """Une a mesma vaga vista mais de uma vez (cargo + empresa + local compatível).

    Entre portais diferentes, fica a fonte mais confiável (empate: a primeira
    vista) e as outras viram ``ALSO_SEEN_IN:<fonte>``. No mesmo portal
    (republicação), fica o anúncio mais recente e ``REPOSTED:<n>`` conta os
    outros. Uma URL que a pessoa acompanha (``preferred_urls``) sempre fica.
    """

    preferred = {canonicalize_url(url) for url in preferred_urls}
    groups: dict[tuple[str, str], list[int]] = {}
    for index, record in enumerate(records):
        key = _semantic_key(record)
        if key is not None:
            groups.setdefault(key, []).append(index)

    dropped: set[int] = set()
    replacements: dict[int, VacancyRecord] = {}
    for indexes in groups.values():
        clusters: list[list[int]] = []
        for index in indexes:
            for cluster in clusters:
                if all(_locations_compatible(records[index], records[other]) for other in cluster):
                    cluster.append(index)
                    break
            else:
                clusters.append([index])
        for cluster in clusters:
            if len(cluster) < 2:
                continue
            keeper = _choose_keeper(records, cluster, preferred)
            kept = records[keeper]
            others = [index for index in cluster if index != keeper]
            other_sources = sorted({records[index].source for index in others} - {kept.source})
            reposts = sum(1 for index in others if records[index].source == kept.source)
            extra = [f"ALSO_SEEN_IN:{source}" for source in other_sources]
            if reposts:
                extra.append(f"REPOSTED:{reposts}")
            labels = dict.fromkeys((*kept.match_labels, *extra))
            replacements[keeper] = replace(kept, match_labels=tuple(sorted(labels)))
            dropped.update(others)

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


def deduplicate(
    records: Iterable[VacancyRecord],
    *,
    preferred_urls: Collection[str] = (),
) -> DeduplicationResult:
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

    unique, merged_count = _merge_cross_source_semantic_duplicates(unique, preferred_urls)
    return DeduplicationResult(
        tuple(unique),
        tuple(ambiguous),
        duplicate_count + merged_count,
    )
