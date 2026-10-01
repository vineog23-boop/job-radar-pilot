"""Descrição e título sem código de página nem restos de navegação.

Trechos reais da coleta de 01/10/2026 (amostra em tests/fixtures).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scrapling.parser import Adaptor

from job_radar.enrich import _main_text
from job_radar.models import SourceKind
from job_radar.sources.base import extract_value
from job_radar.text_cleaning import clean_description, clean_title

PROJECT = Path(__file__).resolve().parents[1]

NERDIN = (
    "Desenvolvedor Back-end (IoT / BMS) Home Office Sistemas • Há 2 dias • Cód. 363-26 "
    "#sistemas #desenvolvedor #c++ #back end Quero essa Vaga (function(){ if "
    "(window.__vagaFavoritoInit) return; window.__vagaFavoritoInit = true; "
    "document.addEventListener('click', function(ev) { var btn = ev.target; });})();"
)
CASADO = (
    "Remoto (Sede em Campinas, SP) CLT Júnior Remoto Programação Superior Completo "
    "Salvar Vaga (adsbygoogle = window.adsbygoogle || []).push({}); .banner-container "
    "{ justify-self: center; min-height: 50px; }"
)
EMPREGOS = (
    "Cloud Security Architect Remota Int Gft Brasil Compartilhar vaga Que tal "
    "compartilhar esta vaga? Email WhatsApp LinkedIn Facebook X (Twitter) Copiar link "
    "Que tal compartilhar esta vaga? Email WhatsApp LinkedIn Facebook X (Twitter) "
    "Copiar link Atuar com segurança em nuvem AWS."
)
PRIMEIRA = (
    "Voltar B Engenheiro Java Júnior Remoto BairesDev Há 3 dias BRASIL, SP CLT "
    "A combinar Descrição da Vaga Panorama Geral"
)


def test_script_tail_is_removed() -> None:
    cleaned = clean_description(NERDIN)

    assert cleaned.endswith("#back end")
    assert "function" not in cleaned and "window." not in cleaned
    assert "Quero essa Vaga" not in cleaned


def test_ads_and_css_are_removed() -> None:
    cleaned = clean_description(CASADO)

    assert cleaned == "Remoto (Sede em Campinas, SP) CLT Júnior Remoto Programação Superior Completo"


def test_share_box_is_removed_but_content_stays() -> None:
    cleaned = clean_description(EMPREGOS)

    assert "compartilhar" not in cleaned.casefold()
    assert "WhatsApp" not in cleaned
    assert cleaned.endswith("Atuar com segurança em nuvem AWS.")


def test_back_link_and_logo_letter_are_removed() -> None:
    assert clean_description(PRIMEIRA).startswith("Engenheiro Java Júnior Remoto BairesDev")
    assert clean_description("Voltar Desenvolvedor Java LINA") == "Desenvolvedor Java LINA"
    assert clean_description("Voltar QA Analyst Júnior") == "QA Analyst Júnior"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_empty_description_is_none(value) -> None:
    assert clean_description(value) is None


def test_normal_text_is_untouched() -> None:
    text = "Voltaremos a contato. Requisitos: Java, Spring e vontade de aprender."

    assert clean_description(text) == text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("[Job-32006] Junior Java Developer, Brazil", "Junior Java Developer, Brazil"),
        ("Técnica - 386089", "Técnica"),
        ("Desenvolvedor Java Júnior (Cód. 12345)", "Desenvolvedor Java Júnior"),
        ("Dev [Remoto] Java", "Dev [Remoto] Java"),
        ("Desenvolvedor .NET 8", "Desenvolvedor .NET 8"),
    ],
)
def test_title_loses_internal_codes(raw: str, expected: str) -> None:
    assert clean_title(raw) == expected


CARD_HTML = """
<div class="card">
  <h3>Dev Java Júnior</h3>
  <div class="desc">Requisitos: Java e SQL.
    <script>(function(){ window.__x = 1; })();</script>
    <style>.banner{min-height:50px}</style>
    <noscript>Ative o JavaScript</noscript>
  </div>
</div>
"""


def test_card_text_skips_script_style_noscript() -> None:
    card = Adaptor(CARD_HTML, url="https://x.com").css(".card")[0]

    value = extract_value(card, ".desc::all-text")

    assert value == "Requisitos: Java e SQL."


def test_detail_page_text_skips_scripts_inside_main() -> None:
    body = "Responsabilidades: desenvolver APIs com Java. " * 6
    page = Adaptor(
        f"<main><p>{body}</p><script>var tracking = window.dataLayer;</script></main>",
        url="https://x.com",
    )

    text = _main_text(page)

    assert "dataLayer" not in text and "Responsabilidades" in text


def test_real_sample_has_no_page_code_after_cleaning() -> None:
    rows = [
        json.loads(line)
        for line in (PROJECT / "tests" / "fixtures" / "amostra-real-2026-10-01.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    cleaned = [clean_description(row.get("description_summary")) or "" for row in rows]

    for marker in ("function(", "window.", "adsbygoogle", "Que tal compartilhar"):
        assert not any(marker in text for text in cleaned), marker
    assert not any(text.startswith("Voltar ") for text in cleaned)


def test_sources_use_description_cleaning() -> None:
    """Cartão, API JSON, RSS e página de detalhe passam pela mesma limpeza."""

    import inspect

    from job_radar import enrich
    from job_radar.sources import base, json_api, rss

    for module in (base, json_api, rss, enrich):
        assert "clean_description" in inspect.getsource(module), module.__name__
    assert SourceKind.GENERIC  # import usado
