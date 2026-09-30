from __future__ import annotations

import ipaddress
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

import yaml

from job_radar.models import BrowserOptions, SearchProfile, SourceConfig, SourceKind


class ConfigError(ValueError):
    """Indica configuração inválida antes de qualquer acesso à rede."""


_PROFILE_KEYS = {
    "positive_keywords",
    "seniority_levels",
    "location_scopes",
    "excluded_terms",
}
_REQUIRED_SOURCE_KEYS = {
    "code",
    "kind",
    "start_url",
    "enabled",
    "max_pages",
    "min_interval_seconds",
    "requires_auth",
}
_OPTIONAL_SOURCE_KEYS = {
    "selectors",
    "queries",
    "default_country",
    "adaptive",
    "single_page",
    "query_path",
    "query_param",
    "browser",
    "fixed_queries",
    "tech_focus",
    "api",
}
_API_KEYS = {
    "items",
    "page_param",
    "page_mode",
    "page_size",
    "size_param",
    "workplace_param",
    "state_param",
    "strip_levels",
    "fields",
}
_API_FIELD_KEYS = {
    "id",
    "title",
    "company",
    "city",
    "state",
    "country",
    "published",
    "deadline",
    "employment_type",
    "description",
    "workplace",
    "remote_flag",
    "url",
    "url_template",
    "skills",
}
_API_PAGE_MODES = {"offset", "page0", "page1"}
_SOURCE_KEYS = _REQUIRED_SOURCE_KEYS | _OPTIONAL_SOURCE_KEYS
_BROWSER_KEYS = {"disable_resources", "blocked_domains", "scroll_to_load"}
_REQUIRED_GENERIC_SELECTORS = {"card", "title", "url"}
_HOSTNAME_PATTERN = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*",
    re.IGNORECASE,
)
_ISO_ALPHA_2_COUNTRY_CODES = frozenset(
    """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ
    BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ
    CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ
    DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR
    GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY
    HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP
    KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY
    MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ
    NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR
    PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN
    SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW
    TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
    """.split()
)


