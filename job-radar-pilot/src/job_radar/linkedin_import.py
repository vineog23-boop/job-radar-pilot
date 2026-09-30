"""Importador de vagas do LinkedIn a partir do que o próprio usuário cola.

O Radar nunca acessa o LinkedIn: o usuário abre a busca no próprio navegador
(já logado) e traz para cá os links das vagas, o texto de um e-mail de alerta
ou o CSV do export oficial de dados. Aqui só interpretamos esse texto local.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from job_radar.classifier import classify
from job_radar.identity import canonicalize_url
from job_radar.models import SearchProfile, VacancyRecord
from job_radar.output import _previous_payloads, _record_payload, rewrite_payloads

SOURCE_CODE = "linkedin"
MAX_ITEMS = 300
MAX_TEXT_CHARS = 400_000

_URL = re.compile(r"https?://[^\s\"'<>)\]]+", re.IGNORECASE)
_SLUG = re.compile(r"^(?P<slug>.*?)-?(?P<id>\d{6,})$")
_COMPANY_SEPARATORS = ("-at-", "-na-", "-no-", "-em-", "-@-")
_URL_PREFIXES = re.compile(
    r"^(ver vaga|view job|candidate-se|apply now|see job|abrir vaga)\s*[:\-]?\s*$",
    re.IGNORECASE,
)
_CSV_COLUMNS = {
    "url": {"job url", "joburl", "url", "link", "job link", "link da vaga"},
    "title": {"job title", "jobtitle", "title", "cargo", "titulo", "título", "vaga"},
    "company": {"company name", "company", "empresa", "companyname"},
    "date": {"saved date", "application date", "date", "data", "data da candidatura"},
}


@dataclass(frozen=True, slots=True)
class ImportedJob:
    job_id: str
    url: str
    title: str | None = None
    company: str | None = None
    location: str | None = None
    saved_at: str | None = None


def _is_linkedin_host(hostname: str | None) -> bool:
    host = (hostname or "").casefold()
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def _job_id_from_url(url: str) -> tuple[str, str | None] | None:
    """(id, slug) de um link de vaga do LinkedIn, ou None se não for de vaga."""

    parts = urlsplit(url)
    if not _is_linkedin_host(parts.hostname):
        return None
    path = unquote(parts.path).rstrip("/")
    if "/jobs/view/" in path:
        tail = path.split("/jobs/view/", 1)[1].split("/", 1)[0]
        match = _SLUG.match(tail)
        if match:
            return match.group("id"), match.group("slug") or None
        return None
    current = parse_qs(parts.query).get("currentJobId", [""])[0]
    if current.isdigit() and len(current) >= 6:
        return current, None
    return None


def _title_case(words: str) -> str:
    small = {"de", "da", "do", "das", "dos", "e", "em", "para", "of", "and", "the"}
    parts = [word for word in words.split("-") if word]
    return " ".join(
        word if word.casefold() in small and index else word.capitalize()
        for index, word in enumerate(parts)
    )


def _from_slug(slug: str | None) -> tuple[str | None, str | None]:
    if not slug:
        return None, None
    for separator in _COMPANY_SEPARATORS:
        if separator in slug:
            head, _, tail = slug.rpartition(separator)
            if head and tail:
                return _title_case(head), _title_case(tail)
    return _title_case(slug), None


def _job(
    url: str,
    *,
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    saved_at: str | None = None,
) -> ImportedJob | None:
    parsed = _job_id_from_url(url if "://" in url else f"https://{url}")
    if parsed is None:
        return None
    job_id, slug = parsed
    slug_title, slug_company = _from_slug(slug)
    return ImportedJob(
        job_id=job_id,
        url=f"https://www.linkedin.com/jobs/view/{job_id}",
        title=title or slug_title,
        company=company or slug_company,
        location=location,
        saved_at=saved_at,
    )


def _normalize_header(value: str) -> str:
    return " ".join(value.strip().strip("﻿").casefold().split())


def _parse_csv(text: str) -> list[ImportedJob] | None:
    """Lê CSV do export do LinkedIn (Saved Jobs / Job Applications); None se não for CSV."""

    first = next((line for line in text.splitlines() if line.strip()), "")
    if "," not in first and ";" not in first and "\t" not in first:
        return None
    try:
        dialect = csv.Sniffer().sniff(first, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    header: dict[str, int] = {}
    jobs: list[ImportedJob] = []
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        if not header:
            names = [_normalize_header(cell) for cell in row]
            for field, aliases in _CSV_COLUMNS.items():
                for index, name in enumerate(names):
                    if name in aliases:
                        header.setdefault(field, index)
            if "url" not in header:
                return None
            continue

        def cell(field: str, row: list[str] = row) -> str | None:
            index = header.get(field)
            if index is None or index >= len(row):
                return None
            return row[index].strip() or None

        url = cell("url")
        if not url:
            continue
        job = _job(url, title=cell("title"), company=cell("company"), saved_at=cell("date"))
        if job is not None:
            jobs.append(job)
    return jobs if header else None


def _clean_line(line: str) -> str:
    return " ".join(line.replace("·", " · ").split()).strip(" -–—|•*")


def _parse_text(text: str) -> list[ImportedJob]:
    """Extrai links de vaga; usa as linhas anteriores (alerta por e-mail) como título/empresa."""

    jobs: list[ImportedJob] = []
    context: list[str] = []
    for raw_line in text.splitlines():
        matches = list(_URL.finditer(raw_line))
        if not matches:
            line = _clean_line(raw_line)
            if line:
                context.append(line)
            continue
        leftover = _clean_line(_URL.sub(" ", raw_line))
        if leftover and not _URL_PREFIXES.match(leftover):
            context.append(leftover)
        for match in matches:
            usable = [
                line
                for line in context[-2:]
                if len(line) <= 140 and "linkedin" not in line.casefold()
                and not _URL_PREFIXES.match(line)
            ]
            title = company = location = None
            if len(usable) == 2:
                title = usable[0]
                company_line = usable[1]
                pieces = [p.strip() for p in re.split(r"\s+[·•]\s+|\s+-\s+", company_line) if p.strip()]
                company = pieces[0] if pieces else None
                location = ", ".join(pieces[1:]) or None
            job = _job(match.group(0).rstrip(".,;"), title=title, company=company, location=location)
            if job is not None:
                jobs.append(job)
        context = []
    return jobs


def parse_import(text: str) -> tuple[list[ImportedJob], int]:
    """(vagas únicas, links ignorados). Aceita CSV do export, links e texto de alertas."""

    text = text[:MAX_TEXT_CHARS]
    csv_jobs = _parse_csv(text)
    jobs = csv_jobs if csv_jobs is not None else _parse_text(text)
    total_links = len(jobs)
    unique: dict[str, ImportedJob] = {}
    for job in jobs:
        current = unique.get(job.job_id)
        # Mantém a entrada mais informativa quando o mesmo link aparece mais de uma vez.
        if current is None or (job.title and not current.title) or (
            job.company and not current.company
        ):
            unique[job.job_id] = job if current is None else replace(
                current,
                title=job.title or current.title,
                company=job.company or current.company,
                location=job.location or current.location,
            )
    non_job_links = 0
    if csv_jobs is None:
        non_job_links = sum(
            1
            for match in _URL.finditer(text)
            if _is_linkedin_host(urlsplit(match.group(0)).hostname)
            and _job_id_from_url(match.group(0)) is None
        )
    ignored = non_job_links + (total_links - len(unique))
    return list(unique.values())[:MAX_ITEMS], ignored


def _record(job: ImportedJob, profile: SearchProfile, observed_at: str) -> VacancyRecord:
    title = job.title or f"Vaga do LinkedIn {job.job_id}"
    record = VacancyRecord(
        source=SOURCE_CODE,
        source_job_id=job.job_id,
        canonical_url=canonicalize_url(job.url),
        title=title,
        company=job.company,
        location=job.location,
        observed_at=observed_at,
        evidence_snippets=(title,),
    )
    classified = classify(record, profile, default_country="BR")
    labels = tuple(dict.fromkeys((*classified.match_labels, "IMPORT:MANUAL")))
    return replace(classified, match_labels=labels)


def import_into_output(
    output_dir: Path,
    text: str,
    profile: SearchProfile,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Mescla as vagas coladas no ``vagas.jsonl`` atual (sem duplicar links)."""

    jobs, ignored = parse_import(text)
    observed_at = (now or datetime.now(timezone.utc)).isoformat()
    payloads = _previous_payloads(output_dir / "vagas.jsonl", set())
    by_url = {p.get("canonical_url"): index for index, p in enumerate(payloads)}
    added = updated = skipped = 0
    for job in jobs:
        record = _record(job, profile, observed_at)
        payload = _record_payload(record)
        index = by_url.get(payload["canonical_url"])
        if index is None:
            payloads.append(payload)
            by_url[payload["canonical_url"]] = len(payloads) - 1
            added += 1
        elif payloads[index].get("source") == SOURCE_CODE and job.title:
            payloads[index] = payload
            updated += 1
        else:
            skipped += 1
    if added or updated:
        output_dir.mkdir(parents=True, exist_ok=True)
        rewrite_payloads(output_dir, payloads)
    return {
        "found": len(jobs),
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "ignored": ignored,
    }
