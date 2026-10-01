"""Item 1.2: apelidos de tecnologia e falsos positivos de termos curtos.

Também cobre os falsos positivos achados na revisão: inglês obrigatório que
virava "diferencial", contrato negado ("não aceitamos PJ") e "redes sociais".
"""

from __future__ import annotations

import pytest

from job_radar.classifier import _canonical_term, _contains_term, _normalize, classify
from job_radar.models import SearchProfile, VacancyRecord, WorkplaceModel


def _has(text: str, term: str) -> bool:
    return _contains_term(_normalize(text), term)


@pytest.mark.parametrize(
    ("profile_term", "job_text"),
    [
        ("springboot", "Experiência com Spring Boot"),
        ("spring boot", "Stack: Java, SpringBoot e Kafka"),
        ("spring-boot", "APIs em spring boot"),
        ("node", "Back-end em Node.js"),
        ("nodejs", "Back-end em Node"),
        ("node.js", "Experiência com NodeJS"),
        ("js", "Conhecimento em JavaScript"),
        ("javascript", "Front com JS e HTML"),
        ("k8s", "Deploy em Kubernetes"),
        ("kubernetes", "Clusters K8s"),
        ("postgres", "Banco PostgreSQL"),
        ("postgresql", "Banco Postgres"),
        ("c#", "Back-end em CSharp"),
        ("csharp", "Back-end em C#"),
        ("c sharp", "Back-end em C#"),
        ("dotnet", "APIs em .NET 8"),
        (".net", "APIs em dotnet"),
        ("go", "Microsserviços em Golang"),
        ("golang", "Microsserviços em Go."),
    ],
)
def test_aliases_match_both_ways(profile_term: str, job_text: str) -> None:
    assert _has(job_text, profile_term)


@pytest.mark.parametrize(
    ("term", "job_text"),
    [
        ("js", "Desenvolvimento em JSP e Servlets"),
        ("js", "Back-end em Node.js"),
        ("go", "Acompanhar o go-live dos clientes"),
        ("go", "Analista de implantação go live"),
        ("go", "Estratégia de go-to-market"),
        ("go", "Vaga no Google"),
        ("go", "Goiânia - GO"),
        ("go", "Goiânia, GO"),
        ("go", "Goiânia/GO"),
        ("go", "Goiânia (GO)"),
        ("r", "Escritório na R. Augusta, 500"),
        ("r", "Salário de R$ 3.000"),
        ("r", "R$3.000 + benefícios"),
        ("c", "Back-end em C#"),
        ("c", "Sistemas embarcados em C++"),
        ("java", "Front-end com JavaScript"),
    ],
)
def test_short_terms_do_not_create_false_positives(term: str, job_text: str) -> None:
    assert not _has(job_text, term)


@pytest.mark.parametrize(
    ("term", "job_text"),
    [
        ("go", "Desenvolvedor Go Júnior"),
        ("go", "Experiência com Go (Golang)"),
        ("r", "Análise estatística com R e Python"),
        ("c", "Programação em C para microcontroladores"),
        ("js", "Front em JS/TS"),
    ],
)
def test_short_terms_still_match_real_mentions(term: str, job_text: str) -> None:
    assert _has(job_text, term)


def test_aliases_share_one_canonical_label() -> None:
    assert _canonical_term("SpringBoot") == "spring boot"
    assert _canonical_term("k8s") == "kubernetes"
    assert _canonical_term("Node.js") == "node"
    assert _canonical_term("go") == "golang"


PROFILE = SearchProfile(
    positive_keywords=("go",),
    seniority_levels=("junior",),
    location_scopes=("remoto-brasil",),
    workplace_models=(WorkplaceModel.REMOTE,),
)


def _record(title: str, description: str, **extra) -> VacancyRecord:
    values = dict(
        source="gupy",
        source_job_id="1",
        canonical_url="https://jobs.example.com/1",
        title=title,
        company="Acme",
        description_summary=description,
        location="Remoto",
        remote_scope="Brasil",
        workplace_model=WorkplaceModel.REMOTE,
    )
    values.update(extra)
    return VacancyRecord(**values)


def test_go_live_job_is_not_ready_for_go_profile() -> None:
    labels = classify(
        _record("Analista de Implantação Júnior", "Acompanhar o go-live dos clientes."),
        PROFILE,
        default_country="BR",
    ).match_labels

    assert "TECH_MATCH:golang" not in labels
    assert "FIT:READY" not in labels


def test_springboot_profile_matches_spring_boot_job() -> None:
    profile = SearchProfile(
        positive_keywords=("java", "springboot"),
        seniority_levels=("junior",),
        location_scopes=("remoto-brasil",),
    )

    labels = classify(
        _record("Desenvolvedor Java Júnior", "APIs com Spring Boot"),
        profile,
        default_country="BR",
    ).match_labels

    assert "TECH_MATCH:spring boot" in labels


JAVA = SearchProfile(
    positive_keywords=("java",),
    seniority_levels=("junior",),
    location_scopes=("remoto-brasil",),
    contract_types=("PJ",),
    avoid_advanced_english=True,
)


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("English: advanced. Bonus points for Docker.", "LANGUAGE:english_advanced"),
        ("Inglês avançado. Diferencial: conhecer Kafka.", "LANGUAGE:english_advanced"),
        ("Inglês avançado é um diferencial.", "LANGUAGE:english_plus"),
        ("Diferenciais: inglês avançado e Docker.", "LANGUAGE:english_plus"),
    ],
)
def test_english_nice_to_have_stays_inside_its_sentence(description: str, expected: str) -> None:
    labels = classify(
        _record("Desenvolvedor Java Júnior", description), JAVA, default_country="BR"
    ).match_labels

    assert expected in labels


@pytest.mark.parametrize(
    ("description", "present", "absent"),
    [
        ("Não aceitamos PJ, somente CLT.", {"CONTRACT:CLT"}, {"CONTRACT:PJ"}),
        ("Contratação PJ (não CLT).", {"CONTRACT:PJ"}, {"CONTRACT:CLT"}),
        ("Sem CLT: contrato PJ.", {"CONTRACT:PJ"}, {"CONTRACT:CLT"}),
        ("Regime CLT ou PJ.", {"CONTRACT:CLT", "CONTRACT:PJ"}, set()),
    ],
)
def test_negated_contract_is_not_detected(description: str, present: set, absent: set) -> None:
    labels = set(
        classify(
            _record("Desenvolvedor Java Júnior", description), JAVA, default_country="BR"
        ).match_labels
    )

    assert present <= labels
    assert not (absent & labels)


def test_job_refusing_pj_is_contract_mismatch_for_pj_profile() -> None:
    labels = classify(
        _record("Desenvolvedor Java Júnior", "Não aceitamos PJ, somente CLT."),
        JAVA,
        default_country="BR",
    ).match_labels

    assert "CONTRACT_MISMATCH:CLT" in labels


def test_social_media_role_is_off_topic() -> None:
    labels = classify(
        _record("Assistente de Redes Sociais", "Gerenciar Instagram e TikTok."),
        JAVA,
        default_country="BR",
    ).match_labels

    assert "RELEVANCE:OFF_TOPIC" in labels


def test_network_role_is_still_it() -> None:
    labels = classify(
        _record("Analista de Redes Júnior", "Cisco, roteadores e firewall."),
        JAVA,
        default_country="BR",
    ).match_labels

    assert "RELEVANCE:OFF_TOPIC" not in labels