def _read_yaml(path: Path) -> Mapping[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Nao foi possivel ler {path}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ConfigError(f"A raiz de {path} deve ser um objeto YAML.")
    return raw


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ConfigError(f"{field_name} deve ser uma lista nao vazia de textos.")
    return tuple(item.strip().casefold() for item in value)


def load_profile(path: Path) -> SearchProfile:
    raw = _read_yaml(path)
    unknown = set(raw) - _PROFILE_KEYS
    missing = {"positive_keywords", "seniority_levels", "location_scopes"} - set(
        raw
    )
    if unknown or missing:
        raise ConfigError(
            f"Perfil invalido; chaves desconhecidas={sorted(unknown)}, ausentes={sorted(missing)}"
        )
    return SearchProfile(
        positive_keywords=_string_tuple(raw["positive_keywords"], "positive_keywords"),
        seniority_levels=_string_tuple(raw["seniority_levels"], "seniority_levels"),
        location_scopes=_string_tuple(raw["location_scopes"], "location_scopes"),
        excluded_terms=tuple(
            item.strip().casefold() for item in raw.get("excluded_terms", [])
        ),
    )


def _load_browser_options(value: Any, index: int) -> BrowserOptions:
    if not isinstance(value, Mapping):
        raise ConfigError(f"sources[{index}].browser deve ser um objeto.")
    if not all(isinstance(key, str) for key in value):
        raise ConfigError(f"sources[{index}].browser exige chaves de texto.")
    unknown = set(value) - _BROWSER_KEYS
    if unknown:
        raise ConfigError(
            f"sources[{index}].browser invalido; chaves desconhecidas={sorted(unknown)}"
        )

    disable_resources = value.get("disable_resources", False)
    if not isinstance(disable_resources, bool):
        raise ConfigError(
            f"sources[{index}].browser.disable_resources deve ser booleano."
        )

    scroll_to_load = value.get("scroll_to_load", False)
    if not isinstance(scroll_to_load, bool):
        raise ConfigError(
            f"sources[{index}].browser.scroll_to_load deve ser booleano."
        )

    blocked_domains = value.get("blocked_domains", [])
    if not isinstance(blocked_domains, list):
        raise ConfigError(
            f"sources[{index}].browser.blocked_domains deve ser uma lista."
        )
    normalized_domains: list[str] = []
    for domain_index, domain in enumerate(blocked_domains):
        field_name = (
            f"sources[{index}].browser.blocked_domains[{domain_index}]"
        )
        if not isinstance(domain, str):
            raise ConfigError(f"{field_name} deve ser um hostname valido.")
        stripped = domain.strip()
        if not stripped or not stripped.isascii():
            raise ConfigError(f"{field_name} deve ser um hostname valido.")
        normalized = stripped.casefold()
        try:
            ipaddress.ip_address(normalized)
        except ValueError:
            pass
        else:
            raise ConfigError(f"{field_name} deve ser um hostname valido.")
        if _HOSTNAME_PATTERN.fullmatch(normalized) is None:
            raise ConfigError(f"{field_name} deve ser um hostname valido.")
        normalized_domains.append(normalized)

    return BrowserOptions(
        disable_resources=disable_resources,
        blocked_domains=tuple(normalized_domains),
        scroll_to_load=scroll_to_load,
    )


def _load_source(item: Any, index: int) -> SourceConfig:
    if not isinstance(item, Mapping):
        raise ConfigError(f"sources[{index}] deve ser um objeto.")
    unknown = set(item) - _SOURCE_KEYS
    missing = _REQUIRED_SOURCE_KEYS - set(item)
    if unknown or missing:
        raise ConfigError(
            f"sources[{index}] invalida; chaves desconhecidas={sorted(unknown)}, ausentes={sorted(missing)}"
        )
    try:
        kind = SourceKind(str(item["kind"]))
    except ValueError as exc:
        raise ConfigError(f"sources[{index}].kind invalido: {item['kind']}") from exc

    url = str(item["start_url"])
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ConfigError(f"sources[{index}].start_url deve usar HTTPS.")

    max_pages = item["max_pages"]
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or not 1 <= max_pages <= 100:
        raise ConfigError(f"sources[{index}].max_pages deve estar entre 1 e 100.")
    interval = item["min_interval_seconds"]
    if not isinstance(interval, (int, float)) or isinstance(interval, bool) or interval < 1:
        raise ConfigError(f"sources[{index}].min_interval_seconds deve ser >= 1.")

    selectors = item.get("selectors", {})
    if not isinstance(selectors, Mapping) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in selectors.items()
    ):
        raise ConfigError(f"sources[{index}].selectors deve ser um objeto de textos.")
    if kind is SourceKind.GENERIC and not _REQUIRED_GENERIC_SELECTORS <= set(selectors):
        raise ConfigError(
            f"sources[{index}].selectors deve conter card, title e url para fonte generica."
        )

    queries_raw = item.get("queries", [])
    if not isinstance(queries_raw, list) or not all(
        isinstance(query, str) and query.strip() for query in queries_raw
    ):
        raise ConfigError(f"sources[{index}].queries deve ser uma lista de textos.")

    code = str(item["code"]).strip()
    if not code:
        raise ConfigError(f"sources[{index}].code nao pode ser vazio.")
    if not isinstance(item["enabled"], bool) or not isinstance(
        item["requires_auth"], bool
    ):
        raise ConfigError(f"sources[{index}] exige enabled/requires_auth booleanos.")

    default_country = item.get("default_country")
    if default_country is not None and (
        not isinstance(default_country, str)
        or default_country not in _ISO_ALPHA_2_COUNTRY_CODES
    ):
        raise ConfigError(
            f"sources[{index}].default_country deve usar codigo ISO alfa-2 maiusculo."
        )

    adaptive = item.get("adaptive", True)
    if not isinstance(adaptive, bool):
        raise ConfigError(f"sources[{index}].adaptive deve ser booleano.")

    single_page = item.get("single_page", False)
    if not isinstance(single_page, bool):
        raise ConfigError(f"sources[{index}].single_page deve ser booleano.")

    query_path = item.get("query_path")
    if query_path is not None and (
        not isinstance(query_path, str)
        or not query_path.startswith("/")
        or "{query}" not in query_path
    ):
        raise ConfigError(
            f"sources[{index}].query_path deve iniciar com / e conter {{query}}."
        )
    query_param = item.get("query_param")
    if query_param is not None and (
        not isinstance(query_param, str) or not query_param.strip()
    ):
        raise ConfigError(f"sources[{index}].query_param deve ser um texto.")
    if query_path is not None and query_param is not None:
        raise ConfigError(
            f"sources[{index}] aceita query_path ou query_param, nao ambos."
        )

    fixed_queries = item.get("fixed_queries", False)
    if not isinstance(fixed_queries, bool):
        raise ConfigError(f"sources[{index}].fixed_queries deve ser booleano.")
    if fixed_queries and not queries_raw:
        raise ConfigError(f"sources[{index}].fixed_queries exige queries.")
    tech_focus = item.get("tech_focus", False)
    if not isinstance(tech_focus, bool):
        raise ConfigError(f"sources[{index}].tech_focus deve ser booleano.")

    browser = _load_browser_options(item.get("browser", {}), index)
    api = _load_api_options(item.get("api"), kind, index)

    return SourceConfig(
        code=code,
        kind=kind,
        start_url=url,
        enabled=item["enabled"],
        max_pages=max_pages,
        min_interval_seconds=float(interval),
        requires_auth=item["requires_auth"],
        selectors=dict(selectors),
        queries=tuple(query.strip() for query in queries_raw),
        default_country=default_country,
        adaptive=adaptive,
        single_page=single_page,
        query_path=query_path,
        query_param=query_param.strip() if query_param else None,
        browser=browser,
        fixed_queries=fixed_queries,
        tech_focus=tech_focus,
        api=api,
    )


