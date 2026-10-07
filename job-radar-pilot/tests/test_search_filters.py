from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from job_radar.classifier import classify
from job_radar.models import (
    CollectionStatus,
    SearchProfile,
    SourceRunResult,
    VacancyRecord,
    WorkplaceModel,
)
from job_radar.output import write_outputs
from job_radar.pipeline import PipelineResult
from job_radar.preferences import PreferencesError, preferences_from_dict
from job_radar.presets import (
    STACKS,
    StackError,
    delete_custom_stack,
    load_custom_stacks,
    make_custom_stack,
    presets_payload,
    save_custom_stack,
    suggest,
)
from job_radar.reclassify import insights, reclassify_output, reclassify_payloads

_NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)

PROFILE = SearchProfile(
    positive_keywords=("java", "spring boot"),
    seniority_levels=("junior",),
    location_scopes=("brasil",),
    workplace_models=(WorkplaceModel.REMOTE,),
)


def _record(title="Desenvolvedor Java Júnior", description="Java e Spring Boot.", **extra):
    values = dict(
        source="gupy",
        source_job_id="1",
        canonical_url="https://ats.test/1",
        title=title,
        company="Acme",
        description_summary=description,
        location="Remoto",
        remote_scope="Brasil",
        workplace_model=WorkplaceModel.REMOTE,
    )
    values.update(extra)
    return VacancyRecord(**values)


def _labels(record, profile=PROFILE):
    return set(classify(record, profile, default_country="BR").match_labels)


# --- classificador: refinos do painel ----------------------------------------------


def test_baseline_record_is_ready() -> None:
    assert "FIT:READY" in _labels(_record())


def test_blocked_keyword_anywhere_excludes() -> None:
    profile = replace(PROFILE, blocked_keywords=("cnh",))
    labels = _labels(_record(description="Java. Necessário CNH categoria B."), profile)
    assert "KEYWORD_BLOCKED:cnh" in labels and "FIT:EXCLUDE" in labels


def test_required_keywords_need_at_least_one() -> None:
    profile = replace(PROFILE, required_keywords=("kotlin", "spring boot"))
    assert "KEYWORD_MATCH:spring boot" in _labels(_record(), profile)
    missing = _labels(_record(description="Só Java."), replace(PROFILE, required_keywords=("kotlin",)))
    assert "KEYWORD_MISSING:required" in missing and "FIT:EXCLUDE" in missing


def test_bonus_and_favorite_company_never_exclude() -> None:
    profile = replace(
        PROFILE, bonus_keywords=("aws", "kafka"), favorite_companies=("acme",)
    )
    labels = _labels(_record(description="Java, Spring Boot, AWS e Kafka."), profile)
    assert {"BONUS_MATCH:aws", "BONUS_MATCH:kafka", "COMPANY_FAVORITE:acme"} <= labels
    assert "FIT:READY" in labels


def test_excluded_company_excludes() -> None:
    labels = _labels(_record(company="Consultoria Acme Ltda"), replace(PROFILE, excluded_companies=("acme",)))
    assert "COMPANY_EXCLUDED:acme" in labels and "FIT:EXCLUDE" in labels


@pytest.mark.parametrize(
    "text, accepted, excluded",
    [
        ("Contratação PJ.", ("CLT",), True),
        ("Regime CLT com benefícios.", ("CLT",), False),
        ("Contrato CLT ou PJ, você escolhe.", ("CLT",), False),
        ("Sem falar de contrato.", ("CLT",), False),
        ("Contratação PJ.", (), False),
    ],
)
def test_contract_filter_only_excludes_explicit_mismatch(text, accepted, excluded) -> None:
    labels = _labels(_record(description=f"Java. {text}"), replace(PROFILE, contract_types=accepted))
    assert ("FIT:EXCLUDE" in labels) is excluded


