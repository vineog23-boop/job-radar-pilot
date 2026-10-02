from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import re
import unicodedata


_UNIT_DELTAS = {
    "minuto": timedelta(minutes=1),
    "hora": timedelta(hours=1),
    "dia": timedelta(days=1),
    "semana": timedelta(weeks=1),
    "mes": timedelta(days=30),
}
_UNIT_ALIASES = {
    "minute": "minuto",
    "hour": "hora",
    "day": "dia",
    "week": "semana",
    "month": "mes",
    "meses": "mes",
}
_RELATIVE = re.compile(
    r"(?<!\w)(?:ha\s+)?(?P<amount>\d{1,3})\s*"
    r"(?P<unit>minutos?|horas?|dias?|semanas?|meses|mes|minutes?|hours?|days?|weeks?|months?)"
    r"(?:\s+ago)?(?!\w)"
)
_MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
_LONG_DATE = re.compile(
    r"(?<!\d)(\d{1,2})\s+de\s+(" + "|".join(_MONTHS) + r")\s+de\s+(\d{4})(?!\d)"
)
_BRAZILIAN_DATE = re.compile(r"(?<!\d)(\d{2})/(\d{2})/(\d{4})(?!\d)")


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        "".join(char for char in decomposed if not unicodedata.combining(char)).split()
    )


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def parse_published_at(value: str | None, *, now: datetime | None = None) -> str | None:
    """Converte data absoluta ou relativa do portal em ISO 8601 UTC; sem evidência, None."""
    if not value or not value.strip():
        return None
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    text = _fold(value)

    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return _iso(parsed) if parsed <= current else None

    brazilian = _BRAZILIAN_DATE.search(text)
    if brazilian is not None:
        day, month, year = (int(part) for part in brazilian.groups())
        try:
            parsed = datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None
        return _iso(parsed) if parsed <= current else None

    long_date = _LONG_DATE.search(text)
    if long_date is not None:
        day, month_name, year = long_date.groups()
        try:
            parsed = datetime(int(year), _MONTHS[month_name], int(day), tzinfo=timezone.utc)
        except ValueError:
            return None
        return _iso(parsed) if parsed <= current else None

    relative = _RELATIVE.search(text)
    if relative is not None:
        unit = relative.group("unit")
        singular = unit if unit in _UNIT_DELTAS else _UNIT_ALIASES.get(unit, unit.removesuffix("s"))
        singular = _UNIT_ALIASES.get(singular, singular)
        delta = _UNIT_DELTAS.get(singular)
        amount = int(relative.group("amount"))
        if delta is None or amount == 0:
            return None
        return _iso(current - delta * amount)

    if re.search(r"(?<!\w)hoje(?!\w)", text):
        return _iso(current)
    if re.search(r"(?<!\w)ontem(?!\w)", text):
        return _iso(current - timedelta(days=1))
    return None


def parse_iso_datetime(value: object) -> datetime | None:
    """Data ISO 8601 gravada no JSONL; sem fuso vira UTC. Inválida -> None."""

    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


_SAO_PAULO = timezone(timedelta(hours=-3), "America/Sao_Paulo")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_deadline(value: str | None) -> str | None:
    """Prazo de candidatura em ISO 8601 UTC. Só data vale até 23:59:59 de Brasília."""

    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if _DATE_ONLY.match(text):
            day = datetime.fromisoformat(text).date()
            moment = datetime.combine(day, time(23, 59, 59), tzinfo=_SAO_PAULO)
        else:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=_SAO_PAULO)
    except ValueError:
        return None
    return moment.astimezone(timezone.utc).isoformat()


def is_stale(
    published_at: str | None, max_age_days: int | None, now: datetime
) -> bool:
    """True só quando há data de publicação comprovada fora da janela."""

    published = parse_iso_datetime(published_at)
    if published is None or max_age_days is None:
        return False
    return published < now - timedelta(days=max_age_days)


def is_expired(application_deadline: str | None, now: datetime) -> bool:
    deadline = parse_iso_datetime(application_deadline)
    return deadline is not None and deadline < now
