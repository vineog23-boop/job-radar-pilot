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
    assert {source.code for source in sources} == EXPECTED_SOURCES
    assert len({source.code for source in sources}) == len(sources)
    assert all(source.start_url.startswith("https://") for source in sources)
    assert all(1 <= source.max_pages <= 100 for source in sources)
    assert all(source.min_interval_seconds >= 1 for source in sources)
    assert "linkedin" not in {source.code for source in sources}


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
