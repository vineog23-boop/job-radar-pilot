"""Nome da empresa (10/10/2026): portais trazem slogan, prefixo de marketing ou nada.
Casos reais da coleta de 10/10/2026."""

from __future__ import annotations

from dataclasses import replace

import pytest

from job_radar.company import clean_company, company_from_ats_url, company_from_title
from job_radar.models import SourceConfig, SourceKind, VacancyRecord
from job_radar.sources.base import apply_source_defaults


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Carreiras SoftExpert", "SoftExpert"),
        ("Neogrid Carreiras", "Neogrid"),
        ("Vagas na Tokenlab", "Tokenlab"),
        ("Vagas Instituto de Pesquisas Eldorado", "Instituto de Pesquisas Eldorado"),
        ("Leite de Rosas | Trabalhe Conosco", "Leite de Rosas"),
        ("Logo Programa de Estágio Base e Flowa 2027", "Base e Flowa"),
        ("Programa de Estágio | Tecon Suape", "Tecon Suape"),
        ("Bauducco #vemparaBauducco", "Bauducco"),
        ("Tahto - Staff e Executivo #VemSerTahto", "Tahto - Staff e Executivo"),
        ("Somos BHS 💚", "BHS"),
        ("Somos Educação", "Somos Educação"),          # nome real: sem emoji/hashtag, fica
        ("Venha Ser Consultoria", "Venha Ser Consultoria"),
        ("Acme Ltda", "Acme Ltda"),
        ("CI&T", "CI&T"),
    ],
)
def test_clean_company_removes_marketing_noise(raw: str, expected: str) -> None:
    assert clean_company(raw) == expected


@pytest.mark.parametrize("raw", ["VENHA SER #SANGUELARANJA 🧡🚀", "#sejaveriter", "   ", None])
def test_slogan_only_names_become_empty(raw) -> None:
    assert clean_company(raw) is None


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://fcamara.gupy.io/jobs/12692056", "Fcamara"),
        ("https://estapar.inhire.app/vagas/108c/dev", "Estapar"),
        ("https://jobs.lever.co/ciandt/28c9ce8e/apply", "Ciandt"),
        ("https://job-boards.greenhouse.io/xpinc/jobs/1", "Xpinc"),
        ("https://boards.greenhouse.io/nubank/jobs/1", "Nubank"),
        ("https://jobs.quickin.io/sinqia/jobs/6ac78feb", "Sinqia"),
        ("https://www.primeiravagatech.com.br/vaga/x", None),
        ("https://portal.gupy.io/job/x", None),
    ],
)
def test_company_from_ats_url(url: str, expected) -> None:
    assert company_from_ats_url(url) == expected


def test_company_from_title_uses_first_matching_group() -> None:
    pattern = r"^(.+?) abre |Trainee ([A-ZÀ-Ú][\w&-]+(?: [A-ZÀ-Ú][\w&-]+)*) 20\d\d"
    assert company_from_title("Ingredion abre Programa de Estágio 2027 para mais de 25 cursos!", pattern) == "Ingredion"
    assert company_from_title("Remuneração de R$ 10.000: Trainee Praso 2027 aceita todos", pattern) == "Praso"
    assert company_from_title("Acompanhe: vagas abertas", pattern) is None


def _source(**selectors) -> SourceConfig:
    return SourceConfig(code="p", kind=SourceKind.RSS, start_url="https://x.com.br/feed", enabled=True,
                        max_pages=1, min_interval_seconds=1, requires_auth=False, selectors=selectors)


def _record(**extra) -> VacancyRecord:
    base = VacancyRecord(source="p", source_job_id="1", canonical_url="https://x.com.br/v/1",
                         title="Dev", company=None)
    return replace(base, **extra)


def test_defaults_clean_slogan_and_fall_back_to_ats_host() -> None:
    record = _record(company="VENHA SER #SANGUELARANJA 🧡🚀", canonical_url="https://fcamara.gupy.io/jobs/1")
    assert apply_source_defaults(record, _source()).company == "Fcamara"


def test_defaults_take_company_from_title_when_card_has_none() -> None:
    source = _source(company_from_title=r"^(.+?) abre ")
    record = _record(title="Kinross abre Trainee para Engenharia")
    assert apply_source_defaults(record, source).company == "Kinross"


def test_defaults_keep_good_company_untouched() -> None:
    record = _record(company="Sicredi", canonical_url="https://fcamara.gupy.io/jobs/1")
    assert apply_source_defaults(record, _source()).company == "Sicredi"
