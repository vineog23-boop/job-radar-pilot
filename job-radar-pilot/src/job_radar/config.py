from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

import yaml

from job_radar.models import SearchProfile, SourceConfig, SourceKind


class ConfigError(ValueError):
    """Indica configuração inválida antes de qualquer acesso à rede."""


_PROFILE_KEYS = {
    "positive_keywords",
    "seniority_levels",
    "location_scopes",
    "excluded_terms",
}
_SOURCE_KEYS = {
    "code",
    "kind",
    "start_url",
    "enabled",
    "max_pages",
    "min_interval_seconds",
    "requires_auth",
    "selectors",
    "queries",
    "default_country",
}
_REQUIRED_SOURCE_KEYS = _SOURCE_KEYS - {"selectors", "queries", "default_country"}
_REQUIRED_GENERIC_SELECTORS = {"card", "title", "url"}
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
    )


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
