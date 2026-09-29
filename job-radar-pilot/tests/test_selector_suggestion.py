from __future__ import annotations

from collections.abc import Callable

import pytest
from scrapling.parser import Adaptor


def _suggest_api() -> Callable[[object, str], object | None]:
    try:
        from job_radar.selector_suggestion import suggest_from_page
    except ModuleNotFoundError:
        pytest.fail("job_radar.selector_suggestion ainda nao existe", pytrace=False)
    return suggest_from_page


def test_suggests_common_card_and_valid_fields_for_every_similar_card() -> None:
    page = Adaptor(
        """
        <main>
          <ul class="jobs">
            <li class="vaga x1"><a href="/1"><h3>Desenvolvedor Java Junior</h3></a></li>
            <li class="vaga x2"><a href="/2"><h3>Estagio Java</h3></a></li>
            <li class="vaga x3"><a href="/3"><h3>Backend Junior</h3></a></li>
          </ul>
        </main>
        """,
        url="https://jobs.example.com/vagas",
    )

    suggestion = _suggest_api()(page, "Desenvolvedor Java Junior")

    assert suggestion is not None
    assert getattr(suggestion, "card") == "li.vaga"
    assert getattr(suggestion, "title") == "h3::all-text"
    assert getattr(suggestion, "url") == "a::attr(href)"
    assert getattr(suggestion, "cards_found") == 3
    assert getattr(suggestion, "title_matches") == 3
    assert getattr(suggestion, "url_matches") == 3


def test_finds_title_split_across_descendants_and_ignores_unsafe_css_tokens() -> None:
    page = Adaptor(
        """
        <ul class="jobs">
          <li class="vaga sm:w-1/2 x1"><a href="/1"><h3><span>Desenvolvedor</span> <span>Java Junior</span></h3></a></li>
          <li class="vaga sm:w-1/2 x2"><a href="/2"><h3><span>Estagio</span> <span>Java</span></h3></a></li>
          <li class="vaga sm:w-1/2 x3"><a href="/3"><h3><span>Backend</span> <span>Junior</span></h3></a></li>
        </ul>
        """,
        url="https://jobs.example.com/vagas",
    )

    suggestion = _suggest_api()(page, "Desenvolvedor Java Junior")

    assert suggestion is not None
    assert getattr(suggestion, "card") == "li.vaga"
    assert getattr(suggestion, "title") == "h3::all-text"
    assert getattr(suggestion, "title_matches") == 3
    assert getattr(suggestion, "url_matches") == 3


def test_returns_none_when_visible_text_does_not_exist() -> None:
    page = Adaptor(
        '<ul><li class="vaga"><a href="/1"><h3>Java Junior</h3></a></li></ul>',
        url="https://jobs.example.com/vagas",
    )

    assert _suggest_api()(page, "Cobol Senior") is None


def test_scopes_card_selector_when_same_classes_exist_in_another_container() -> None:
    page = Adaptor(
        """
        <main>
          <ul class="jobs">
            <li class="vaga x1"><a href="/1"><h3>Java Junior</h3></a></li>
            <li class="vaga x2"><a href="/2"><h3>Estagio Java</h3></a></li>
            <li class="vaga x3"><a href="/3"><h3>Backend Junior</h3></a></li>
          </ul>
          <ul class="related">
            <li class="vaga"><a href="/guide"><h3>Guia de carreira</h3></a></li>
          </ul>
        </main>
        """,
        url="https://jobs.example.com/vagas",
    )

    suggestion = _suggest_api()(page, "Java Junior")

    assert suggestion is not None
    assert getattr(suggestion, "card") == "ul.jobs > li.vaga"
    assert getattr(suggestion, "cards_found") == 3


def test_does_not_promote_repeated_layout_columns_above_job_cards() -> None:
    page = Adaptor(
        """
        <main class="row">
          <section class="column">
            <div class="vaga x1"><a href="/1"><h3>Java Junior</h3></a></div>
            <div class="vaga x2"><a href="/2"><h3>Estagio Java</h3></a></div>
            <div class="vaga x3"><a href="/3"><h3>Backend Junior</h3></a></div>
          </section>
          <section class="column"><p>Filtros</p></section>
          <section class="column"><p>Conteudo lateral</p></section>
        </main>
        """,
        url="https://jobs.example.com/vagas",
    )

    suggestion = _suggest_api()(page, "Java Junior")

    assert suggestion is not None
    assert getattr(suggestion, "card") == "div.vaga"
    assert getattr(suggestion, "cards_found") == 3


def test_excludes_invalid_sibling_class_from_card_selector() -> None:
    page = Adaptor(
        """
        <section class="jobs">
          <div class="vaga"><a href="/1"><h3>Java Junior</h3></a></div>
          <div class="vaga"><a href="/2"><h3>Estagio Java</h3></a></div>
          <div class="vaga"><a href="/3"><h3>Backend Junior</h3></a></div>
          <div class="vaga encerrada"><p>Vaga encerrada</p></div>
        </section>
        """,
        url="https://jobs.example.com/vagas",
    )

    suggestion = _suggest_api()(page, "Java Junior")

    assert suggestion is not None
    assert getattr(suggestion, "card") == "div.vaga:not(.encerrada)"
    assert getattr(suggestion, "cards_found") == 3


def test_rejects_cards_with_ambiguous_title_and_url_matches() -> None:
    page = Adaptor(
        """
        <ul class="jobs">
          <li class="vaga"><a href="/1"><h3>Java Junior</h3></a><a href="/1-alt"><h3>Outra vaga</h3></a></li>
          <li class="vaga"><a href="/2"><h3>Estagio Java</h3></a><a href="/2-alt"><h3>Outra vaga</h3></a></li>
          <li class="vaga"><a href="/3"><h3>Backend Junior</h3></a><a href="/3-alt"><h3>Outra vaga</h3></a></li>
        </ul>
        """,
        url="https://jobs.example.com/vagas",
    )

    assert _suggest_api()(page, "Java Junior") is None


def test_prefers_innermost_repeated_job_cards_over_repeated_container() -> None:
    page = Adaptor(
        """
        <main>
          <ul class="jobs">
            <li class="vaga"><a href="/1"><h3>Java Junior</h3></a></li>
            <li class="vaga"><a href="/2"><h3>Estagio Java</h3></a></li>
            <li class="vaga"><a href="/3"><h3>Backend Junior</h3></a></li>
          </ul>
          <ul class="jobs"><article><a href="/guia"><h3>Guia de carreira</h3></a></article></ul>
          <ul class="jobs"><article><a href="/evento"><h3>Evento de tecnologia</h3></a></article></ul>
        </main>
        """,
        url="https://jobs.example.com/vagas",
    )

    suggestion = _suggest_api()(page, "Java Junior")

    assert suggestion is not None
    assert getattr(suggestion, "card") == "li.vaga"
    assert getattr(suggestion, "cards_found") == 3


def test_rejects_pure_suggestion_when_similar_group_has_editorial_outlier() -> None:
    page = Adaptor(
        """
        <ul class="jobs">
          <li class="vaga"><a href="/1"><h3>Java Junior</h3></a></li>
          <li class="vaga"><a href="/2"><h3>Estagio Java</h3></a></li>
          <li class="vaga"><a href="/3"><h3>Backend Junior</h3></a></li>
          <li class="vaga promo"><a href="/guia"><h3>Guia de carreira</h3></a></li>
        </ul>
        """,
        url="https://jobs.example.com/vagas",
    )

    assert _suggest_api()(page, "Java Junior") is None
