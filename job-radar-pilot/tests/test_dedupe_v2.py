"""Deduplicação mais esperta: casos reais da coleta de 01/10/2026.

- Mesma vaga em portais diferentes com "Remoto" só num título e locais
  escritos de jeitos diferentes ("Brasil, SP" × "Remoto").
- Republicação: mesmo cargo e empresa no mesmo portal, URLs diferentes.
- Nunca juntar empresas diferentes nem cidades presenciais diferentes.
"""

from __future__ import annotations

import json
from pathlib import Path

from job_radar.identity import deduplicate
from job_radar.models import VacancyRecord, WorkplaceModel
from job_radar.reclassify import record_from_payload

PROJECT = Path(__file__).resolve().parents[1]


def _record(source: str, url: str, title: str, company: str, location: str | None, **extra) -> VacancyRecord:
    return VacancyRecord(
        source=source,
        source_job_id=None,
        canonical_url=url,
        title=title,
        company=company,
        location=location,
        **extra,
    )


def test_cross_portal_same_job_with_remote_suffix_and_different_location_text() -> None:
    primeira = _record(
        "primeiravagatech",
        "https://www.primeiravagatech.com.br/vaga/desenvolvedor-java-i-python-junior-remoto-brasil-64ae37",
        "Desenvolvedor (Java I Python) Junior Remoto",
        "INSI",
        "Brasil, SP",
    )
    indeed = _record(
        "indeed",
        "https://br.indeed.com/viewjob?jk=28ad982b28dcf6a0",
        "Desenvolvedor (Java I Python) Junior",
        "Insi",
        "Remoto",
    )

    result = deduplicate([primeira, indeed])

    assert len(result.unique) == 1
    assert "ALSO_SEEN_IN:indeed" in result.unique[0].match_labels


def test_repost_in_same_portal_keeps_most_recent() -> None:
    older = _record(
        "primeiravagatech",
        "https://www.primeiravagatech.com.br/vaga/-desenvolvedor-java-junior-remoto-brasil-4acf8f",
        "Desenvolvedor Java Junior (Remoto)",
        "LELLO",
        "Brasil, SP",
        published_at="2026-08-20T00:00:00+00:00",
    )
    newer = _record(
        "primeiravagatech",
        "https://www.primeiravagatech.com.br/vaga/desenvolvedor-java-junior-remoto-brasil-08e492",
        "Desenvolvedor Java Junior (Remoto)",
        "LELLO",
        "Brasil, SP",
        published_at="2026-08-23T00:00:00+00:00",
    )

    result = deduplicate([older, newer])

    assert [record.canonical_url for record in result.unique] == [newer.canonical_url]
    assert "REPOSTED:1" in result.unique[0].match_labels
    assert result.duplicate_count == 1


def test_gender_and_role_spelling_variants_are_the_same_job() -> None:
    first = _record("empregostec", "https://a.com/1", "Pessoa Desenvolvedora Back-End Java", "Acme Ltda", "Remoto")
    second = _record("remotar", "https://b.com/2", "Desenvolvedor(a) Backend Java", "ACME", None)

    result = deduplicate([first, second])

    assert len(result.unique) == 1


def test_different_companies_are_never_merged() -> None:
    first = _record("primeiravagatech", "https://a.com/1", "Desenvolvedor Java Junior - Remoto", "BairesDev", "Brasil, SP")
    second = _record("primeiravagatech", "https://a.com/2", "Desenvolvedor Java Junior - Remoto", "Nava Technology for Business", "Brasil, SP")

    assert len(deduplicate([first, second]).unique) == 2


def test_different_onsite_cities_are_different_openings() -> None:
    first = _record("gupy", "https://a.com/1", "Desenvolvedor Java Júnior", "Banco X", "São Paulo, SP", workplace_model=WorkplaceModel.ONSITE)
    second = _record("gupy", "https://a.com/2", "Desenvolvedor Java Júnior", "Banco X", "Recife, PE", workplace_model=WorkplaceModel.ONSITE)

    assert len(deduplicate([first, second]).unique) == 2


def test_different_specialization_is_not_merged() -> None:
    first = _record("primeiravagatech", "https://a.com/1", "Desenvolvedor Back-end Java Junior", "Acme", "Remoto")
    second = _record("indeed", "https://b.com/2", "Desenvolvedor Back-end Java Jr - Payments", "Acme", "Remoto")

    assert len(deduplicate([first, second]).unique) == 2


def test_tracked_url_is_kept_even_when_older() -> None:
    older = _record("empregostec", "https://e.com/especialista-vr-beneficios", "Especialista Dev Back | Java", "VR Benefícios", "Remoto", published_at="2026-09-09T10:45:00-03:00")
    newer = _record("empregostec", "https://e.com/especialista-vr-2", "Especialista Dev Back | Java", "VR Benefícios", "Remoto", published_at="2026-09-23T11:45:00-03:00")

    result = deduplicate([older, newer], preferred_urls={older.canonical_url})

    assert [record.canonical_url for record in result.unique] == [older.canonical_url]


def test_generic_titles_are_still_never_merged() -> None:
    first = _record("ciee", "https://c.com/A", "Estágio", "CIEE", "São Paulo, SP")
    second = _record("ciee", "https://c.com/B", "Estágio", "CIEE", "São Paulo, SP")

    assert len(deduplicate([first, second]).unique) == 2


def test_real_sample_duplicates_collapse() -> None:
    rows = [
        json.loads(line)
        for line in (PROJECT / "tests" / "fixtures" / "amostra-real-2026-10-01.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    records = [record_from_payload({**row, "match_labels": []}) for row in rows]

    result = deduplicate(records)
    titles = [(record.title, record.company) for record in result.unique]

    assert titles.count(("Desenvolvedor Java Junior (Remoto)", "LELLO")) == 1
    assert titles.count(("Especialista Dev Back | Java", "VR Benefícios")) == 1
    assert sum(1 for title, company in titles if (company or "").casefold() == "insi") == 1
    assert 280 <= len(result.unique) < 300
