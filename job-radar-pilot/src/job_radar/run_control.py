"""Pausar, retomar e parar uma coleta em andamento.

A coleta roda em outro processo (``job-radar collect``); o painel conversa com
ela por um arquivo de controle pequeno, com uma palavra: ``pause`` ou ``stop``.
Sem arquivo (ou vazio), a coleta segue normalmente.

- **Pausa**: cada requisição espera antes de sair (ver ``FetchPolicy._throttle``),
  então a coleta congela depois da página atual e continua de onde parou.
- **Parar**: a coleta termina a consulta atual, não começa outra e grava o que
  já encontrou. Portais que nem começaram mantêm as vagas da coleta anterior.
"""

from __future__ import annotations

from pathlib import Path
import time
from typing import Callable

STATE_RUN = "run"
STATE_PAUSE = "pause"
STATE_STOP = "stop"
CONTROL_FILE_NAME = ".radar-control"
STOP_REASON = "STOPPED_BY_USER"


class RunControl:
    """Lê o arquivo de controle; sem caminho, nunca pausa nem para."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        poll_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._path = path
        self._poll_seconds = poll_seconds
        self._sleep = sleep
        self.was_paused = False

    @property
    def path(self) -> Path | None:
        return self._path

    def state(self) -> str:
        if self._path is None:
            return STATE_RUN
        try:
            word = self._path.read_text(encoding="utf-8").strip().casefold()
        except OSError:
            return STATE_RUN
        return word if word in {STATE_PAUSE, STATE_STOP} else STATE_RUN

    def wait_if_paused(self) -> None:
        """Bloqueia enquanto estiver pausado (sai se pedirem para parar)."""

        while self.state() == STATE_PAUSE:
            self.was_paused = True
            self._sleep(self._poll_seconds)

    def should_stop(self) -> bool:
        self.wait_if_paused()
        return self.state() == STATE_STOP


_NO_CONTROL = RunControl()
_active: RunControl = _NO_CONTROL


def activate(control: RunControl | None) -> None:
    """Define o controle da coleta deste processo (None desliga)."""

    global _active
    _active = control or _NO_CONTROL


def current() -> RunControl:
    return _active


def write_state(path: Path, state: str) -> None:
    """Usado pelo painel: grava ``pause``/``stop`` ou apaga (``run``)."""

    if state == STATE_RUN:
        path.unlink(missing_ok=True)
        return
    if state not in {STATE_PAUSE, STATE_STOP}:
        raise ValueError(f"Estado de controle invalido: {state}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(state, encoding="utf-8")
    temporary.replace(path)
