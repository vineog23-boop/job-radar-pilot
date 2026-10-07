"""Exportação em planilha .xlsx (sem dependências extras).

Gera uma planilha no formato de um acompanhamento de candidaturas: uma linha por
vaga, cabeçalho fixo, filtros automáticos, links clicáveis e cores para score,
modalidade e status. O .xlsx é só um zip com XML; escrevê-lo direto evita
depender do openpyxl na instalação de quem só quer usar o painel.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import io
import re
from typing import Any, Mapping, Sequence
from xml.sax.saxutils import escape, quoteattr
import zipfile

from job_radar.dates import parse_iso_datetime
from job_radar.fit import fit_state, job_technologies
from job_radar.tracking import TRACKING_NAMES

_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_LEVEL_NAMES = {
    "estagio": "Estágio",
    "junior": "Júnior",
    "pleno": "Pleno",
    "senior": "Sênior",
}
WORKPLACE_NAMES = {
    "REMOTE": "Remoto",
    "HYBRID": "Híbrido",
    "ONSITE": "Presencial",
    "UNKNOWN": "A confirmar",
}
_TRACKING_NAMES = TRACKING_NAMES

# Índices de estilo (ver _STYLES).
_S_HEADER, _S_TEXT, _S_CENTER, _S_LINK, _S_DATE = 1, 2, 3, 4, 5
_S_SCORE_HIGH, _S_SCORE_MID, _S_SCORE_LOW = 6, 7, 8
_S_GREEN, _S_YELLOW, _S_ORANGE, _S_BLUE, _S_GRAY = 9, 10, 11, 12, 13
_S_TITLE = 14

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/></numFmts>
<fonts count="4">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><u/><sz val="11"/><color rgb="FF0563C1"/><name val="Calibri"/></font>
<font><b/><sz val="14"/><name val="Calibri"/></font>
</fonts>
<fills count="8">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF1F3A5F"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFC6EFCE"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFEB9C"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFF8CBAD"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFDDEBF7"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE7E6E6"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFD0D0D0"/></left><right style="thin"><color rgb="FFD0D0D0"/></right><top style="thin"><color rgb="FFD0D0D0"/></top><bottom style="thin"><color rgb="FFD0D0D0"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="15">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment vertical="top"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>
<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>
<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>
<xf numFmtId="0" fontId="0" fillId="7" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>
<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="5" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="6" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="7" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

COLUMNS: tuple[tuple[str, float], ...] = (
    ("Empresa", 26),
    ("Cargo", 46),
    ("Nível", 13),
    ("Modalidade", 15),
    ("Localização", 26),
    ("Score", 8),
    ("Status", 15),
    ("Publicada em", 13),
    ("Link da Vaga", 44),
    ("Tecnologias", 30),
    ("Portal", 16),
    ("Observações", 38),
)


def _text(value: Any) -> str:
    return _ILLEGAL_XML.sub("", str(value if value is not None else ""))


def _column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _labels(job: Mapping[str, Any]) -> list[str]:
    return [str(label) for label in job.get("match_labels") or []]


def fit_points(job: Mapping[str, Any]) -> int:
    for label in _labels(job):
        match = re.fullmatch(r"FIT_SCORE:(-?\d+)", label)
        if match:
            return int(match.group(1))
    return 0


def boost_points(job: Mapping[str, Any]) -> int:
    """Diferenciais (+5 cada, até 10) e empresa favorita (+10) do perfil."""

    labels = [str(label) for label in job.get("match_labels") or []]
    bonus = sum(label.startswith("BONUS_MATCH:") for label in labels)
    favorite = any(label.startswith("COMPANY_FAVORITE:") for label in labels)
    return min(10, bonus * 5) + (10 if favorite else 0)


def job_score(job: Mapping[str, Any], now: datetime | None = None) -> int:
    """Nota de 0 a 100: aderência ao perfil (até 90) + frescor da vaga (até 10).

    Cada critério atendido (tecnologia, nível, local, modelo) vale 20; ser
    `FIT:READY` soma 10; vaga publicada há menos de 3 dias soma 10, 7 dias 7,
    14 dias 4 e 30 dias 2. Vaga fora do perfil recebe 0.
    """

    state = fit_state(job)
    points = fit_points(job)
    if state == "EXCLUDE" or points < 0:
        return 0
    score = points * 20 + (10 if state == "READY" else 0) + boost_points(job)
    published = parse_iso_datetime(job.get("published_at"))
    if published is not None:
        age = ((now or datetime.now(timezone.utc)) - published).total_seconds() / 86400
        for limit, bonus in ((3, 10), (7, 7), (14, 4), (30, 2)):
            if 0 <= age <= limit:
                score += bonus
                break
    return min(100, max(0, score))


def _observations(job: Mapping[str, Any], note: str, reasons: Sequence[str]) -> str:
    parts = [note] if note else []
    if reasons:
        parts.append("Atenção: " + "; ".join(reasons))
    also = [
        label.removeprefix("ALSO_SEEN_IN:")
        for label in _labels(job)
        if label.startswith("ALSO_SEEN_IN:")
    ]
    if also:
        parts.append("Também em " + ", ".join(also))
    return " | ".join(parts)


def _status(job: Mapping[str, Any], tracking_status: str) -> tuple[str, int]:
    if tracking_status in _TRACKING_NAMES:
        style = {
            "SAVED": _S_BLUE,
            "APPLIED": _S_GREEN,
            "INTERVIEW": _S_GREEN,
            "OFFER": _S_GREEN,
            "REJECTED": _S_GRAY,
            "DISCARDED": _S_GRAY,
        }[tracking_status]
        return _TRACKING_NAMES[tracking_status], style
    if "STATUS:NEW" in _labels(job):
        return "Nova", _S_BLUE
    return "Descoberta", _S_CENTER


def level_name(job: Mapping[str, Any]) -> str:
    raw = str(job.get("seniority") or "").casefold()
    return _LEVEL_NAMES.get(raw, raw.title())


def _cell(ref: str, value: Any, style: int) -> str:
    if value is None or value == "":
        return f'<c r="{ref}" s="{style}"/>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
    return (
        f'<c r="{ref}" s="{style}" t="inlineStr"><is>'
        f'<t xml:space="preserve">{escape(_text(value))}</t></is></c>'
    )


def _sheet_xml(
    rows: Sequence[Sequence[tuple[Any, int]]],
    widths: Sequence[float],
    *,
    header_row: int | None,
    links: Mapping[str, str],
) -> str:
    cols = "".join(
        f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>'
        for i, width in enumerate(widths, start=1)
    )
    body = []
    for number, row in enumerate(rows, start=1):
        height = ' ht="32" customHeight="1"' if number == header_row else ""
        cells = "".join(
            _cell(f"{_column_letter(index)}{number}", value, style)
            for index, (value, style) in enumerate(row)
        )
        body.append(f'<row r="{number}"{height}>{cells}</row>')
    pane = ""
    filter_xml = ""
    if header_row is not None:
        last = f"{_column_letter(len(widths) - 1)}{len(rows)}"
        pane = (
            f'<pane ySplit="{header_row}" topLeftCell="A{header_row + 1}" '
            'activePane="bottomLeft" state="frozen"/>'
        )
        filter_xml = f'<autoFilter ref="A{header_row}:{last}"/>'
    link_xml = ""
    if links:
        link_xml = "<hyperlinks>" + "".join(
            f'<hyperlink ref="{ref}" r:id="rId{index}"/>'
            for index, ref in enumerate(links, start=1)
        ) + "</hyperlinks>"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheetViews><sheetView workbookViewId="0" showGridLines="0">{pane}</sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f"<cols>{cols}</cols><sheetData>{''.join(body)}</sheetData>{filter_xml}{link_xml}"
        "</worksheet>"
    )


def _rels_xml(links: Mapping[str, str]) -> str:
    items = "".join(
        '<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/hyperlink" Target={t} TargetMode="External"/>'.format(
            i=index, t=quoteattr(url)
        )
        for index, url in enumerate(links.values(), start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{items}</Relationships>"
    )


def _safe_link(url: Any) -> str | None:
    text = _text(url).strip()
    return text if text.startswith(("https://", "http://")) and len(text) <= 2000 else None


def build_jobs_xlsx(
    jobs: Sequence[Mapping[str, Any]],
    tracking: Mapping[str, Mapping[str, str]],
    *,
    filters: Sequence[tuple[str, str]] = (),
    reasons_for: Any = None,
    now: datetime | None = None,
    preserve_order: bool = False,
) -> bytes:
    """Planilha com as vagas (melhor score primeiro) e uma aba com os filtros usados."""

    now = now or datetime.now(timezone.utc)
    scored = [(job_score(job, now), job) for job in jobs]
    if not preserve_order:
        scored.sort(key=lambda item: (
            -item[0],
            -(parse_iso_datetime(item[1].get("published_at")) or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
        ))
    header = [(name, _S_HEADER) for name, _ in COLUMNS]
    rows: list[list[tuple[Any, int]]] = [header]
    links: dict[str, str] = {}
    epoch = date(1899, 12, 30)
    for score, job in scored:
        entry = tracking.get(str(job.get("canonical_url")), {})
        status, status_style = _status(job, entry.get("status", ""))
        workplace = str(job.get("workplace_model") or "UNKNOWN")
        workplace_style = {
            "REMOTE": _S_GREEN,
            "HYBRID": _S_YELLOW,
            "ONSITE": _S_ORANGE,
        }.get(workplace, _S_CENTER)
        published = parse_iso_datetime(job.get("published_at"))
        score_style = _S_SCORE_HIGH if score >= 80 else _S_SCORE_MID if score >= 60 else _S_SCORE_LOW
        url = _safe_link(job.get("canonical_url"))
        row_number = len(rows) + 1
        if url:
            links[f"I{row_number}"] = url
        reasons = reasons_for(job) if reasons_for else []
        rows.append(
            [
                (job.get("company") or "Não informada", _S_TEXT),
                (job.get("title") or "Cargo não informado", _S_TEXT),
                (level_name(job), _S_CENTER),
                (WORKPLACE_NAMES.get(workplace, workplace), workplace_style),
                (job.get("location") or job.get("remote_scope") or "", _S_TEXT),
                (score, score_style),
                (status, status_style),
                ((published.date() - epoch).days if published else None, _S_DATE),
                (url or "", _S_LINK if url else _S_TEXT),
                (", ".join(job_technologies(job)), _S_TEXT),
                (job.get("source") or "", _S_CENTER),
                (_observations(job, entry.get("note", ""), reasons), _S_TEXT),
            ]
        )

    info: list[list[tuple[Any, int]]] = [
        [("Vagas exportadas pelo Job Radar", _S_TITLE)],
        [(f"Gerado em {now.astimezone().strftime('%d/%m/%Y %H:%M')}", _S_TEXT)],
        [(f"Total: {len(scored)} vaga(s)", _S_TEXT)],
        [("", _S_TEXT)],
        [("Filtro", _S_HEADER), ("Valor", _S_HEADER)],
        *[[(name, _S_TEXT), (value, _S_TEXT)] for name, value in filters],
        [("", _S_TEXT)],
        [("Como o Score é calculado", _S_HEADER), ("", _S_HEADER)],
        [("Aderência", _S_TEXT), ("20 pontos por critério atendido: tecnologia, nível, local e modelo de trabalho.", _S_TEXT)],
        [("Mais compatível", _S_TEXT), ("+10 quando tudo confirma (FIT:READY).", _S_TEXT)],
        [("Recência", _S_TEXT), ("+10 até 3 dias, +7 até 7 dias, +4 até 14 dias, +2 até 30 dias.", _S_TEXT)],
    ]

    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<bookViews><workbookView activeTab="0"/></bookViews><sheets>'
            '<sheet name="Vagas" sheetId="1" r:id="rId1"/>'
            '<sheet name="Filtros e critérios" sheetId="2" r:id="rId2"/>'
            "</sheets></workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>"
        ),
        "xl/styles.xml": _STYLES,
        "xl/worksheets/sheet1.xml": _sheet_xml(
            rows, [w for _, w in COLUMNS], header_row=1, links=links
        ),
        "xl/worksheets/sheet2.xml": _sheet_xml(
            info, [34, 90], header_row=None, links={}
        ),
    }
    if links:
        files["xl/worksheets/_rels/sheet1.xml.rels"] = _rels_xml(links)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()
