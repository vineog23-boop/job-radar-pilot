"""Exportação automática ao fim de cada coleta.

Depois de toda busca (pelo painel ou pela coleta agendada), o Radar deixa as
vagas prontas numa pasta do usuário (padrão: Documentos\\Radar de Vagas):

- ``melhores-vagas-AAAA-MM-DD-HHMM.xlsx``: "Mais compatível" + "A revisar",
  sem as descartadas, ordenadas pelo Score;
- ``todas-de-ti-AAAA-MM-DD-HHMM.csv``: todas as vagas de tecnologia;
- ``ultima-busca.xlsx``: cópia da planilha mais recente (nome fixo).

Os arquivos ficam fora do repositório; nada é apagado da pasta.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Mapping

SETTINGS_NAME = "auto-export.json"
LATEST_NAME = "ultima-busca.xlsx"
_MAX_FOLDER_LENGTH = 400


def default_folder() -> Path:
    override = os.environ.get("JOB_RADAR_EXPORT_DIR")
    if override:
        return Path(override)
    return Path.home() / "Documents" / "Radar de Vagas"


@dataclass(frozen=True, slots=True)
class AutoExportSettings:
    enabled: bool = True
    folder: Path | None = None

    @property
    def resolved_folder(self) -> Path:
        return self.folder or default_folder()

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "folder": str(self.resolved_folder)}


def settings_from_dict(payload: Mapping[str, Any]) -> AutoExportSettings:
    if not isinstance(payload, Mapping):
        raise ValueError("Configuração de exportação deve ser um objeto JSON.")
    enabled = payload.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("enabled deve ser verdadeiro ou falso.")
    raw_folder = payload.get("folder")
    folder: Path | None = None
    if raw_folder not in (None, ""):
        if not isinstance(raw_folder, str) or len(raw_folder) > _MAX_FOLDER_LENGTH:
            raise ValueError("Pasta de exportação inválida.")
        folder = Path(raw_folder.strip())
        if not folder.is_absolute():
            raise ValueError("Use o caminho completo da pasta (ex.: C:\\Users\\voce\\Documents\\Vagas).")
    return AutoExportSettings(enabled=enabled, folder=folder)


def settings_path(preferences_path: Path) -> Path:
    return preferences_path.parent / SETTINGS_NAME


def load_settings(preferences_path: Path) -> AutoExportSettings:
    """Configuração salva; ausente ou inválida volta ao padrão (ligada, Documentos)."""

    try:
        payload = json.loads(settings_path(preferences_path).read_text(encoding="utf-8"))
        settings = settings_from_dict(payload)
    except (OSError, ValueError):
        settings = AutoExportSettings()
    return AutoExportSettings(enabled=settings.enabled, folder=settings.resolved_folder)


def save_settings(preferences_path: Path, settings: AutoExportSettings) -> None:
    from job_radar.cleanup import replace_atomically

    path = settings_path(preferences_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"enabled": settings.enabled, "folder": str(settings.folder) if settings.folder else None}
    replace_atomically(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _write_bytes(target: Path, content: bytes) -> None:
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def export_after_collection(
    output_dir: Path,
    settings: AutoExportSettings,
    tracking: Mapping[str, Mapping[str, str]],
    *,
    now: datetime | None = None,
) -> list[Path]:
    """Grava as planilhas da última coleta; devolve os arquivos escritos."""

    if not settings.enabled:
        return []
    from job_radar.fit import fit_reasons
    from job_radar.webapp import (
        build_jobs_csv,
        describe_export_filters,
        filter_jobs_for_export,
        load_output,
    )
    from job_radar.xlsx_export import build_jobs_xlsx

    output = load_output(output_dir)
    if output["read_error"]:
        raise ValueError(f"Não foi possível ler as vagas: {output['read_error']}")
    tracked = dict(tracking)
    all_it = filter_jobs_for_export(output["jobs"], match="", tracked="active", tracking=tracked)
    if not all_it:
        return []
    best = filter_jobs_for_export(all_it, match="fit", tracking=tracked)

    moment = now or datetime.now().astimezone()
    stamp = moment.strftime("%Y-%m-%d-%H%M")
    folder = settings.resolved_folder
    folder.mkdir(parents=True, exist_ok=True)
    workbook = build_jobs_xlsx(
        best,
        tracked,
        filters=describe_export_filters(match="fit", tracked="active"),
        reasons_for=fit_reasons,
        now=moment,
    )
    best_path = folder / f"melhores-vagas-{stamp}.xlsx"
    csv_path = folder / f"todas-de-ti-{stamp}.csv"
    latest_path = folder / LATEST_NAME
    _write_bytes(best_path, workbook)
    _write_bytes(csv_path, build_jobs_csv(all_it, tracked))
    _write_bytes(latest_path, workbook)
    return [best_path, csv_path, latest_path]