@pytest.mark.parametrize(
    "text, expected, excluded",
    [
        ("Inglês avançado obrigatório.", "LANGUAGE:english_advanced", True),
        ("Fluent English required.", "LANGUAGE:english_advanced", True),
        ("Inglês fluente será um diferencial.", "LANGUAGE:english_plus", False),
        ("Inglês básico.", None, False),
    ],
)
def test_advanced_english(text, expected, excluded) -> None:
    labels = _labels(
        _record(description=f"Java. {text}"), replace(PROFILE, avoid_advanced_english=True)
    )
    if expected:
        assert expected in labels
    else:
        assert not any(label.startswith("LANGUAGE") for label in labels)
    assert ("FIT:EXCLUDE" in labels) is excluded
    # sem a opção marcada, o rótulo informa mas não exclui
    assert "FIT:EXCLUDE" not in _labels(_record(description=f"Java. {text}"))


def test_title_excluded_term_is_not_reported_as_level() -> None:
    labels = _labels(
        _record(title="Desenvolvedor Java Júnior - Vendas"), replace(PROFILE, excluded_terms=("vendas", "senior"))
    )
    assert "TITLE_EXCLUDED:vendas" in labels
    assert not any(label.startswith("SENIORITY_MISMATCH") for label in labels)
    assert "FIT:EXCLUDE" in labels


# --- preferências ---------------------------------------------------------------------


def _prefs_payload(**extra):
    payload = {
        "search_terms": ["java junior"],
        "seniority_levels": ["junior"],
        "workplace_models": [],
        "location_scopes": ["brasil"],
    }
    payload.update(extra)
    return payload


def test_preferences_accept_refinements_and_normalize() -> None:
    prefs = preferences_from_dict(
        _prefs_payload(
            required_keywords=["Java", " java "],
            contract_types=["clt", "PJ"],
            avoid_advanced_english=True,
            excluded_companies=["Acme"],
        )
    )
    assert prefs.required_keywords == ("java",)
    assert prefs.contract_types == ("CLT", "PJ")
    assert prefs.avoid_advanced_english is True
    assert prefs.excluded_companies == ("acme",)


@pytest.mark.parametrize(
    "extra",
    [
        {"contract_types": ["estagio"]},
        {"avoid_advanced_english": "sim"},
        {"bonus_keywords": ["x" * 81]},
        {"required_keywords": [f"t{i}" for i in range(21)]},
    ],
)
def test_preferences_reject_invalid_refinements(extra) -> None:
    with pytest.raises(PreferencesError):
        preferences_from_dict(_prefs_payload(**extra))


# --- stacks ---------------------------------------------------------------------------


def test_preset_catalog_has_many_unique_stacks() -> None:
    ids = [stack.id for stack in STACKS]
    assert len(ids) >= 25 and len(ids) == len(set(ids))
    assert {"fullstack", "kotlin", "ia", "seguranca", "sap", "lowcode"} <= set(ids)


def test_custom_stack_lifecycle_and_suggestions(tmp_path: Path) -> None:
    prefs_path = tmp_path / "search-preferences.json"
    stack = make_custom_stack("Java + Angular", "java, spring boot, angular", "java angular")
    assert stack.id == "custom-java-angular"
    save_custom_stack(prefs_path, stack)
    # mesmo nome substitui, não duplica
    save_custom_stack(prefs_path, make_custom_stack("Java + Angular", ["java", "angular", "rxjs"]))
    loaded = load_custom_stacks(prefs_path)
    assert [item.id for item in loaded] == ["custom-java-angular"]
    assert loaded[0].queries == ("java", "angular")  # sem termos: usa as 2 primeiras

    payload = presets_payload(loaded)
    assert payload["stacks"][-1]["custom"] is True
    result = suggest(["custom-java-angular"], ["junior"], loaded)
    assert "rxjs" in result["technologies"]
    assert "java junior" in result["search_terms"]

    delete_custom_stack(prefs_path, "custom-java-angular")
    assert load_custom_stacks(prefs_path) == ()
    with pytest.raises(StackError):
        delete_custom_stack(prefs_path, "custom-java-angular")


@pytest.mark.parametrize(
    "label, techs",
    [("", "java"), ("Nome", ""), ("Python", "python"), ("x" * 41, "java")],
)
def test_custom_stack_validation(tmp_path: Path, label, techs) -> None:
    with pytest.raises(StackError):
        save_custom_stack(tmp_path / "p.json", make_custom_stack(label, techs))


# --- reaplicar às vagas salvas ---------------------------------------------------------


