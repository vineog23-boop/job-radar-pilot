"""Raiz compartilhada de dados locais, fora do repositório."""
from __future__ import annotations

import os
from pathlib import Path
import sys


def user_data_dir() -> Path:
    """Preserva LOCALAPPDATA explícito; senão usa o padrão do sistema."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "JobRadar"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "JobRadar"
    if sys.platform == "win32":
        return Path.home() / "AppData" / "Local" / "JobRadar"
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else Path.home() / ".local" / "share") / "job-radar"
