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
    # Vazio = usar positive_keywords/excluded_terms do profile.yaml.
    technologies: tuple[str, ...] = ()
    excluded_terms: tuple[str, ...] = ()
    # Refinos (todos opcionais): ver SearchProfile.
    required_keywords: tuple[str, ...] = ()
    bonus_keywords: tuple[str, ...] = ()
    blocked_keywords: tuple[str, ...] = ()
    excluded_companies: tuple[str, ...] = ()
    favorite_companies: tuple[str, ...] = ()
    contract_types: tuple[str, ...] = ()
    avoid_advanced_english: bool = False

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
        for field_name in ("technologies", "excluded_terms"):
            object.__setattr__(
                self,
                field_name,
                _validated_texts(
                    getattr(self, field_name),
                    field=field_name,
                    minimum=0,
                    maximum=_MAX_FILTER_TERMS,
                    item_limit=60,
                    casefold=True,
                ),
            )
        for field_name, maximum in _REFINE_LIMITS.items():
            object.__setattr__(
                self,
                field_name,
                _validated_texts(
                    getattr(self, field_name),
                    field=field_name,
                    minimum=0,
                    maximum=maximum,
                    item_limit=80,
                    casefold=True,
                ),
            )
        contracts = _validated_texts(
            self.contract_types,
            field="contract_types",
            minimum=0,
            maximum=len(CONTRACT_TYPES),
            item_limit=20,
            casefold=False,
        )
        contracts = tuple(item.upper() for item in contracts)
        if not set(contracts) <= set(CONTRACT_TYPES):
            raise PreferencesError("contract_types aceita apenas CLT, PJ e FREELANCE.")
        object.__setattr__(self, "contract_types", contracts)
        if not isinstance(self.avoid_advanced_english, bool):
            raise PreferencesError("avoid_advanced_english deve ser verdadeiro ou falso.")


CONTRACT_TYPES = ("CLT", "PJ", "FREELANCE")
_REFINE_LIMITS = {
    "required_keywords": 20,
    "bonus_keywords": 40,
    "blocked_keywords": 40,
    "excluded_companies": 60,
    "favorite_companies": 60,
}

_REQUIRED_FIELDS = {
    "search_terms",
    "seniority_levels",
    "workplace_models",
    "location_scopes",
}
_OPTIONAL_FIELDS = {
    "technologies",
    "excluded_terms",
    *_REFINE_LIMITS,
    "contract_types",
    "avoid_advanced_english",
}
_FIELDS = _REQUIRED_FIELDS | _OPTIONAL_FIELDS
_MAX_FILTER_TERMS = 40
_SENIORITY_LEVELS = {"estagio", "junior", "pleno", "senior"}
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
        maximum=4,
        item_limit=20,
        casefold=True,
    )
    normalized = tuple(_without_accents(value) for value in normalized)
    if not set(normalized) <= _SENIORITY_LEVELS:
        raise PreferencesError(
            "seniority_levels aceita apenas estagio, junior, pleno e senior."
        )
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
    missing = _REQUIRED_FIELDS - set(payload)
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
        technologies=payload.get("technologies", ()),  # type: ignore[arg-type]
        excluded_terms=payload.get("excluded_terms", ()),  # type: ignore[arg-type]
        **{name: payload.get(name, ()) for name in _REFINE_LIMITS},  # type: ignore[arg-type]
        contract_types=payload.get("contract_types", ()),  # type: ignore[arg-type]
        avoid_advanced_english=payload.get("avoid_advanced_english", False),  # type: ignore[arg-type]
    )


def validate_preferences_payload(
    payload: Mapping[str, object],
) -> SearchPreferences:
    """Valida e normaliza o contrato recebido pela interface local."""
    return preferences_from_dict(payload)


def preferences_to_dict(preferences: SearchPreferences) -> dict[str, object]:
    validated = replace(preferences)  # revalida (__post_init__)
    return {
        "search_terms": list(validated.search_terms),
        "seniority_levels": list(validated.seniority_levels),
        "workplace_models": [model.value for model in validated.workplace_models],
        "location_scopes": list(validated.location_scopes),
        "technologies": list(validated.technologies),
        "excluded_terms": list(validated.excluded_terms),
        **{name: list(getattr(validated, name)) for name in _REFINE_LIMITS},
        "contract_types": list(validated.contract_types),
        "avoid_advanced_english": validated.avoid_advanced_english,
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
            technologies=tuple(default_profile.positive_keywords[:_MAX_FILTER_TERMS]),
            excluded_terms=tuple(default_profile.excluded_terms[:_MAX_FILTER_TERMS]),
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


def _effective_excluded_terms(
    excluded: tuple[str, ...], seniority_levels: tuple[str, ...]
) -> tuple[str, ...]:
    """Tira das exclusões os níveis que o próprio perfil pediu.

    Quem escolhe "pleno" não pode ter "pleno" como termo de exclusão; quem escolhe
    "sênior" também aceita cargos de liderança/especialidade.
    """

    from job_radar.classifier import LEADERSHIP_TERMS, _canonical_term

    selected = {_canonical_term(level) for level in seniority_levels}
    drop_leadership = "senior" in selected
    leadership = {_canonical_term(term) for term in LEADERSHIP_TERMS}
    return tuple(
        term
        for term in excluded
        if _canonical_term(term) not in selected
        and not (drop_leadership and _canonical_term(term) in leadership)
    )


def apply_preferences(
    profile: SearchProfile, preferences: SearchPreferences
) -> SearchProfile:
    excluded = _effective_excluded_terms(
        preferences.excluded_terms or profile.excluded_terms,
        preferences.seniority_levels,
    )
    return replace(
        profile,
        search_terms=preferences.search_terms,
        seniority_levels=preferences.seniority_levels,
        workplace_models=preferences.workplace_models,
        location_scopes=preferences.location_scopes,
        positive_keywords=preferences.technologies or profile.positive_keywords,
        excluded_terms=excluded,
        required_keywords=preferences.required_keywords,
        bonus_keywords=preferences.bonus_keywords,
        blocked_keywords=preferences.blocked_keywords,
        excluded_companies=preferences.excluded_companies,
        favorite_companies=preferences.favorite_companies,
        contract_types=preferences.contract_types,
        avoid_advanced_english=preferences.avoid_advanced_english,
    )
