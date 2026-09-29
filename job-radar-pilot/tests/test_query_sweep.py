from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from job_radar.config import ConfigError, load_sources
from job_radar.pipeline import _search_urls, _slugify


def _source(tmp_path: Path, extra: str):
    path = tmp_path / "s.yaml"
    path.write_text(
        "sources:\n  - code: x\n    kind: generic\n    start_url: https://x.com.br/vagas\n"
        "    enabled: true\n    max_pages: 1\n    min_interval_seconds: 1\n"
        "    requires_auth: false\n    selectors: {card: a, title: a, url: '::attr(href)'}\n"
        + extra,
        encoding="utf-8",
    )
    return load_sources(path)[0]


def test_slugify_removes_accents_and_symbols() -> None:
    assert _slugify("Estágio  Java/Spring!") == "estagio-java-spring"


def test_query_path_builds_one_url_per_query(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        '    query_path: "/vagas-de-{query}"\n    queries: [java junior, "Estágio Java"]\n',
    )
    assert _search_urls(source) == (
        "https://x.com.br/vagas-de-java-junior",
        "https://x.com.br/vagas-de-estagio-java",
    )


def test_query_param_replaces_existing_parameter(tmp_path: Path) -> None:
    source = _source(tmp_path, "    query_param: termo\n    queries: [backend]\n")
    source = replace(source, start_url="https://x.com.br/vagas?termo=old&page=3&f=1")
    assert _search_urls(source) == ("https://x.com.br/vagas?f=1&termo=backend",)


def test_source_without_query_support_keeps_start_url(tmp_path: Path) -> None:
    source = _source(tmp_path, "    queries: [java]\n")
    assert _search_urls(source) == ("https://x.com.br/vagas",)


@pytest.mark.parametrize(
    "extra",
    [
        '    query_path: "sem-barra-{query}"\n',
        '    query_path: "/vagas"\n',
        "    query_param: ''\n",
        '    query_path: "/v-{query}"\n    query_param: q\n',
    ],
)
def test_invalid_query_options_are_rejected(tmp_path: Path, extra: str) -> None:
    with pytest.raises(ConfigError):
        _source(tmp_path, extra)
