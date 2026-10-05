"""Script avulso: exporta em XLSX só as vagas READY/CONDITIONAL confirmadas
LINK:LIVE (checadas de novo, agora, por link_check.verify_output).

Uso: python scripts/exportar_verificadas.py [saida.xlsx]
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from job_radar.fit import fit_state  # noqa: E402
from job_radar.reclassify import read_payloads  # noqa: E402
from job_radar.xlsx_export import build_jobs_xlsx  # noqa: E402


def main() -> int:
    output_dir = PROJECT / "output"
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT / "output" / "vagas-verificadas-live.xlsx"

    payloads = read_payloads(output_dir)
    selected = [
        job
        for job in payloads
        if fit_state(job.get("match_labels") or ()) in {"READY", "CONDITIONAL"}
        and "LINK:LIVE" in (job.get("match_labels") or ())
    ]
    if not selected:
        print("Nenhuma vaga READY/CONDITIONAL com LINK:LIVE encontrada.", file=sys.stderr)
        return 1

    data = build_jobs_xlsx(selected, tracking={})
    destino.write_bytes(data)
    print(f"OK: {len(selected)} vagas exportadas para {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
