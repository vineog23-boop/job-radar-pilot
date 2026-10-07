"""Acompanhamento local das vagas (salva, aplicada, descartada).

Fica em %LOCALAPPDATA%\\JobRadar\\tracking.json, fora do repositório e do funil
canônico; guarda somente URL, estado, data e uma nota curta do usuário.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import datetime
import json
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Callable, Iterator
from urllib.parse import urlsplit

from job_radar.output_lock import FileLock


# Funil de candidatura, na ordem em que a pessoa avança.
TRACKING_STATUSES = ("SAVED", "APPLIED", "INTERVIEW", "OFFER", "REJECTED", "DISCARDED")
TRACKING_NAMES = {
    "SAVED": "Salva",
    "APPLIED": "Aplicada",
    "INTERVIEW": "Entrevista",
    "OFFER": "Oferta",
    "REJECTED": "Recusada",
    "DISCARDED": "Descartada",
}
# "Em processo": já se candidatou e ainda não teve resposta final.
IN_PROGRESS_STATUSES = ("APPLIED", "INTERVIEW", "OFFER")
_MAX_URL_LENGTH = 2048
_MAX_NOTE_LENGTH = 500


class TrackingError(ValueError):
    """Entrada ou arquivo de acompanhamento fora do contrato."""


def tracking_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return root / "JobRadar" / "tracking.json"


def _validated_url(url: object) -> str:
    if not isinstance(url, str) or not url or len(url) > _MAX_URL_LENGTH:
        raise TrackingError("URL da vaga invalida.")
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise TrackingError("URL da vaga invalida.") from exc
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise TrackingError("URL da vaga deve ser http(s).")
    return url


class TrackingStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or tracking_path()

    @contextmanager
    def transaction(self) -> Iterator["TrackingStore"]:
        """Mantém o snapshot final da coleta estável até sua publicação."""

        with ExitStack() as held:
            try:
                held.enter_context(FileLock(self._path))
            except OSError as exc:
                raise TrackingError(
                    f"Nao foi possivel travar o acompanhamento em {self._path}."
                ) from exc
            yield self

    def load(self) -> dict[str, dict[str, str]]:
        """Lê o arquivo inteiro ou recusa, sem filtrar/normalizar entradas.

        Cada chave é uma URL http(s) válida; a entrada é um objeto com status
        conhecido e todos os valores são texto. Datas e nota são opcionais.
        Qualquer violação impede o snapshot e toda reescrita do acompanhamento.
        """

        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TrackingError(
                f"Nao foi possivel ler o acompanhamento em {self._path}."
            ) from exc
        entries = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(entries, dict):
            raise TrackingError("Arquivo de acompanhamento com formato inesperado.")
        validated: dict[str, dict[str, str]] = {}
        for url, entry in entries.items():
            try:
                _validated_url(url)
            except TrackingError as exc:
                raise TrackingError("Arquivo de acompanhamento com URL invalida.") from exc
            if (
                not isinstance(entry, dict)
                or entry.get("status") not in TRACKING_STATUSES
                or any(not isinstance(value, str) for value in entry.values())
            ):
                raise TrackingError("Arquivo de acompanhamento com entrada invalida.")
            validated[url] = dict(entry)
        return validated

    def snapshot(self) -> tuple[dict[str, dict[str, str]], str]:
        """Conteúdo e versão pertencem à mesma leitura protegida."""
        with self.transaction():
            entries = self.load()
            content = json.dumps(entries, sort_keys=True, ensure_ascii=False).encode("utf-8")
            return entries, hashlib.sha256(content).hexdigest()

    def set_status(
        self,
        url: object,
        status: object,
        *,
        now: datetime,
        note: object = None,
        validate: Callable[[str], None] | None = None,
    ) -> dict[str, dict[str, str]]:
        canonical = _validated_url(url)
        if status is not None and status not in TRACKING_STATUSES:
            raise TrackingError(f"Estado aceita {', '.join(TRACKING_STATUSES)} ou vazio.")
        if note is not None and not isinstance(note, str):
            raise TrackingError("Nota deve ser texto.")
        cleaned_note = " ".join((note or "").split())
        if len(cleaned_note) > _MAX_NOTE_LENGTH:
            raise TrackingError(f"Nota excede {_MAX_NOTE_LENGTH} caracteres.")

        with self.transaction():
            entries = self.load()
            if validate is not None:
                validate(canonical)
            if status is None:
                entries.pop(canonical, None)
            else:
                previous = entries.get(canonical, {})
                # Datas de cada etapa já alcançada (applied_at, interview_at...) ficam.
                entry = {key: value for key, value in previous.items() if key.endswith("_at")}
                entry.update({"status": str(status), "updated_at": now.isoformat()})
                entry.setdefault(f"{str(status).lower()}_at", now.isoformat())
                # Sem nota no pedido (ex.: mudar o estado pelo painel), a nota antiga fica.
                kept_note = cleaned_note if note is not None else previous.get("note", "")
                if kept_note:
                    entry["note"] = kept_note
                entries[canonical] = entry
            self._write(entries)
            return entries

    def _write(self, entries: dict[str, dict[str, str]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(
            dir=self._path.parent, prefix="tracking-", suffix=".tmp"
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump({"version": 1, "jobs": entries}, stream, ensure_ascii=False)
            os.replace(temp_name, self._path)
        except OSError as exc:
            Path(temp_name).unlink(missing_ok=True)
            raise TrackingError(
                f"Nao foi possivel salvar o acompanhamento em {self._path}."
            ) from exc