def _write(records, output: Path) -> None:
    write_outputs(
        PipelineResult(
            started_at="2026-09-30T12:00:00+00:00",
            finished_at="2026-09-30T12:01:00+00:00",
            records=tuple(records),
            ambiguous=(),
            source_results=(SourceRunResult("gupy", CollectionStatus.SUCCESS, tuple(records)),),
            raw_record_count=len(records),
            duplicate_count=0,
        ),
        output,
    )


def _saved_records():
    first = classify(_record(), PROFILE, default_country="BR")
    first = replace(first, match_labels=tuple(sorted({*first.match_labels, "STATUS:NEW", "ALSO_SEEN_IN:indeed"})))
    second = classify(
        _record(
            canonical_url="https://ats.test/2",
            source_job_id="2",
            company="Outra",
            description="Java, Spring Boot e AWS. Contratação PJ.",
            technologies=("docker", "aws"),
        ),
        PROFILE,
        default_country="BR",
    )
    return [first, second]


def test_reclassify_keeps_non_classifier_labels(tmp_path: Path) -> None:
    _write(_saved_records(), tmp_path)
    profile = replace(PROFILE, contract_types=("CLT",), bonus_keywords=("aws",))
    preview = reclassify_output(tmp_path, profile, {"gupy": "BR"}, dry_run=True)
    assert preview["dry_run"] is True
    assert preview["exclude"] == 1 and preview["by_preferences"] == 1 and preview["changed"] == 1
    untouched = (tmp_path / "vagas.jsonl").read_text(encoding="utf-8")
    assert "CONTRACT_MISMATCH" not in untouched  # prévia não grava

    done = reclassify_output(tmp_path, profile, {"gupy": "BR"})
    lines = [json.loads(line) for line in (tmp_path / "vagas.jsonl").read_text(encoding="utf-8").splitlines()]
    first, second = sorted(lines, key=lambda item: item["canonical_url"])
    assert {"STATUS:NEW", "ALSO_SEEN_IN:indeed", "FIT:READY"} <= set(first["match_labels"])
    assert "CONTRACT_MISMATCH:PJ" in second["match_labels"] and "FIT:EXCLUDE" in second["match_labels"]
    assert done["ready"] == 1


def test_insights_suggest_missing_technologies(tmp_path: Path) -> None:
    payloads = reclassify_payloads(
        [
            {**json.loads(json.dumps(_payload)), "canonical_url": f"https://ats.test/{i}"}
            for i, _payload in enumerate(
                [
                    {"source": "gupy", "canonical_url": "x", "title": "Dev Java", "company": "Acme",
                     "technologies": ["kafka", "java"], "match_labels": []},
                    {"source": "gupy", "canonical_url": "y", "title": "Dev Java", "company": "Acme",
                     "technologies": ["kafka", "react"], "match_labels": []},
                ]
            )
        ],
        PROFILE,
    )
    result = insights(payloads, PROFILE)
    terms = {item["term"]: item["count"] for item in result["technologies"]}
    assert terms == {"kafka": 2}  # java já está no perfil; react aparece 1 vez só


# --- API --------------------------------------------------------------------------------


def _server(tmp_path: Path):
    from job_radar.webapp import SearchController, create_server

    static_dir = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
    output = tmp_path / "output"
    output.mkdir(exist_ok=True)
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(output, runner=lambda *_: 0),
        static_dir,
        preferences_path=tmp_path / "search-preferences.json",
        tracking_path=tmp_path / "tracking.json",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}"


