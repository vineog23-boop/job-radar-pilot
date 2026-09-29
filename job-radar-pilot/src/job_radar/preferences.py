from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable, Mapping
import unicodedata

from job_radar.models import SearchProfile, WorkplaceModel


class PreferencesError(ValueError):
    """Indica preferências locais fora do contrato aceito."""


@dataclass(frozen=True, slots=True)
class SearchPreferences:
    search_terms: tuple[str, ...]
    seniority_levels: tuple[str, ...]
    workplace_models: tuple[WorkplaceModel, ...]
    location_scopes: tuple[str, ...]

    def __post_init__(self) -> None:
        search_terms = _validated_texts(
            self.search_terms,
            field="search_terms",
            minimum=1,
            maximum=12,
            item_limit=120,
            casefold=False,
        )
        seniority_levels = _validated_seniority(self.seniority_levels)
        workplace_models = _validated_workplace_models(self.workplace_models)
        location_scopes = _validated_texts(
            self.location_scopes,
            field="location_scopes",
            minimum=1,
            maximum=12,
            item_limit=100,
            casefold=True,
        )
        object.__setattr__(self, "search_terms", search_terms)
        object.__setattr__(self, "seniority_levels", seniority_levels)
        object.__setattr__(self, "workplace_models", workplace_models)
        object.__setattr__(self, "location_scopes", location_scopes)


_FIELDS = {
    "search_terms",
    "seniority_levels",
    "workplace_models",
    "location_scopes",
}
_SENIORITY_LEVELS = {"estagio", "junior"}
_WORKPLACE_MODELS = {
    WorkplaceModel.REMOTE,
    WorkplaceModel.HYBRID,
    WorkplaceModel.ONSITE,
}


def _without_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )


def _validated_texts(
    values: object,
    *,
    field: str,
    minimum: int,
    maximum: int,
    item_limit: int,
    casefold: bool,
) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or not minimum <= len(values) <= maximum:
        raise PreferencesError(
            f"{field} deve conter entre {minimum} e {maximum} textos."
        )

    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            raise PreferencesError(f"{field} deve conter apenas textos.")
        value = " ".join(item.split())
        if not value or len(value) > item_limit:
            raise PreferencesError(
                f"{field} contem texto vazio ou maior que {item_limit} caracteres."
            )
        identity = value.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        normalized.append(value.casefold() if casefold else value)
    if len(normalized) < minimum:
        raise PreferencesError(f"{field} nao pode ficar vazio apos normalizacao.")
    return tuple(normalized)


def _validated_seniority(values: object) -> tuple[str, ...]:
    normalized = _validated_texts(
        values,
        field="seniority_levels",
        minimum=1,
        maximum=2,
        item_limit=20,
        casefold=True,
    )
    normalized = tuple(_without_accents(value) for value in normalized)
    if not set(normalized) <= _SENIORITY_LEVELS:
        raise PreferencesError("seniority_levels aceita apenas estagio e junior.")
    return normalized


def _validated_workplace_models(values: object) -> tuple[WorkplaceModel, ...]:
    if not isinstance(values, (list, tuple)) or len(values) > 3:
        raise PreferencesError("workplace_models deve conter no maximo 3 valores.")
    normalized: list[WorkplaceModel] = []
    for item in values:
        try:
            model = item if isinstance(item, WorkplaceModel) else WorkplaceModel(str(item))
        except ValueError as exc:
            raise PreferencesError(
                "workplace_models aceita apenas REMOTE, HYBRID e ONSITE."
            ) from exc
        if model not in _WORKPLACE_MODELS:
            raise PreferencesError(
                "workplace_models aceita apenas REMOTE, HYBRID e ONSITE."
            )
        if model not in normalized:
            normalized.append(model)
    return tuple(normalized)


def preferences_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "JobRadar" / "search-preferences.json"


def preferences_from_dict(payload: Mapping[str, object]) -> SearchPreferences:
    if not isinstance(payload, Mapping):
        raise PreferencesError("Preferencias devem ser um objeto JSON.")
    unknown = set(payload) - _FIELDS
    missing = _FIELDS - set(payload)
    if unknown or missing:
        raise PreferencesError(
            "Preferencias com chaves desconhecidas="
            f"{sorted(unknown)}, ausentes={sorted(missing)}."
        )
    return SearchPreferences(
        search_terms=payload["search_terms"],  # type: ignore[arg-type]
        seniority_levels=payload["seniority_levels"],  # type: ignore[arg-type]
        workplace_models=payload["workplace_models"],  # type: ignore[arg-type]
        location_scopes=payload["location_scopes"],  # type: ignore[arg-type]
    )


def validate_preferences_payload(
    payload: Mapping[str, object],
) -> SearchPreferences:
    """Valida e normaliza o contrato recebido pela interface local."""
    return preferences_from_dict(payload)


def preferences_to_dict(preferences: SearchPreferences) -> dict[str, list[str]]:
    validated = SearchPreferences(
        search_terms=preferences.search_terms,
        seniority_levels=preferences.seniority_levels,
        workplace_models=preferences.workplace_models,
        location_scopes=preferences.location_scopes,
    )
    return {
        "search_terms": list(validated.search_terms),
        "seniority_levels": list(validated.seniority_levels),
        "workplace_models": [model.value for model in validated.workplace_models],
        "location_scopes": list(validated.location_scopes),
    }


def load_preferences(
    *,
    default_profile: SearchProfile,
    default_search_terms: Iterable[str],
    path: Path | None = None,
) -> SearchPreferences:
    resolved_path = path or preferences_path()
    if not resolved_path.exists():
        normalized_defaults: list[str] = []
        seen_defaults: set[str] = set()
        for item in default_search_terms:
            identity = " ".join(item.split()).casefold()
            if identity and identity not in seen_defaults:
                seen_defaults.add(identity)
                normalized_defaults.append(" ".join(item.split()))
            if len(normalized_defaults) == 12:
                break
        return SearchPreferences(
            search_terms=tuple(normalized_defaults),
            seniority_levels=default_profile.seniority_levels,
            workplace_models=default_profile.workplace_models,
            location_scopes=default_profile.location_scopes,
        )
    try:
        raw = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreferencesError(
            f"Nao foi possivel ler preferencias locais em {resolved_path}."
        ) from exc
    if not isinstance(raw, Mapping):
        raise PreferencesError("A raiz das preferencias deve ser um objeto JSON.")
    return preferences_from_dict(raw)


def save_preferences(
    preferences: SearchPreferences,
    path: Path | None = None,
) -> Path:
    resolved_path = path or preferences_path()
    payload = preferences_to_dict(preferences)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{resolved_path.name}.",
            suffix=".tmp",
            dir=resolved_path.parent,
            delete=False,
        ) as temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(resolved_path)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise PreferencesError(
            f"Nao foi possivel salvar preferencias locais em {resolved_path}."
        ) from exc
    return resolved_path


def apply_preferences(
    profile: SearchProfile, preferences: SearchPreferences
) -> SearchProfile:
    return replace(
        profile,
        search_terms=preferences.search_terms,
        seniority_levels=preferences.seniority_levels,
        workplace_models=preferences.workplace_models,
        location_scopes=preferences.location_scopes,
    )
