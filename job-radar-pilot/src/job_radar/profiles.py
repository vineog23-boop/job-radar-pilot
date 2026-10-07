"""Perfis de busca nomeados: vários perfis salvos, um ativo por vez.

Cada perfil guarda um ``SearchPreferences`` completo. Ativar um perfil grava as
preferências no arquivo principal (o mesmo que a coleta já lê), então o resto do
sistema não precisa saber que existem vários perfis.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
import os
import tempfile
from pathlib import Path
import re
import unicodedata

from job_radar.preferences import (
    PreferencesError,
    SearchPreferences,
    preferences_from_dict,
    preferences_to_dict,
    save_preferences,
)

_ACTIVE_FILE = "_ativo.json"
_NAME_LIMIT = 40


def profiles_dir(preferences_path: Path) -> Path:
    return preferences_path.parent / "profiles"


def _clean_name(name: object) -> str:
    if not isinstance(name, str):
        raise PreferencesError("Nome do perfil deve ser um texto.")
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > _NAME_LIMIT:
        raise PreferencesError(
            f"Nome do perfil deve ter de 1 a {_NAME_LIMIT} caracteres."
        )
    if re.search(r"[\\/:*?\"<>|]", cleaned):
        raise PreferencesError("Nome do perfil contém caracteres inválidos.")
    return cleaned


def _slug(name: str) -> str:
    ascii_name = "".join(
        char
        for char in unicodedata.normalize("NFKD", name.casefold())
        if not unicodedata.combining(char)
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    if not slug:
        raise PreferencesError("Nome do perfil precisa ter letras ou números.")
    return slug


def _profile_path(preferences_path: Path, name: str) -> Path:
    return profiles_dir(preferences_path) / f"{_slug(name)}.json"


def save_profile(
    preferences_path: Path, name: object, preferences: SearchPreferences
) -> str:
    display = _clean_name(name)
    path = _profile_path(preferences_path, display)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"name": display, "preferences": preferences_to_dict(preferences)},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return display


def _read_profile(path: Path) -> tuple[str, SearchPreferences] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return str(raw["name"]), preferences_from_dict(raw["preferences"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError, PreferencesError):
        return None


def list_profiles(preferences_path: Path) -> list[dict[str, object]]:
    directory = profiles_dir(preferences_path)
    if not directory.is_dir():
        return []
    active = active_profile(preferences_path)
    profiles: list[dict[str, object]] = []
    for path in sorted(directory.glob("*.json")):
        if path.name == _ACTIVE_FILE:
            continue
        loaded = _read_profile(path)
        if loaded is None:
            continue
        name, preferences = loaded
        profiles.append(
            {
                "name": name,
                "active": name == active,
                "preferences": preferences_to_dict(preferences),
            }
        )
    return profiles


def active_profile(preferences_path: Path) -> str | None:
    path = profiles_dir(preferences_path) / _ACTIVE_FILE
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("name")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    return value if isinstance(value, str) else None


def _set_active(preferences_path: Path, name: str | None) -> None:
    directory = profiles_dir(preferences_path)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / _ACTIVE_FILE).write_text(
        json.dumps({"name": name}, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def activate_profile(preferences_path: Path, name: object) -> SearchPreferences:
    stored_name, preferences = read_profile(preferences_path, name)
    save_preferences(preferences, path=preferences_path)
    _set_active(preferences_path, stored_name)
    return preferences


def delete_profile(preferences_path: Path, name: object) -> None:
    display = _clean_name(name)
    path = _profile_path(preferences_path, display)
    if not path.exists():
        raise PreferencesError(f"Perfil '{display}' não encontrado.")
    path.unlink()
    if active_profile(preferences_path) == display:
        _set_active(preferences_path, None)


@contextmanager
def profile_application(preferences_path: Path, output_dir: Path) -> Iterator[None]:
    """Restaura perfil e saída se a aplicação falhar; exige OutputLock externo.

    A confirmação é única para o chamador. Não é um journal de recuperação
    contra encerramento abrupto do processo ou falha do próprio disco no rollback.
    """
    from job_radar.cleanup import DISCARDED_NAME

    directory = profiles_dir(preferences_path)
    paths = {preferences_path, *directory.glob("*.json")}
    paths.update(output_dir / name for name in (
        "vagas.jsonl", "vagas.csv", "relatorio-execucao.json", DISCARDED_NAME,
    ))
    before = {path: path.read_bytes() if path.exists() else None for path in paths}
    try:
        yield
    except Exception:
        # Inclui um perfil criado durante a tentativa que falhou.
        for path in paths | set(directory.glob("*.json")):
            content = before.get(path)
            if content is None:
                path.unlink(missing_ok=True)
            elif not path.exists() or path.read_bytes() != content:
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
                        temporary = Path(handle.name)
                        handle.write(content)
                        handle.flush()
                        os.fsync(handle.fileno())
                    temporary.replace(path)
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
        raise


def read_profile(preferences_path: Path, name: object) -> tuple[str, SearchPreferences]:
    display = _clean_name(name)
    loaded = _read_profile(_profile_path(preferences_path, display))
    if loaded is None:
        raise PreferencesError(f"Perfil '{display}' não encontrado.")
    return loaded
