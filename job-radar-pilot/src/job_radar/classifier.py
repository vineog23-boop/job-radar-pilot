from __future__ import annotations

from dataclasses import replace
import unicodedata

from job_radar.models import SearchProfile, VacancyRecord, WorkplaceModel


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        "".join(character for character in decomposed if not unicodedata.combining(character)).split()
    )


def classify(record: VacancyRecord, profile: SearchProfile) -> VacancyRecord:
    searchable_text = _normalize(
        " ".join(
            part
            for part in (
                record.title,
                record.description_summary,
                record.location,
                " ".join(record.requirements),
                " ".join(record.evidence_snippets),
            )
            if part
        )
    )
    labels: set[str] = set()

    for keyword in profile.positive_keywords:
        normalized = _normalize(keyword)
        if normalized and normalized in searchable_text:
            labels.add(f"TECH_MATCH:{normalized}")

    for seniority in profile.seniority_levels:
        normalized = _normalize(seniority)
        if normalized and normalized in searchable_text:
            labels.add(f"SENIORITY_MATCH:{normalized}")

    for excluded in profile.excluded_terms:
        normalized = _normalize(excluded)
        if normalized and normalized in searchable_text:
            labels.add(f"SENIORITY_MISMATCH:{normalized}")

    normalized_location = _normalize(record.location)
    if record.workplace_model is WorkplaceModel.REMOTE:
        normalized_scope = _normalize(record.remote_scope)
        if "brasil" in normalized_scope or "brazil" in normalized_scope:
            labels.add("LOCATION_MATCH:remote_brazil")
        else:
            labels.add("LOCATION_UNCLEAR:remote_scope")
    elif not normalized_location:
        labels.add("LOCATION_UNCLEAR:missing")
    else:
        for scope in profile.location_scopes:
            normalized_scope = _normalize(scope.replace("-", " "))
            city = normalized_scope.removesuffix(" sp").removesuffix(" sc")
            if city and city != "remoto brasil" and city in normalized_location:
                labels.add(f"LOCATION_MATCH:{scope}")

    return replace(record, match_labels=tuple(sorted(labels)))
