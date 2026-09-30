"""Fontes com API JSON pública do próprio portal (kind: json).

Vários portais alimentam o site por uma API aberta (sem login) que devolve as
vagas já estruturadas: data, empresa, modelo de trabalho, local e descrição
completa. Ler o JSON é mais confiável e rico do que interpretar o HTML, então o
mapeamento dos campos fica no ``sources.yaml`` (bloco ``api``) e cada portal novo
vira só configuração.
"""

from __future__ import annotations

from datetime import datetime, timezone
import html
import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from job_radar.adaptive import AdaptiveCardLocator
from job_radar.fetching import BlockReason, FetchPolicy
from job_radar.identity import canonicalize_url
from job_radar.models import (
    CollectionStatus,
    SourceConfig,
    SourceRunResult,
    VacancyRecord,
    WorkplaceModel,
)

_MAX_DESCRIPTION = 3000
_TEMPLATE_FIELD = re.compile(r"\{([A-Za-z0-9_.]+)\}")
_WORKPLACES = {
    "remote": WorkplaceModel.REMOTE,
    "remoto": WorkplaceModel.REMOTE,
    "hybrid": WorkplaceModel.HYBRID,
    "hibrido": WorkplaceModel.HYBRID,
    "híbrido": WorkplaceModel.HYBRID,
    "on-site": WorkplaceModel.ONSITE,
    "onsite": WorkplaceModel.ONSITE,
    "on_site": WorkplaceModel.ONSITE,
    "presencial": WorkplaceModel.ONSITE,
}
_EMPLOYMENT_NAMES = {
    "vacancy_type_effective": "CLT",
    "vacancy_type_internship": "Estágio",
    "vacancy_type_apprentice": "Aprendiz",
    "vacancy_type_temporary": "Temporário",
    "vacancy_type_talent_pool": "Banco de talentos",
    "vacancy_type_pj": "PJ",
}


def get_path(data: Any, path: str) -> Any:
    """Valor em ``a.b.c`` de dicionários aninhados (caminho vazio = raiz)."""

    if not path:
        return data
    current = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def clean_text(value: Any) -> str | None:
    """Texto simples: sem HTML, entidades ou marcação markdown."""

    if value is None:
        return None
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("**", "").replace("\xa0", " ")
    text = " ".join(text.split())
    return text or None


def to_iso_datetime(value: Any) -> str | None:
    """Converte datas de portal (ISO, só data ou MM/DD/AAAA) em ISO com fuso."""

    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for pattern in ("%m/%d/%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                parsed = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _workplace(item: dict[str, Any], fields: dict[str, str]) -> WorkplaceModel:
    raw = get_path(item, fields["workplace"]) if "workplace" in fields else None
    if isinstance(raw, str) and raw.strip().casefold() in _WORKPLACES:
        return _WORKPLACES[raw.strip().casefold()]
    if "remote_flag" in fields and get_path(item, fields["remote_flag"]) is True:
        return WorkplaceModel.REMOTE
    return WorkplaceModel.UNKNOWN


def _location(city: str | None, state: str | None) -> str | None:
    parts = []
    for part in (city, state):
        if part:
            parts.append(part.title() if part.isupper() and len(part) > 2 else part)
    return ", ".join(parts) or None


def _skills(item: dict[str, Any], fields: dict[str, str]) -> tuple[str, ...]:
    raw = get_path(item, fields["skills"]) if "skills" in fields else None
    if not isinstance(raw, list):
        return ()
    names = []
    for entry in raw:
        name = entry.get("name") if isinstance(entry, dict) else entry
        cleaned = clean_text(name)
        if cleaned and cleaned not in names:
            names.append(cleaned)
    return tuple(names)


def record_from_item(
    item: dict[str, Any], config: SourceConfig, observed_at: str
) -> VacancyRecord | None:
    fields: dict[str, str] = dict(config.api["fields"])  # type: ignore[arg-type]

    def value(name: str) -> Any:
        return get_path(item, fields[name]) if name in fields else None

    title = clean_text(value("title"))
    if "url" in fields:
        url = value("url")
    else:
        template = fields["url_template"]
        url = _TEMPLATE_FIELD.sub(
            lambda match: str(get_path(item, match.group(1)) or ""), template
        )
    if not title or not isinstance(url, str) or not url.startswith("https://"):
        return None

    workplace = _workplace(item, fields)
    city = clean_text(value("city"))
    state = clean_text(value("state"))
    country = clean_text(value("country"))
    location = _location(city, state)
    remote_scope = country if workplace is WorkplaceModel.REMOTE else None
    if workplace is WorkplaceModel.REMOTE and not location:
        location = "Remoto"
    employment_raw = clean_text(value("employment_type"))
    description = clean_text(value("description"))
    identifier = value("id")

    return VacancyRecord(
        source=config.code,
        source_job_id=str(identifier) if identifier not in (None, "") else None,
        canonical_url=canonicalize_url(url),
        title=title,
        company=clean_text(value("company")),
        description_summary=(description[:_MAX_DESCRIPTION] if description else None),
        employment_type=_EMPLOYMENT_NAMES.get(employment_raw or "", employment_raw),
        technologies=_skills(item, fields),
        location=location,
        workplace_model=workplace,
        remote_scope=remote_scope,
        published_at=to_iso_datetime(value("published")),
        observed_at=observed_at,
        application_deadline=to_iso_datetime(value("deadline")),
        evidence_snippets=(title,),
    )


def page_url(config: SourceConfig, page_index: int) -> str:
    """URL da página ``page_index`` (0 = primeira) conforme o modo de paginação."""

    api = config.api
    parsed = urlsplit(config.start_url)
    page_param = str(api["page_param"])
    size = int(api["page_size"])  # type: ignore[arg-type]
    mode = api["page_mode"]
    number = page_index * size if mode == "offset" else page_index + (1 if mode == "page1" else 0)
    parameters = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in {page_param, str(api.get("size_param", ""))}
    ]
    if api.get("size_param"):
        parameters.append((str(api["size_param"]), str(size)))
    parameters.append((page_param, str(number)))
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(parameters), "")
    )


