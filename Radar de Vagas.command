#!/bin/bash
# Execute este arquivo na raiz do workspace; requer Python 3.13.
set -euo pipefail

workspace_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$workspace_root"
python="$workspace_root/job-radar-pilot/.venv/bin/python"
data_root="${LOCALAPPDATA:+$LOCALAPPDATA/JobRadar}"
data_root="${data_root:-$HOME/Library/Application Support/JobRadar}"
mkdir -p "$data_root/logs"
log="$data_root/logs/interface.log"
fail() { echo "Falha: $* (log: $log)" | tee -a "$log" >&2; exit 1; }
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Abrindo Radar em $workspace_root" | tee -a "$log"

if [[ ! -x "$python" ]]; then
    echo "Primeira execução: preparando Python 3.13 e dependências..." | tee -a "$log"
    /bin/bash "$workspace_root/scripts/setup-mac.sh" 2>&1 | tee -a "$log"
fi
"$python" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 13) else 1)' || fail "A venv precisa usar Python 3.13."
"$python" -c 'import importlib.metadata as m; assert m.version("scrapling") == "0.4.15"' || fail "Execute scripts/setup-mac.sh para instalar Scrapling 0.4.15."
export PYTHONPATH="$workspace_root/job-radar-pilot/src${PYTHONPATH:+:$PYTHONPATH}"

# Não encerra processos. Confere PID, venv e código do painel já aberto.
if "$python" - <<'PY'
import socket
with socket.socket() as sock:
    sock.settimeout(1)
    raise SystemExit(0 if sock.connect_ex(("127.0.0.1", 8765)) == 0 else 1)
PY
then
    pids="$(lsof -nP -iTCP:8765 -sTCP:LISTEN -t 2>/dev/null || true)"
    identity="$(curl --noproxy '*' --fail --silent --max-time 2 http://127.0.0.1:8765/api/instance || true)"
    if ! "$python" - "$workspace_root" "$pids" "$identity" <<'PYTHON'
import json
from pathlib import Path
import sys

try:
    root = Path(sys.argv[1]) / "job-radar-pilot"
    pids = {int(pid) for pid in sys.argv[2].split()}
    instance = json.loads(sys.argv[3])
    matches = (
        pids == {instance["pid"]}
        and Path(instance["venv"]).resolve() == (root / ".venv").resolve()
        and Path(instance["project_root"]).resolve() == root.resolve()
    )
except (ValueError, KeyError, TypeError, OSError):
    matches = False
raise SystemExit(0 if matches else 1)
PYTHON
    then
        fail "Porta 8765 ocupada por outro processo; feche-o ou use outra porta pela CLI."
    fi
    echo "O painel deste workspace já está aberto." | tee -a "$log"
    open "http://127.0.0.1:8765/"
    exit 0
fi

echo "Painel: http://127.0.0.1:8765/ — Ctrl+C encerra. Log: $log" | tee -a "$log"
"$python" -u -m job_radar.webapp 2>&1 | tee -a "$log"
