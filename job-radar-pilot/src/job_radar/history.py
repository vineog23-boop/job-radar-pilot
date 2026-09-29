"""Histórico local de vagas já vistas (first_seen) para destacar novidades."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable

from job_radar.identity import identity_key
from job_radar.models import VacancyRecord

NEW_LABEL = "STATUS:NEW"
_MAX_ENTRIES = 200_000


def history_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return root / "JobRadar" / "history.json"


class SeenHistory:
    """Guarda apenas chave de identidade e data da primeira observação."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or history_path()

    def _load(self) -> dict[str, str]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        seen = data.get("seen") if isinstance(data, dict) else None
        if not isinstance(seen, dict):
            return {}
        return {
            str(key): str(value)
            for key, value in seen.items()
            if isinstance(key, str) and isinstance(value, str)
        }

    def _save(self, seen: dict[str, str]) -> None:
        if len(seen) > _MAX_ENTRIES:
            ordered = sorted(seen.items(), key=lambda item: item[1])
            seen = dict(ordered[-_MAX_ENTRIES:])
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(
            dir=self._path.parent, prefix="history-", suffix=".tmp"
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump({"version": 1, "seen": seen}, stream, ensure_ascii=False)
            os.replace(temp_name, self._path)
        except OSError:
            try:
                os.unlink(temp_name)
            except OSError:
                pass

    @staticmethod
    def _key(record: VacancyRecord) -> str:
        source, ident = identity_key(record)
        return f"{source}|{ident}"

    def annotate(
        self, records: Iterable[VacancyRecord], now: datetime
    ) -> tuple[VacancyRecord, ...]:
        """Marca vagas inéditas com STATUS:NEW e grava o histórico.

        Na primeira execução (histórico vazio) nada é marcado como novo, para
        não rotular a base inteira.
        """

        items = tuple(records)
        seen = self._load()
        first_run = not seen
        stamp = now.isoformat()
        result: list[VacancyRecord] = []
        for record in items:
            key = self._key(record)
            if key in seen:
                result.append(record)
                continue
            seen[key] = stamp
            if first_run:
                result.append(record)
            else:
                result.append(
                    replace(
                        record,
                        match_labels=tuple(
                            dict.fromkeys((*record.match_labels, NEW_LABEL))
                        ),
                    )
                )
        if items:
            self._save(seen)
        return tuple(result)
