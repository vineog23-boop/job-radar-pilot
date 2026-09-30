from __future__ import annotations

import re
from urllib.parse import urlencode

from job_radar.geo import STATE_NAMES, uf_from_scope
from job_radar.models import WorkplaceModel
from job_radar.preferences import SearchPreferences


_LINKEDIN_HOME_URL = "https://www.linkedin.com/"
_LINKEDIN_SEARCH_URL = "https://www.linkedin.com/jobs/search/"

# Parâmetros públicos da própria busca de vagas do LinkedIn (os mesmos que o
# site coloca na barra de endereço quando você usa os filtros).
_PERIODS = {
    "day": "r86400",
    "week": "r604800",
    "month": "r2592000",
    "any": "",
}
DEFAULT_PERIOD = "week"
_EXPERIENCE = {
    "estagio": ("1",),
    "junior": ("2", "3"),
    "pleno": ("3", "4"),
    "senior": ("4",),
}
_WORKPLACE = {
    WorkplaceModel.ONSITE: "1",
    WorkplaceModel.REMOTE: "2",
    WorkplaceModel.HYBRID: "3",
}
MAX_TERMS_WITH_LINKS = 12
MAX_LOCATIONS = 3


def location_query(scope: str) -> str:
    """Texto de localização para a busca ("sao-carlos-sp" → "Sao Carlos, São Paulo, Brasil")."""

    text = scope.strip()
    if not text:
        return "Brasil"
    words = [word for word in re.split(r"[-_\s]+", text) if word]
    lowered = [word.casefold() for word in words]
    if lowered in (["brasil"], ["brazil"], ["remoto", "brasil"]):
        return "Brasil"
    uf = uf_from_scope(scope)
    if uf is None:
        return ", ".join(word.capitalize() for word in words)
    state = STATE_NAMES[uf]
    state_words = [word.casefold() for word in re.split(r"\s+", state)]
    stripped = lowered
    if stripped and stripped[-1] == uf.casefold():
        stripped = stripped[:-1]
    elif len(stripped) >= len(state_words) and stripped[-len(state_words) :] == state_words:
        stripped = stripped[: -len(state_words)]
    city = " ".join(word.capitalize() for word in stripped)
    return ", ".join(part for part in (city, state, "Brasil") if part)


def linkedin_search_url(
    term: str,
    *,
    location: str,
    seniority_levels: tuple[str, ...] = (),
    workplace_models: tuple[WorkplaceModel, ...] = (),
    period: str = DEFAULT_PERIOD,
) -> str:
    """Link de busca filtrada (palavra-chave, local, nível, modelo e recência)."""

    parameters: list[tuple[str, str]] = [("keywords", term), ("location", location)]
    experience = sorted({code for level in seniority_levels for code in _EXPERIENCE.get(level, ())})
    if experience and len(seniority_levels) < len(_EXPERIENCE):
        parameters.append(("f_E", ",".join(experience)))
    workplace = sorted({_WORKPLACE[m] for m in workplace_models if m in _WORKPLACE})
    if workplace and len(workplace) < len(_WORKPLACE):
        parameters.append(("f_WT", ",".join(workplace)))
    recency = _PERIODS.get(period, _PERIODS[DEFAULT_PERIOD])
    if recency:
        parameters.append(("f_TPR", recency))
    parameters.append(("sortBy", "DD"))
    return f"{_LINKEDIN_SEARCH_URL}?{urlencode(parameters)}"


def build_linkedin_search_plan(
    preferences: SearchPreferences, *, period: str = DEFAULT_PERIOD
) -> dict[str, object]:
    """Monta atalhos oficiais sem acessar, controlar ou ler o LinkedIn."""
    if period not in _PERIODS:
        period = DEFAULT_PERIOD
    searches = [{"label": term} for term in preferences.search_terms]
    locations = [location_query(scope) for scope in preferences.location_scopes]
    locations = list(dict.fromkeys(locations))[:MAX_LOCATIONS] or ["Brasil"]
    links = [
        {
            "term": term,
            "locations": [
                {
                    "label": location,
                    "url": linkedin_search_url(
                        term,
                        location=location,
                        seniority_levels=preferences.seniority_levels,
                        workplace_models=preferences.workplace_models,
                        period=period,
                    ),
                }
                for location in locations
            ],
        }
        for term in preferences.search_terms[:MAX_TERMS_WITH_LINKS]
    ]
    return {
        "portal": "LinkedIn",
        "access_mode": "MANUAL_FOREGROUND",
        "network_access": False,
        "home_url": _LINKEDIN_HOME_URL,
        "period": period,
        "searches": searches,
        "links": links,
        "filters": {
            "seniority_levels": list(preferences.seniority_levels),
            "workplace_models": [
                model.value for model in preferences.workplace_models
            ],
            "location_scopes": list(preferences.location_scopes),
        },
        "notice": (
            "Os links abrem a busca filtrada oficial no seu navegador. O Radar não "
            "acessa, captura nem armazena cookies ou tokens e não inicia coleta "
            "automática; para trazer as vagas para cá, cole os links ou o texto "
            "dos alertas no importador."
        ),
    }
