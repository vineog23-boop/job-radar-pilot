from __future__ import annotations


def test_markdown_report_groups_fit_states_and_escapes_untrusted_values() -> None:
    from job_radar.export_document import build_markdown_report

    jobs = [
        {
            "title": "Dev <script>alert(1)</script> [Java]",
            "company": "Acme | Labs",
            "location": "Remoto",
            "source": "gupy",
            "canonical_url": "https://example.com/vaga?id=1&from=radar",
            "match_labels": ["FIT:READY", "FIT_SCORE:91"],
        },
        {
            "title": "Estagio Backend",
            "company": "Beta",
            "location": "Sao Paulo",
            "source": "indeed",
            "canonical_url": "https://example.com/vaga/2",
            "match_labels": ["FIT:CONDITIONAL"],
        },
        {
            "title": "Link inseguro",
            "company": "Gamma",
            "location": "Hibrido",
            "source": "example",
            "canonical_url": "javascript:alert(1)",
            "match_labels": ["FIT:EXCLUDE"],
        },
        {
            "title": "URL com quebra",
            "company": "Delta",
            "location": "Remoto",
            "source": "example",
            "canonical_url": "https://example.com/vaga\n## titulo injetado",
            "match_labels": ["FIT:CONDITIONAL"],
        },
    ]

    report = build_markdown_report(
        jobs,
        generated_at="29/09/2026 10:30",
        sources=[
            {"source": "gupy", "status": "SUCCESS", "stop_reason": "EXHAUSTED"},
            {"source": "indeed", "status": "PARTIAL", "stop_reason": "LOGIN_REQUIRED"},
        ],
        applied_filters={"text": "java", "source": "", "match": "review"},
    )

    assert "# Relatorio de vagas" in report
    assert "## Mais compativeis (1)" in report
    assert "## A revisar (2)" in report
    assert "## Dados insuficientes (0)" in report
    assert "## Fora do perfil (1)" in report
    assert "## Cobertura da coleta" in report
    assert "Completos: 1; parciais: 1; sem vagas: 0; bloqueados ou com erro: 0." in report
    assert "indeed: PARTIAL \\(LOGIN_REQUIRED\\)" in report
    assert "Filtros aplicados:" in report
    assert "texto=java" in report
    assert "aderencia=review" in report
    assert "Dev &lt;script&gt;alert\\(1\\)&lt;/script&gt; \\[Java\\]" in report
    assert "Acme \\| Labs" in report
    assert "[Abrir vaga](https://example.com/vaga?id=1&from=radar)" in report
    assert "javascript:" not in report
    assert "titulo injetado" not in report
    assert "Link indisponivel" in report


def test_markdown_report_puts_jobs_without_fit_in_review_group() -> None:
    from job_radar.export_document import build_markdown_report

    report = build_markdown_report(
        [
            {
                "title": "Vaga sem classificacao",
                "company": None,
                "location": None,
                "source": "portal",
                "canonical_url": "https://example.com/vaga",
                "match_labels": [],
            }
        ],
        generated_at="29/09/2026 10:30",
    )

    assert "## Dados insuficientes (1)" in report
    assert "Empresa nao informada" in report
    assert "Local nao informado" in report


def test_markdown_report_separates_conditional_from_ambiguous() -> None:
    from job_radar.export_document import build_markdown_report

    report = build_markdown_report(
        [
            {"title": "Revisar", "match_labels": ["FIT:CONDITIONAL"]},
            {"title": "Sem dados", "match_labels": ["FIT:AMBIGUOUS"]},
        ],
        generated_at="29/09/2026 10:30",
    )

    assert "## A revisar (1)" in report
    assert "## Dados insuficientes (1)" in report


def test_markdown_report_does_not_describe_empty_or_error_as_partial() -> None:
    from job_radar.export_document import build_markdown_report

    report = build_markdown_report(
        [],
        generated_at="29/09/2026 10:30",
        sources=[
            {"source": "vagas", "status": "EMPTY", "stop_reason": "NO_RESULTS"},
            {"source": "portal", "status": "ERROR", "stop_reason": "FETCH_ERROR"},
            {"source": "indeed", "status": "PARTIAL", "stop_reason": "LOGIN_REQUIRED"},
        ],
    )

    assert "Completos: 0; parciais: 1; sem vagas: 1; bloqueados ou com erro: 1." in report
