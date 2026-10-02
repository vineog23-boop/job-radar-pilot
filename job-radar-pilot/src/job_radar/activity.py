"""Situação da vaga (ativa, encerrada ou não comprovada), derivada dos dados salvos.

Nada é gravado: a situação é recalculada a cada leitura para que um registro
preservado de uma coleta antiga não continue "ativo" por inércia.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping

from job_radar.dates import parse_iso_datetime

ACTIVE_CONFIRMED = "ACTIVE_CONFIRMED"  # prazo oficial ainda aberto
ACTIVE_LISTED = "ACTIVE_LISTED"  # apareceu na listagem de uma coleta recente
CLOSED = "CLOSED"  # prazo vencido
UNKNOWN = "UNKNOWN"  # sem evidência suficiente

# Passada essa idade, a última observação não prova mais que a vaga segue no ar.
LISTING_FRESH_DAYS = 7


def activity_state(job: Mapping[str, Any], now: datetime) -> str:
    published = parse_iso_datetime(job.get("published_at"))
    deadline = parse_iso_datetime(job.get("application_deadline"))
    if deadline is not None and deadline < now:
        return CLOSED
    if published is None or published > now:
        return UNKNOWN
    if deadline is not None:
        return ACTIVE_CONFIRMED
    observed = parse_iso_datetime(job.get("observed_at"))
    if observed is not None and now - observed <= timedelta(days=LISTING_FRESH_DAYS):
        return ACTIVE_LISTED
    return UNKNOWN
