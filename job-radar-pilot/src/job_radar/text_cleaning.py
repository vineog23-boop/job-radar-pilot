from __future__ import annotations

import re
import unicodedata


# Selos de destaque que alguns portais colam no texto do título ("Nova", "Novo").
_BADGE = r"(?:nova|novo)"
_LEADING_BADGE = re.compile(rf"^{_BADGE}\s+(?=\S)", re.IGNORECASE)
_TRAILING_BADGE = re.compile(rf"(?<=\S)\s+{_BADGE}$", re.IGNORECASE)
# "Nova Scotia", "Novo Mundo": o selo só vale se o resto continuar sendo um cargo.
_PLACE_AFTER_BADGE = re.compile(r"^nova\s+scotia\b", re.IGNORECASE)
_SENIORITY_HINT = re.compile(
    r"(?<!\w)(?:estagi\w*|intern(?:ship)?|trainee|aprendiz|junior|jr\.?|pleno|pl|"
    r"senior|sr\.?|iniciante|entry\s+level|nivel\s*(?:1|i))(?!\w)"
)


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def clean_title(value: str | None) -> str | None:
    """Remove ruído de exibição do título sem perder informação de senioridade."""
    if value is None:
        return None
    title = " ".join(value.split())
    if not title:
        return None

    if _LEADING_BADGE.match(title) and not _PLACE_AFTER_BADGE.match(title):
        title = _LEADING_BADGE.sub("", title, count=1)
    if _TRAILING_BADGE.search(title):
        title = _TRAILING_BADGE.sub("", title, count=1)

    head, separator, tail = title.partition("|")
    if separator and head.strip() and not _SENIORITY_HINT.search(_fold(tail)):
        title = head.strip()
    return title or None