class JsonApiAdapter:
    def __init__(self, locator: AdaptiveCardLocator | None = None) -> None:
        self._locator = locator

    def collect(self, config: SourceConfig, fetcher: FetchPolicy) -> SourceRunResult:
        page_size = int(config.api["page_size"])  # type: ignore[arg-type]
        items_path = str(config.api["items"])
        observed_at = datetime.now(timezone.utc).isoformat()
        records: list[VacancyRecord] = []
        visited: list[str] = []
        seen_ids: set[str] = set()
        items_observed = 0

        def result(
            status: CollectionStatus,
            stop_reason: str | None = None,
            *,
            has_more: bool = False,
            errors: tuple[str, ...] = (),
        ) -> SourceRunResult:
            return SourceRunResult(
                source_code=config.code,
                status=status,
                records=tuple(records),
                pages_observed=len(visited),
                cards_observed=items_observed,
                has_more=has_more,
                stop_reason=stop_reason,
                errors=errors,
                visited_urls=tuple(visited),
            )

        for page_index in range(config.max_pages):
            url = page_url(config, page_index)
            visited.append(url)
            fetched = fetcher.fetch(url, config)
            if fetched.status is not CollectionStatus.SUCCESS or fetched.response is None:
                auth = {BlockReason.LOGIN_REQUIRED, BlockReason.TWO_FACTOR}
                status = (
                    CollectionStatus.PARTIAL
                    if records
                    else CollectionStatus.AUTH_REQUIRED
                    if fetched.block_reason in auth
                    else fetched.status
                )
                return result(
                    status,
                    fetched.block_reason.value
                    if fetched.block_reason is not None
                    else "FETCH_ERROR",
                    has_more=bool(records),
                    errors=(fetched.error,) if fetched.error else (),
                )
            try:
                payload = json.loads(fetched.response.body)
            except (ValueError, TypeError):
                payload = None
            items = get_path(payload, items_path)
            if not isinstance(items, list):
                return result(
                    CollectionStatus.PARTIAL if records else CollectionStatus.ERROR,
                    "LAYOUT_CHANGED",
                    has_more=bool(records),
                )
            items_observed += len(items)
            new_on_page = 0
            for item in items:
                if not isinstance(item, dict):
                    continue
                record = record_from_item(item, config, observed_at)
                if record is None:
                    continue
                key = record.source_job_id or record.canonical_url
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                records.append(record)
                new_on_page += 1
            if not items:
                break
            if new_on_page == 0:
                # O servidor ignorou a paginação e repetiu a página.
                return result(CollectionStatus.PARTIAL, "PAGINATION_LOOP", has_more=True)
            if len(items) < page_size:
                break
        else:
            return result(CollectionStatus.PARTIAL, "PAGE_LIMIT", has_more=True)

        if not records:
            return result(CollectionStatus.EMPTY, "NO_RESULTS")
        return result(CollectionStatus.SUCCESS)
