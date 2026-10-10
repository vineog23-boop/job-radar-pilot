"""Nome da empresa: limpa o que os portais colocam no lugar dele e acha o nome em outro lugar.

Portais trazem slogan ("VENHA SER #SANGUELARANJA"), prefixo de marketing ("Carreiras X",
"Vagas na X", "Logo Programa de Estágio X 2027") ou nada. Empresa errada atrapalha a
deduplicação entre portais (que compara empresa + cargo) e o filtro de anúncios anônimos.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

# Emojis, pictogramas e símbolos decorativos.
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D\U00002B00-\U00002BFF]"
)
_HASHTAG = re.compile(r"#\w+")
# Trechos que dizem "venha trabalhar aqui", não quem é a empresa.
_NOISE = re.compile(
    r"(?i)^\s*(logo\s+)?(programa\s+de\s+(est[aá]gio|trainee)\s*(\|\s*)?)|"
    r"^\s*(carreiras|vagas?)(\s+(na|no|da|do|de))?\s+|"
    r"\s+carreiras\s*$|"
    r"\s*\|?\s*trabalhe\s+conosco\s*$|"
    r"\s+20\d\d\s*$"
)
# "Somos X", "Venha ser X": só é slogan quando veio decorado (emoji/hashtag). Sem isso pode
# ser o nome real da empresa ("Somos Educação").
_SLOGAN_PREFIX = re.compile(r"(?i)^\s*(somos|venha\s+ser|fa[cç]a\s+parte\s+(da|do|de))\s+")
_MIN_LETTERS = 2

# ATS cujo endereço identifica a empresa: subdomínio ou primeiro trecho do caminho.
_ATS_SUBDOMAIN = re.compile(
    r"^(?P<slug>[a-z0-9-]+)\.(gupy\.io|inhire\.app|recruitee\.com|teamtailor\.com|"
    r"breezy\.hr|bamboohr\.com|pandape\.infojobs\.com\.br)$"
)
_ATS_PATH = {
    "jobs.lever.co": 0,
    "boards.greenhouse.io": 0,
    "job-boards.greenhouse.io": 0,
    "jobs.ashbyhq.com": 0,
    "jobs.smartrecruiters.com": 0,
    "apply.workable.com": 0,
    "jobs.quickin.io": 0,
}
_NOT_A_COMPANY = {"portal", "www", "jobs", "careers", "app", "vagas", "job", "apply"}


def clean_company(name: str | None) -> str | None:
    """Tira emoji, hashtag e frases de marketing. ``None`` se não sobrar um nome."""

    if not name:
        return None
    decorated = bool(_EMOJI.search(name) or _HASHTAG.search(name))
    text = _EMOJI.sub(" ", name)
    text = _HASHTAG.sub(" ", text)
    if decorated:
        text = _SLOGAN_PREFIX.sub(" ", text)
    previous = None
    while previous != text:   # "Logo Programa de Estágio X 2027": várias camadas
        previous = text
        text = _NOISE.sub(" ", text).strip(" |-–—:·")
    text = " ".join(text.split())
    if sum(ch.isalpha() for ch in text) < _MIN_LETTERS:
        return None
    # Sobrou só o slogan ("VENHA SER #SANGUELARANJA" -> "VENHA SER" já removido acima).
    if decorated and re.fullmatch(r"(?i)(venha|seja|vem)(\s+\w+)?", text):
        return None
    return text[:120]


def _slug_name(slug: str) -> str | None:
    slug = re.sub(r"-\d+$", "", slug.strip().lower())
    if not slug or slug in _NOT_A_COMPANY:
        return None
    return " ".join(part.capitalize() for part in re.split(r"[-_]+", slug) if part) or None


def company_from_ats_url(url: str | None) -> str | None:
    """Empresa pelo endereço do ATS (``fcamara.gupy.io`` -> "Fcamara")."""

    if not url:
        return None
    parts = urlsplit(url)
    host = parts.netloc.lower().split(":")[0]
    match = _ATS_SUBDOMAIN.match(host)
    if match:
        return _slug_name(match.group("slug"))
    if host in _ATS_PATH:
        segments = [segment for segment in parts.path.split("/") if segment]
        index = _ATS_PATH[host]
        if len(segments) > index:
            return _slug_name(segments[index])
    return None


def company_from_title(title: str | None, pattern: str | None) -> str | None:
    """Empresa pelo título (portais de programa: "Ingredion abre Programa de Estágio...")."""

    if not title or not pattern:
        return None
    try:
        match = re.search(pattern, title)
    except re.error:
        return None
    if not match:
        return None
    for group in match.groups():
        if group:
            return clean_company(group)
    return None