def _call(url: str, method: str = "GET", payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url, data=data, headers={"Content-Type": "application/json"} if data else {}, method=method
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def test_api_stacks_preview_reapply_and_insights(tmp_path: Path) -> None:
    _write(_saved_records(), tmp_path / "output")
    server, thread, base = _server(tmp_path)
    try:
        created_status, created = _call(
            f"{base}/api/stacks", "POST", {"label": "Meu Back", "technologies": "java, quarkus"}
        )
        bad_status, _ = _call(f"{base}/api/stacks", "POST", {"label": "", "technologies": "x"})
        _, presets = _call(f"{base}/api/presets")
        _, suggestion = _call(f"{base}/api/presets/suggest?stacks=custom-meu-back&levels=junior")
        delete_status, _ = _call(f"{base}/api/stacks/delete", "POST", {"id": "custom-meu-back"})

        prefs = {
            "search_terms": ["java junior"],
            "seniority_levels": ["junior"],
            "workplace_models": ["REMOTE"],
            "location_scopes": ["brasil"],
            "technologies": ["java", "spring boot"],
            "contract_types": ["CLT"],
        }
        preview_status, preview = _call(f"{base}/api/preferences/preview", "POST", prefs)
        save_status, saved = _call(f"{base}/api/preferences?reapply=1", "PUT", prefs)
        _, insight = _call(f"{base}/api/preferences/insights")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert created_status == 200 and created["created"] == "custom-meu-back"
    assert bad_status == 400
    assert presets["stacks"][-1]["id"] == "custom-meu-back"
    assert "quarkus" in suggestion["technologies"]
    assert delete_status == 200
    assert preview_status == 200 and preview["dry_run"] is True and preview["exclude"] == 1
    assert save_status == 200 and saved["reapplied"]["exclude"] == 1
    assert {"technologies", "companies"} <= set(insight)


def test_api_tracking_insights(tmp_path: Path) -> None:
    from job_radar.tracking import TrackingStore

    _write(_saved_records(), tmp_path / "output")
    store = TrackingStore(tmp_path / "tracking.json")
    store.set_status("https://ats.test/1", "SAVED", now=_NOW)
    store.set_status("https://ats.test/2", "DISCARDED", now=_NOW)
    server, thread, base = _server(tmp_path)
    try:
        status, payload = _call(f"{base}/api/tracking/insights")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 200
    assert payload["sample"] == {"saved": 1, "discarded": 1}
    assert {"companies_avoid", "companies_favorite", "keywords_avoid", "keywords_favorite"} <= set(payload)


def test_dashboard_custom_stack_tags_and_impact(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    _write(_saved_records(), tmp_path / "output")
    server, thread, base = _server(tmp_path)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("dialog", lambda dialog: dialog.accept())
            page.goto(f"{base}/")
            page.get_by_role("button", name="Configurar busca").click()
            page.locator("#stack-chips .chip").first.wait_for()
            assert page.locator("#stack-chips .chip").count() >= 25

            # cria uma stack própria e usa nas sugestões
            page.get_by_role("button", name="+ Criar stack").click()
            page.locator("#new-stack-label").fill("Java + Angular")
            page.locator("#new-stack-techs").fill("java, angular, rxjs")
            page.get_by_role("button", name="Salvar stack").click()
            page.get_by_text('Stack "Java + Angular" criada').wait_for()
            assert page.locator('[data-stack="custom-java-angular"]').get_attribute("aria-pressed") == "true"
            page.get_by_role("button", name="Preencher sugestões").click()
            page.wait_for_function("() => document.querySelector('#technologies').value.includes('rxjs')")
            assert page.locator(".tag", has_text="rxjs").count() == 1

            # etiquetas: Enter adiciona, × remove (filtros avançados ficam recolhidos)
            page.evaluate("document.querySelector('#refine-details').open = true")
            entry = page.locator("#bonus-keywords-entry")
            entry.fill("aws")
            entry.press("Enter")
            entry.fill("kafka, docker")
            entry.press("Enter")
            assert page.locator("#bonus-keywords").input_value() == "aws\nkafka\ndocker"
            page.get_by_role("button", name="Remover docker").click()
            assert page.locator("#bonus-keywords").input_value() == "aws\nkafka"

            # filtro fino + impacto antes de salvar
            page.locator("#contract-clt").check()
            page.get_by_role("button", name="Ver impacto").click()
            page.get_by_text("Com estas configurações:").wait_for()
            assert "cortadas pelos filtros finos" in page.locator("#preferences-impact").inner_text()

            page.get_by_role("button", name="Salvar configurações").click()
            page.get_by_text("Reaplicado às vagas salvas:").wait_for()

            # a stack personalizada pode ser excluída
            page.get_by_role("button", name="Excluir a stack Java + Angular").click()
            page.get_by_text('Stack "Java + Angular" excluída.').wait_for()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    saved = json.loads((tmp_path / "search-preferences.json").read_text(encoding="utf-8"))
    assert saved["bonus_keywords"] == ["aws", "kafka"]
    assert saved["contract_types"] == ["CLT"]
