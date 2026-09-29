from __future__ import annotations

from pathlib import Path

import pytest

from job_radar.config import ConfigError, load_profile, load_sources
from job_radar.models import SourceKind


PROJECT = Path(__file__).resolve().parents[1]
EXPECTED_SOURCES = {
    "gupy",
    "indeed",
    "estagiotrainee",
    "eureca",
    "programathor",
    "casado-dev",
    "ciee",
    "nube",
    "vagas-com",
    "99jobs",
    "cia-de-talentos",
    "companhia-de-estagios",
    "otrainee",
    "vidadetrainee",
    "seja-trainee",
    "infojobs",
}


def test_loads_complete_profile_and_sources() -> None:
    profile = load_profile(PROJECT / "config" / "profile.yaml")
    sources = load_sources(PROJECT / "config" / "sources.yaml")

    assert {"java", "spring boot", "backend", "api rest"} <= set(
        profile.positive_keywords
    )
    assert profile.seniority_levels == ("estagio", "junior")
    assert "remoto-brasil" in profile.location_scopes
    assert "sao-carlos-sp" in profile.location_scopes
    assert "florianopolis-sc" in profile.location_scopes
    assert {"pleno", "senior", "staff", "principal"} <= set(profile.excluded_terms)
    assert {source.code for source in sources} == EXPECTED_SOURCES
    assert len({source.code for source in sources}) == len(sources)
    assert all(source.start_url.startswith("https://") for source in sources)
    assert all(1 <= source.max_pages <= 100 for source in sources)
    assert all(source.min_interval_seconds >= 1 for source in sources)
    assert "linkedin" not in {source.code for source in sources}
    assert {
        source.code for source in sources if source.default_country == "BR"
    } == {"indeed", "casado-dev"}


def test_priority_sources_target_real_result_surfaces_and_current_selectors() -> None:
    sources = {
        source.code: source
        for source in load_sources(PROJECT / "config" / "sources.yaml")
    }

    assert "/job-search/term%3D" in sources["gupy"].start_url
    assert sources["gupy"].max_pages == 3
    assert "?q=" in sources["indeed"].start_url
    assert sources["indeed"].max_pages == 1
    assert len(sources["gupy"].queries) >= 5
    assert len(sources["indeed"].queries) >= 5
    assert sources["programathor"].selectors["next"]
    assert ":not(.opacity-60p)" in sources["programathor"].selectors["card"]
    assert sources["casado-dev"].selectors["card"] == "a.cd-job"
    assert sources["casado-dev"].selectors["next"] == "a[rel='next']::attr(href)"
    assert sources["vagas-com"].selectors["title"].endswith("::all-text")
    assert sources["companhia-de-estagios"].start_url.endswith("/vagas-de-estagio/")
    assert "--expired" in sources["companhia-de-estagios"].selectors["card"]
    assert sources["otrainee"].start_url.endswith("/category/vagas-abertas/")
    assert sources["otrainee"].selectors["title"] == ".entry-title a::all-text"
    assert sources["seja-trainee"].selectors["card"] == "article.jeg_post"
    assert sources["vidadetrainee"].enabled is False
    assert sources["eureca"].start_url.endswith("/oportunidades")
    assert sources["eureca"].selectors["card"].startswith("[data-testid^")
    assert sources["ciee"].selectors["card"].startswith("a.vaga-row")
    assert sources["nube"].requires_auth is False
    assert sources["nube"].selectors["card"].startswith("a.flex.flex-col")
    assert sources["99jobs"].kind is SourceKind.GENERIC
    assert sources["99jobs"].selectors["declared_count"].startswith("#opportunities")
    assert sources["cia-de-talentos"].selectors["card"] == ".block-opportunities"
    assert sources["infojobs"].kind is SourceKind.DYNAMIC
    assert sources["infojobs"].selectors["card"].startswith(".js_vacanciesGridFragment")


def test_rejects_unknown_source_kind(tmp_path: Path) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text(
        "sources:\n"
        "  - code: example\n"
        "    kind: magic\n"
        "    start_url: https://example.com/jobs\n"
        "    enabled: true\n"
        "    max_pages: 1\n"
        "    min_interval_seconds: 1\n"
        "    requires_auth: false\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="kind"):
        load_sources(config)


def test_rejects_non_https_start_url(tmp_path: Path) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text(
        "sources:\n"
        "  - code: example\n"
        "    kind: dynamic\n"
        "    start_url: http://example.com/jobs\n"
        "    enabled: true\n"
        "    max_pages: 1\n"
        "    min_interval_seconds: 1\n"
        "    requires_auth: false\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="HTTPS"):
        load_sources(config)


def test_loads_optional_source_default_country(tmp_path: Path) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text(
        "sources:\n"
        "  - code: example\n"
        "    kind: dynamic\n"
        "    start_url: https://example.com/jobs\n"
        "    enabled: true\n"
        "    max_pages: 1\n"
        "    min_interval_seconds: 1\n"
        "    requires_auth: false\n"
        "    default_country: BR\n",
        encoding="utf-8",
    )

    sources = load_sources(config)

    assert sources[0].default_country == "BR"


def test_source_adaptive_defaults_true_and_accepts_false(tmp_path: Path) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text(
        "sources:\n"
        "  - code: default-adaptive\n"
        "    kind: dynamic\n"
        "    start_url: https://example.com/default\n"
        "    enabled: true\n"
        "    max_pages: 1\n"
        "    min_interval_seconds: 1\n"
        "    requires_auth: false\n"
        "  - code: disabled-adaptive\n"
        "    kind: dynamic\n"
        "    start_url: https://example.com/disabled\n"
        "    enabled: true\n"
        "    max_pages: 1\n"
        "    min_interval_seconds: 1\n"
        "    requires_auth: false\n"
        "    adaptive: false\n",
        encoding="utf-8",
    )

    sources = load_sources(config)

    assert sources[0].adaptive is True
    assert sources[1].adaptive is False


def test_rejects_non_boolean_source_adaptive(tmp_path: Path) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text(
        "sources:\n"
        "  - code: example\n"
        "    kind: dynamic\n"
        "    start_url: https://example.com/jobs\n"
        "    enabled: true\n"
        "    max_pages: 1\n"
        "    min_interval_seconds: 1\n"
        "    requires_auth: false\n"
        '    adaptive: "yes"\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="adaptive deve ser booleano"):
        load_sources(config)


@pytest.mark.parametrize("default_country", ("BRA", "ZZ", "br"))
def test_rejects_invalid_source_default_country_code(
    tmp_path: Path,
    default_country: str,
) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text(
        "sources:\n"
        "  - code: example\n"
        "    kind: dynamic\n"
        "    start_url: https://example.com/jobs\n"
        "    enabled: true\n"
        "    max_pages: 1\n"
        "    min_interval_seconds: 1\n"
        "    requires_auth: false\n"
        f"    default_country: {default_country}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="default_country deve usar codigo ISO"):
        load_sources(config)


def test_rejects_missing_selectors_before_network(tmp_path: Path) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text(
        "sources:\n"
        "  - code: example\n"
        f"    kind: {SourceKind.GENERIC.value}\n"
        "    start_url: https://example.com/jobs\n"
        "    enabled: true\n"
        "    max_pages: 1\n"
        "    min_interval_seconds: 1\n"
        "    requires_auth: false\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="selectors"):
        load_sources(config)
