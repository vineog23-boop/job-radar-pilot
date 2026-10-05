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
from job_radar.models import CollectionStatus, SourceRunResult, VacancyRecord

NEW_LABEL = "STATUS:NEW"
_MAX_ENTRIES = 200_000
# Contagens por fonte: guarda as últimas coletas válidas e exige um mínimo antes
# de comparar, para uma única coleta atípica não virar referência.
_MAX_COUNTS_PER_SOURCE = 10
_MIN_PREVIOUS_COUNTS = 2
_DROP_RATIO = 0.5
_COUNTABLE_STATUSES = {
    CollectionStatus.SUCCESS,
    CollectionStatus.PARTIAL,
    CollectionStatus.EMPTY,
}


def history_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return root / "JobRadar" / "history.json"


class SeenHistory:
    """Guarda apenas chave de identidade e data da primeira observação."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or history_path()

    def _read_document(self) -> dict[str, object]:
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError:
            return {}
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if not isinstance(data, dict):
            self._preserve_corrupt()
            return {}
        return data

    def _preserve_corrupt(self) -> None:
        """Guarda o histórico ilegível ao lado antes de a próxima gravação o trocar."""

        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        copy = self._path.with_name(f"{self._path.stem}.corrompido-{stamp}{self._path.suffix}")
        try:
            os.replace(self._path, copy)
        except OSError:
            pass

    def _load(self) -> dict[str, str]:
        seen = self._read_document().get("seen")
        if not isinstance(seen, dict):
            return {}
        return {
            str(key): str(value)
            for key, value in seen.items()
            if isinstance(key, str) and isinstance(value, str)
        }

    def _load_source_counts(self) -> dict[str, list[int]]:
        counts = self._read_document().get("source_counts")
        if not isinstance(counts, dict):
            return {}
        return {
            str(code): [value for value in values if isinstance(value, int) and value >= 0]
            for code, values in counts.items()
            if isinstance(values, list)
        }

    def _save(
        self,
        seen: dict[str, str] | None = None,
        source_counts: dict[str, list[int]] | None = None,
    ) -> None:
        if seen is None:
            seen = self._load()
        if source_counts is None:
            source_counts = self._load_source_counts()
        if len(seen) > _MAX_ENTRIES:
            ordered = sorted(seen.items(), key=lambda item: item[1])
            seen = dict(ordered[-_MAX_ENTRIES:])
        self._write({"version": 1, "seen": seen, "source_counts": source_counts})

    def _write(self, document: dict[str, object]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            handle, temp_name = tempfile.mkstemp(
                dir=self._path.parent, prefix="history-", suffix=".tmp"
            )
        except OSError:
            return
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(document, stream, ensure_ascii=False)
            os.replace(temp_name, self._path)
        except OSError:
            try:
                os.unlink(temp_name)
            except OSError:
                pass

    def check_source_counts(
        self, results: Iterable[SourceRunResult]
    ) -> dict[str, str]:
        """Compara a contagem de cada fonte com a média das coletas anteriores.

        Avisa quando a fonte cai mais de 50% ou zera; depois registra a
        contagem atual (somente de coletas que terminaram sem erro/bloqueio).
        """

        counts = self._load_source_counts()
        warnings: dict[str, str] = {}
        for result in results:
            current = len(result.records)
            previous = counts.get(result.source_code, [])
            if len(previous) >= _MIN_PREVIOUS_COUNTS:
                average = sum(previous) / len(previous)
                if average > 0 and current == 0:
                    warnings[result.source_code] = f"SOURCE_COUNT_ZERO:0<{average:.0f}"
                elif current < average * _DROP_RATIO:
                    warnings[result.source_code] = (
                        f"SOURCE_COUNT_DROP:{current}<{average:.0f}"
                    )
            if result.status in _COUNTABLE_STATUSES:
                counts[result.source_code] = [*previous, current][-_MAX_COUNTS_PER_SOURCE:]
        self._save(source_counts=counts)
        return warnings

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
            self._save(seen=seen)
        return tuple(result)