def _load_api_options(value: Any, kind: SourceKind, index: int) -> dict[str, Any]:
    label = f"sources[{index}].api"
    if kind is not SourceKind.JSON:
        if value is not None:
            raise ConfigError(f"{label} so vale para fontes kind: json.")
        return {}
    if not isinstance(value, Mapping):
        raise ConfigError(f"{label} e obrigatorio e deve ser um objeto (kind: json).")
    unknown = set(value) - _API_KEYS
    if unknown:
        raise ConfigError(f"{label} invalido; chaves desconhecidas={sorted(unknown)}")
    items = value.get("items", "")
    if not isinstance(items, str):
        raise ConfigError(f"{label}.items deve ser um texto (caminho da lista).")
    page_mode = value.get("page_mode", "offset")
    if page_mode not in _API_PAGE_MODES:
        raise ConfigError(f"{label}.page_mode deve ser um de {sorted(_API_PAGE_MODES)}.")
    page_size = value.get("page_size", 50)
    if not isinstance(page_size, int) or isinstance(page_size, bool) or not 1 <= page_size <= 500:
        raise ConfigError(f"{label}.page_size deve estar entre 1 e 500.")
    for key in ("page_param", "size_param", "workplace_param", "state_param"):
        if key in value and (not isinstance(value[key], str) or not value[key].strip()):
            raise ConfigError(f"{label}.{key} deve ser um texto.")
    if "page_param" not in value:
        raise ConfigError(f"{label}.page_param e obrigatorio.")
    strip_levels = value.get("strip_levels", False)
    if not isinstance(strip_levels, bool):
        raise ConfigError(f"{label}.strip_levels deve ser booleano.")
    fields = value.get("fields")
    if not isinstance(fields, Mapping) or not all(
        isinstance(k, str) and isinstance(v, str) and v for k, v in fields.items()
    ):
        raise ConfigError(f"{label}.fields deve ser um objeto de textos.")
    bad = set(fields) - _API_FIELD_KEYS
    if bad:
        raise ConfigError(f"{label}.fields com chaves desconhecidas={sorted(bad)}")
    if "title" not in fields or not ({"url", "url_template"} & set(fields)):
        raise ConfigError(f"{label}.fields exige title e url (ou url_template).")
    return {
        "items": items,
        "page_param": value["page_param"].strip(),
        "page_mode": page_mode,
        "page_size": page_size,
        **{
            key: value[key].strip()
            for key in ("size_param", "workplace_param", "state_param")
            if key in value
        },
        "strip_levels": strip_levels,
        "fields": dict(fields),
    }


def load_sources(path: Path) -> tuple[SourceConfig, ...]:
    raw = _read_yaml(path)
    if set(raw) != {"sources"} or not isinstance(raw["sources"], list):
        raise ConfigError("O arquivo de fontes deve conter apenas a lista sources.")
    sources = tuple(
        _load_source(item, index) for index, item in enumerate(raw["sources"])
    )
    codes = [source.code for source in sources]
    if len(codes) != len(set(codes)):
        raise ConfigError("Os codigos das fontes devem ser unicos.")
    return sources
