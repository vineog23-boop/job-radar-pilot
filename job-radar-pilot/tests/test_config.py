from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import job_radar.models as models
from job_radar.config import ConfigError, load_profile, load_sources
from job_radar.models import SourceKind


PROJECT = Path(__file__).resolve().parents[1]
EXPECTED_SOURCES = {
    "inhire-programmers", "inhire-bionexo", "ciandt", "greenhouse-abinbev",
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
    "nerdin",
    "mytechjobs",
    "geekhunter", "quickin", "gupy-api", "primeiravagatech", "empregostec",
    "empregos-com",
    "trampos",
    "remotar",
    "coodesh",
}


def test_browser_options_is_immutable_slotted_and_defaults_to_noop() -> None:
    options = models.BrowserOptions()

    assert options.disable_resources is False
    assert options.blocked_domains == ()
    assert not hasattr(options, "__dict__")
    with pytest.raises(FrozenInstanceError):
        options.disable_resources = True  # type: ignore[misc]


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
    # Boards corporativos podem conter vagas globais: não inventar país.
    company_boards = {"inhire-programmers", "inhire-bionexo", "ciandt", "greenhouse-abinbev"}
    assert all(
        source.default_country == (None if source.code in company_boards else "BR")
        for source in sources
    )
    scrolling = {source.code for source in sources if source.browser.scroll_to_load}
    assert scrolling == {
        "eureca", "nube", "cia-de-talentos", "trampos", "remotar", "coodesh"
    }
    assert all(
        source.browser
        == models.BrowserOptions(scroll_to_load=source.code in scrolling)
        for source in sources
    )


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


def test_source_browser_options_default_and_accept_explicit_values(
    tmp_path: Path,
) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text(
        "sources:\n"
        "  - code: default-browser\n"
        "    kind: dynamic\n"
        "    start_url: https://example.com/default\n"
        "    enabled: true\n"
        "    max_pages: 1\n"
        "    min_interval_seconds: 1\n"
        "    requires_auth: false\n"
        "  - code: empty-browser\n"
        "    kind: dynamic\n"
        "    start_url: https://example.com/empty\n"
        "    enabled: true\n"
        "    max_pages: 1\n"
        "    min_interval_seconds: 1\n"
        "    requires_auth: false\n"
        "    browser: {}\n"
        "  - code: optimized-browser\n"
        "    kind: dynamic\n"
        "    start_url: https://example.com/optimized\n"
        "    enabled: true\n"
        "    max_pages: 1\n"
        "    min_interval_seconds: 1\n"
        "    requires_auth: false\n"
        "    browser:\n"
        "      disable_resources: true\n"
        "      blocked_domains: [ads.example.com, metrics.example.org]\n",
        encoding="utf-8",
    )

    sources = load_sources(config)

    assert sources[0].browser == models.BrowserOptions()
    assert sources[1].browser == models.BrowserOptions()
    assert sources[2].browser == models.BrowserOptions(
        disable_resources=True,
        blocked_domains=("ads.example.com", "metrics.example.org"),
    )


def test_rejects_non_mapping_source_browser(tmp_path: Path) -> None:
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
        "    browser: []\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=r"sources\[0\]\.browser deve ser um objeto"):
        load_sources(config)


