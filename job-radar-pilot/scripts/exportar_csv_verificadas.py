"""Gera um CSV pequeno (texto puro) com as vagas READY/CONDITIONAL + LINK:LIVE,
para subir ao Google Drive sem depender de base64 (planilha binaria grande)."""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from job_radar.fit import fit_state, job_technologies  # noqa: E402
from job_radar.reclassify import read_payloads  # noqa: E402

WORKPLACE_NAMES = {"REMOTE": "Remoto", "HYBRID": "Hibrido", "ONSITE": "Presencial", "UNKNOWN": "A confirmar"}
LEVEL_NAMES = {"estagio": "Estagio", "junior": "Junior", "pleno": "Pleno", "senior": "Senior"}


def main() -> int:
    output_dir = PROJECT / "output"
    only_ready = "--ready-only" in sys.argv
    positional = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    destino = Path(positional[0]) if positional else PROJECT / "output" / "vagas-verificadas-live.csv"

    wanted_fits = {"READY"} if only_ready else {"READY", "CONDITIONAL"}
    payloads = read_payloads(output_dir)
    selected = [
        job
        for job in payloads
        if fit_state(job.get("match_labels") or ()) in wanted_fits
        and "LINK:LIVE" in (job.get("match_labels") or ())
    ]
    selected.sort(key=lambda job: str(job.get("published_at") or ""), reverse=True)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Aderencia", "Empresa", "Cargo", "Nivel", "Modalidade",
        "Publicada em", "Portal", "Link",
    ])
    for job in selected:
        fit = fit_state(job.get("match_labels") or ())
        seniority = str(job.get("seniority") or "")
        writer.writerow([
            "Melhor" if fit == "READY" else "Boa",
            job.get("company") or "Nao informada",
            job.get("title") or "",
            LEVEL_NAMES.get(seniority, seniority),
            WORKPLACE_NAMES.get(str(job.get("workplace_model") or "UNKNOWN"), ""),
            (job.get("published_at") or "")[:10],
            job.get("source") or "",
            job.get("canonical_url") or "",
        ])

    destino.write_text(buffer.getvalue(), encoding="utf-8", newline="")
    print(f"OK: {len(selected)} vagas em {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
