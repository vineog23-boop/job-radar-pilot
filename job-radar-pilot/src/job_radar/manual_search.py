from __future__ import annotations

from job_radar.preferences import SearchPreferences


_LINKEDIN_HOME_URL = "https://www.linkedin.com/"


def build_linkedin_search_plan(preferences: SearchPreferences) -> dict[str, object]:
    """Monta atalhos oficiais sem acessar, controlar ou ler o LinkedIn."""
    searches = [{"label": term} for term in preferences.search_terms]
    return {
        "portal": "LinkedIn",
        "access_mode": "MANUAL_FOREGROUND",
        "network_access": False,
        "home_url": _LINKEDIN_HOME_URL,
        "searches": searches,
        "filters": {
            "seniority_levels": list(preferences.seniority_levels),
            "workplace_models": [
                model.value for model in preferences.workplace_models
            ],
            "location_scopes": list(preferences.location_scopes),
        },
        "notice": (
            "O link abre a página inicial oficial. O Radar não acessa, captura "
            "nem armazena cookies ou tokens e não inicia coleta automática."
        ),
    }