def test_rejects_non_string_source_browser_key_with_config_error(
    tmp_path: Path,
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
        "    browser: {1: true, unknown: true}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="browser exige chaves de texto"):
        load_sources(config)


@pytest.mark.parametrize(
    ("browser_yaml", "message"),
    (
        ("      unknown: true\n", "browser invalido; chaves desconhecidas"),
        ('      disable_resources: "yes"\n', "disable_resources deve ser booleano"),
        ("      disable_resources: 1\n", "disable_resources deve ser booleano"),
        ("      blocked_domains: ads.example.com\n", "blocked_domains deve ser uma lista"),
        ("      blocked_domains: ['']\n", r"blocked_domains\[0\].*hostname valido"),
        ("      blocked_domains: [123]\n", r"blocked_domains\[0\].*hostname valido"),
        ("      blocked_domains: [https://ads.example.com]\n", r"blocked_domains\[0\].*hostname valido"),
        ("      blocked_domains: [user@ads.example.com]\n", r"blocked_domains\[0\].*hostname valido"),
        ("      blocked_domains: [ads.example.com:443]\n", r"blocked_domains\[0\].*hostname valido"),
        ("      blocked_domains: [ads.example.com/path]\n", r"blocked_domains\[0\].*hostname valido"),
        ("      blocked_domains: ['ads.example.com?x=1']\n", r"blocked_domains\[0\].*hostname valido"),
        ("      blocked_domains: ['ads.example.com#fragment']\n", r"blocked_domains\[0\].*hostname valido"),
        ("      blocked_domains: ['*.example.com']\n", r"blocked_domains\[0\].*hostname valido"),
        ("      blocked_domains: [bad_label.example.com]\n", r"blocked_domains\[0\].*hostname valido"),
        ("      blocked_domains: [-ads.example.com]\n", r"blocked_domains\[0\].*hostname valido"),
        ("      blocked_domains: [ads-.example.com]\n", r"blocked_domains\[0\].*hostname valido"),
        ("      blocked_domains: ['faß.de']\n", r"blocked_domains\[0\].*hostname valido"),
        ("      blocked_domains: ['K.example']\n", r"blocked_domains\[0\].*hostname valido"),
        ("      blocked_domains: [127.0.0.1]\n", r"blocked_domains\[0\].*hostname valido"),
    ),
)
def test_rejects_invalid_source_browser_options(
    tmp_path: Path,
    browser_yaml: str,
    message: str,
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
        "    browser:\n"
        f"{browser_yaml}",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=message):
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


def test_single_page_defaults_false_and_rejects_non_boolean(tmp_path: Path) -> None:
    base = (
        "sources:\n  - code: x\n    kind: generic\n    start_url: https://x.com.br/v\n"
        "    enabled: true\n    max_pages: 1\n    min_interval_seconds: 1\n"
        "    requires_auth: false\n"
        "    selectors: {card: a, title: a, url: '::attr(href)'}\n"
    )
    ok = tmp_path / "ok.yaml"
    ok.write_text(base + "    single_page: true\n", encoding="utf-8")
    assert models_single(ok) is True
    default = tmp_path / "default.yaml"
    default.write_text(base, encoding="utf-8")
    assert models_single(default) is False
    bad = tmp_path / "bad.yaml"
    bad.write_text(base + "    single_page: sim\n", encoding="utf-8")
    import pytest
    from job_radar.config import ConfigError, load_sources

    with pytest.raises(ConfigError):
        load_sources(bad)


def models_single(path: Path) -> bool:
    from job_radar.config import load_sources

    return load_sources(path)[0].single_page


def test_tech_focus_and_fixed_queries_defaults_and_validation(tmp_path: Path) -> None:
    base = (
        "sources:\n  - code: x\n    kind: generic\n    start_url: https://x.com.br/v?q=a\n"
        "    enabled: true\n    max_pages: 1\n    min_interval_seconds: 1\n"
        "    requires_auth: false\n"
        "    selectors: {card: a, title: a, url: '::attr(href)'}\n"
    )
    default = tmp_path / "default.yaml"
    default.write_text(base, encoding="utf-8")
    source = load_sources(default)[0]
    assert source.tech_focus is False and source.fixed_queries is False

    ok = tmp_path / "ok.yaml"
    ok.write_text(
        base + "    tech_focus: true\n    fixed_queries: true\n"
        "    query_param: q\n    queries: [java]\n",
        encoding="utf-8",
    )
    source = load_sources(ok)[0]
    assert source.tech_focus is True and source.fixed_queries is True

    no_queries = tmp_path / "noq.yaml"
    no_queries.write_text(base + "    fixed_queries: true\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_sources(no_queries)

    bad_type = tmp_path / "bad.yaml"
    bad_type.write_text(base + "    tech_focus: talvez\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_sources(bad_type)
