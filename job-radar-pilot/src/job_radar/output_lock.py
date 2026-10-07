"""Trava da pasta de saída compartilhada entre processos.

A coleta (do painel ou do Agendador do Windows) e as ações do painel que
regravam ``vagas.jsonl`` (reaplicar perfil, limpar, desfazer, importar) rodam
em processos diferentes. Cada uma lê o arquivo, muda e grava de volta; sem uma
trava, quem grava por último apaga o trabalho do outro ("atualização perdida").

A trava é do sistema operacional (``msvcrt`` no Windows, ``flock`` no resto):
se o processo morrer, o próprio sistema a solta, então não sobra trava presa.
"""

from __future__ import annotations

import errno
import os
import time
from pathlib import Path
from typing import Any

LOCK_FILE_NAME = ".radar-output.lock"
BUSY_MESSAGE = (
    "Outra coleta esta em andamento (talvez a agendada). "
    "Espere ela terminar e tente de novo."
)


class OutputBusyError(RuntimeError):
    """Outro processo está gravando a pasta de saída."""


def _lock(handle: Any) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:  # pragma: no cover - a aplicacao principal roda no Windows
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle: Any) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:  # pragma: no cover - a aplicacao principal roda no Windows
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class OutputLock:
    """``with OutputLock(pasta):`` — exclusiva e sem espera (falha na hora)."""

    def __init__(self, output_dir: Path) -> None:
        self._path = output_dir / LOCK_FILE_NAME
        self._file: Any | None = None

    def __enter__(self) -> "OutputLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            _lock(handle)
        except OSError as error:
            handle.close()
            raise OutputBusyError(BUSY_MESSAGE) from error
        self._file = handle
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._file is None:
            return
        try:
            self._file.seek(0)
            _unlock(self._file)
        finally:
            self._file.close()
            self._file = None


def is_output_locked(output_dir: Path) -> bool:
    """True se outro processo segura a trava agora (só consulta, não segura)."""

    if not (output_dir / LOCK_FILE_NAME).exists():
        return False
    try:
        with OutputLock(output_dir):
            return False
    except OutputBusyError:
        return True


class FileLock:
    """Serializa leitura-modificação-gravação de um arquivo, com espera.

    A trava usa um arquivo auxiliar estável: substituir o JSON atomicamente
    não troca o arquivo que o sistema operacional está travando.
    """

    def __init__(self, path: Path) -> None:
        self._path = path.with_name(path.name + ".lock")
        self._file: Any | None = None

    def __enter__(self) -> "FileLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            while True:
                handle.seek(0)
                try:
                    _lock(handle)
                    break
                except OSError as error:
                    if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise
                    time.sleep(0.02)
        except BaseException:
            handle.close()
            raise
        self._file = handle
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._file is None:
            return
        try:
            self._file.seek(0)
            _unlock(self._file)
        finally:
            self._file.close()
            self._file = None
