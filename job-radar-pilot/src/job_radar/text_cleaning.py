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


# Códigos internos do portal: "[Job-32006] Dev", "Técnica - 386089", "Dev (Cód. 123)".
_LEADING_CODE = re.compile(r"^\[[^\]]*\d[^\]]*\]\s*")
_TRAILING_CODE = re.compile(
    r"(?:\s+-\s*\d{4,}|\s*\((?:c[oó]d(?:igo)?|ref)\.?\s*[\w-]+\))$", re.IGNORECASE
)


def clean_title(value: str | None) -> str | None:
    """Remove ruído de exibição do título sem perder informação de senioridade."""
    if value is None:
        return None
    title = " ".join(value.split())
    if not title:
        return None
    title = _TRAILING_CODE.sub("", _LEADING_CODE.sub("", title)).strip() or title

    if _LEADING_BADGE.match(title) and not _PLACE_AFTER_BADGE.match(title):
        title = _LEADING_BADGE.sub("", title, count=1)
    if _TRAILING_BADGE.search(title):
        title = _TRAILING_BADGE.sub("", title, count=1)

    head, separator, tail = title.partition("|")
    if separator and head.strip() and not _SENIORITY_HINT.search(_fold(tail)):
        title = head.strip()
    return title or None


# Começos de célula que o Excel/LibreOffice interpretam como fórmula.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def spreadsheet_safe(value):
    """Neutraliza fórmula em célula de CSV (OWASP "CSV injection").

    Títulos e empresas vêm dos portais: um "=HYPERLINK(...)" viraria link ativo
    ao abrir o CSV no Excel. Com o apóstrofo na frente, a célula é só texto.
    Valores que não são texto passam intactos.
    """

    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


# Código de página que vaza quando o portal põe <script>/<style> dentro do
# cartão: do primeiro sinal em diante, o resto é código, não vaga.
_PAGE_CODE = re.compile(
    r"\(\s*function\s*\(|\(\s*adsbygoogle|window\.\w+\s*=|document\.addEventListener"
    r"|\.[\w-]+\s*\{[^}]*:[^}]*\}"
)
# Botões e caixas de compartilhar que viram texto do cartão.
_SHARE_BOX = re.compile(
    r"(?:compartilhar vaga\s*)?que tal compartilhar esta vaga\?"
    r"(?:\s*(?:email|e-mail|whatsapp|linkedin|facebook|x \(twitter\)|twitter|copiar link))*"
    r"|compartilhar vaga",
    re.IGNORECASE,
)
_UI_PHRASES = re.compile(r"(?<!\w)(?:quero essa vaga|salvar vaga)(?!\w)", re.IGNORECASE)
# Primeira Vaga Tech: "Voltar B Engenheiro..." (link de voltar + inicial do logo).
# A letra do logo nem sempre vem (logo em imagem); "QA ..." não é logo.
_BACK_LINK = re.compile(r"^(?i:voltar)\s+(?:[A-Z0-9]\s+(?=\S))?")
# Alguns agregadores (ex.: PrimeiraVagaTech) colam ao final um bloco gerado por
# IA ("Dica 1 ... Dica 2 ... palavras de alto CPC") e um botão de call-to-action.
# Nenhum dos dois é conteúdo real da vaga; cortar a partir do primeiro sinal.
_AI_TIPS_SECTION = re.compile(r"\bdicas?\s+importantes\b.*$", re.IGNORECASE | re.DOTALL)
_CTA_SECTION = re.compile(r"\bpronto para (?:este|esse) desafio\??.*$", re.IGNORECASE | re.DOTALL)


def clean_description(value: str | None) -> str | None:
    """Descrição sem código de página, botões e restos de navegação do portal."""

    if value is None:
        return None
    text = " ".join(value.split())
    code = _PAGE_CODE.search(text)
    if code is not None:
        text = text[: code.start()]
    text = _BACK_LINK.sub("", text)
    text = _SHARE_BOX.sub(" ", text)
    text = _UI_PHRASES.sub(" ", text)
    text = _AI_TIPS_SECTION.sub("", text)
    text = _CTA_SECTION.sub("", text)
    text = " ".join(text.split())
    return text or None
