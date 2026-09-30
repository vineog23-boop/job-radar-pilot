from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping


class SourceKind(StrEnum):
    GENERIC = "generic"
    GUPY = "gupy"
    INDEED = "indeed"
    DYNAMIC = "dynamic"


class CollectionStatus(StrEnum):
    SUCCESS = "SUCCESS"
    EMPTY = "EMPTY"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    ERROR = "ERROR"


class WorkplaceModel(StrEnum):
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"
    ONSITE = "ONSITE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class BrowserOptions:
    disable_resources: bool = False
    blocked_domains: tuple[str, ...] = ()
    scroll_to_load: bool = False


@dataclass(frozen=True, slots=True)
class SearchProfile:
    positive_keywords: tuple[str, ...]
    seniority_levels: tuple[str, ...]
    location_scopes: tuple[str, ...]
    excluded_terms: tuple[str, ...] = ()
    search_terms: tuple[str, ...] = ()
    workplace_models: tuple[WorkplaceModel, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceConfig:
    code: str
    kind: SourceKind
    start_url: str
    enabled: bool
    max_pages: int
    min_interval_seconds: float
    requires_auth: bool
    selectors: Mapping[str, str] = field(default_factory=dict)
    queries: tuple[str, ...] = ()
    default_country: str | None = None
    adaptive: bool = True
    single_page: bool = False
    query_path: str | None = None
    query_param: str | None = None
    browser: BrowserOptions = field(default_factory=BrowserOptions)
    # True: os termos da fonte não são trocados pelos do perfil (ex.: lista de
    # empresas monitoradas ou termos amplos que o classificador filtra depois).
    fixed_queries: bool = False
    # True: portal focado em tecnologia; entra na "busca rápida" do painel.
    tech_focus: bool = False


@dataclass(frozen=True, slots=True)
class VacancyRecord:
    source: str
    source_job_id: str | None
    canonical_url: str
    title: str | None
    company: str | None
    description_summary: str | None = None
    seniority: str | None = None
    employment_type: str | None = None
    technologies: tuple[str, ...] = ()
    location: str | None = None
    workplace_model: WorkplaceModel = WorkplaceModel.UNKNOWN
    remote_scope: str | None = None
    published_at: str | None = None
    observed_at: str | None = None
    application_deadline: str | None = None
    requirements: tuple[str, ...] = ()
    eligibility_notes: tuple[str, ...] = ()
    evidence_snippets: tuple[str, ...] = ()
    match_labels: tuple[str, ...] = ()
    collection_status: CollectionStatus = CollectionStatus.SUCCESS
    content_hash: str | None = None
    identity_strength: str = "STRONG"


@dataclass(frozen=True, slots=True)
class SourceRunResult:
    source_code: str
    status: CollectionStatus
    records: tuple[VacancyRecord, ...] = ()
    pages_observed: int = 0
    cards_observed: int = 0
    has_more: bool = False
    stop_reason: str | None = None
    errors: tuple[str, ...] = ()
    visited_urls: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RunReport:
    started_at: str
    finished_at: str
    source_results: tuple[SourceRunResult, ...]
    upstream_commit: str | None = None
