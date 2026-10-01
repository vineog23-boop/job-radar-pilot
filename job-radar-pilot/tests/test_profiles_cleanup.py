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
from job_radar.cleanup import clean_output, discard_reason, prune_payloads
from job_radar.models import (
    CollectionStatus,
    SearchProfile,
    SourceRunResult,
    VacancyRecord,
    WorkplaceModel,
)
from job_radar.output import write_outputs
from job_radar.pipeline import PipelineResult
from job_radar.preferences import (
    PreferencesError,
    SearchPreferences,
    apply_preferences,
    preferences_from_dict,
)
from job_radar.presets import STACKS, presets_payload, suggest
from job_radar.profiles import (
    activate_profile,
    active_profile,
    delete_profile,
    list_profiles,
    save_profile,
)

NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def _prefs(**overrides) -> SearchPreferences:
    values = {
        "search_terms": ("python pleno",),
        "seniority_levels": ("pleno",),
        "workplace_models": (),
        "location_scopes": ("brasil",),
        "technologies": ("python", "django"),
        "excluded_terms": (),
    }
    values.update(overrides)
    return SearchPreferences(**values)


def _record(title: str, url: str, labels=(), **extra) -> VacancyRecord:
    values = dict(
        source="gupy",
        source_job_id=url[-1],
        canonical_url=url,
        title=title,
        company="Acme",
        description_summary="Vaga de software",
        location="São Paulo, SP",
        workplace_model=WorkplaceModel.REMOTE,
        observed_at="2026-09-29T12:00:00+00:00",
        evidence_snippets=(title,),
        match_labels=tuple(labels),
        collection_status=CollectionStatus.SUCCESS,
    )
    values.update(extra)
    return VacancyRecord(**values)


# --- presets ---------------------------------------------------------------


def test_presets_payload_lists_levels_and_all_stacks() -> None:
    payload = presets_payload()

    assert [level["id"] for level in payload["levels"]] == [
        "estagio",
        "junior",
        "pleno",
        "senior",
    ]
    assert {stack["id"] for stack in payload["stacks"]} == {s.id for s in STACKS}
    assert all(stack["technologies"] and stack["queries"] for stack in payload["stacks"])


def test_suggest_combines_stacks_and_levels_within_limit() -> None:
    result = suggest(["python", "java"], ["junior", "pleno"])

    assert "python junior" in result["search_terms"]
    assert "spring boot pleno" in result["search_terms"]
    assert len(result["search_terms"]) <= 20
    assert "django" in result["technologies"] and "jpa" in result["technologies"]


def test_suggest_ignores_unknown_ids_and_works_without_levels() -> None:
    result = suggest(["nao-existe", "qa"], ["mestre"])

    # sem nível: primeiro as consultas da stack, depois os cargos
    assert result["search_terms"][:2] == ["qa", "analista de testes"]
    assert "analista de qa" in result["search_terms"]


# --- níveis no classificador e nas preferências --------------------------------


def test_mid_level_profile_matches_pleno_and_rejects_junior_only_titles() -> None:
    profile = SearchProfile(
        positive_keywords=("python", "django"),
        seniority_levels=("pleno",),
        location_scopes=("brasil",),
        excluded_terms=("pleno", "senior"),  # o "pleno" não pode excluir quem quer pleno
    )

    pleno = classify(_record("Desenvolvedor Python Pleno", "https://x.com/1"), profile)
    junior = classify(_record("Desenvolvedor Python Júnior", "https://x.com/2"), profile)
    senior = classify(_record("Desenvolvedor Python Sênior", "https://x.com/3"), profile)

    assert "SENIORITY_MATCH:pleno" in pleno.match_labels
    assert "SENIORITY_MISMATCH:pleno" not in pleno.match_labels
    assert "FIT:READY" in pleno.match_labels
    assert "FIT:EXCLUDE" in junior.match_labels
    assert "FIT:EXCLUDE" in senior.match_labels


def test_junior_pleno_range_still_fits_a_pleno_profile() -> None:
    profile = SearchProfile(
        positive_keywords=("python",),
        seniority_levels=("pleno",),
        location_scopes=("brasil",),
    )

    result = classify(_record("Desenvolvedor Python Júnior/Pleno", "https://x.com/4"), profile)

    assert "FIT:EXCLUDE" not in result.match_labels


def test_non_java_stack_counts_as_core_technology() -> None:
    profile = SearchProfile(
        positive_keywords=("python", "docker"),
        seniority_levels=("junior",),
        location_scopes=("brasil",),
    )

    result = classify(
        _record("Desenvolvedor Python Júnior", "https://x.com/5"), profile
    )

    assert "FIT:READY" in result.match_labels
    assert "RELEVANCE:OFF_TOPIC" not in result.match_labels


def test_preferences_accept_four_levels_and_reject_unknown() -> None:
    prefs = preferences_from_dict(
        {
            "search_terms": ["java"],
            "seniority_levels": ["estagio", "junior", "pleno", "senior"],
            "workplace_models": [],
            "location_scopes": ["brasil"],
        }
    )
    assert prefs.seniority_levels == ("estagio", "junior", "pleno", "senior")
    with pytest.raises(PreferencesError):
        _prefs(seniority_levels=("guru",))


def test_apply_preferences_drops_selected_levels_and_leadership_for_senior() -> None:
    profile = SearchProfile(
        positive_keywords=("java",),
        seniority_levels=("junior",),
        location_scopes=("brasil",),
        excluded_terms=("pleno", "senior", "tech lead", "estagio rh"),
    )

    mid = apply_preferences(profile, _prefs(seniority_levels=("pleno",)))
    senior = apply_preferences(profile, _prefs(seniority_levels=("senior",)))

    assert "pleno" not in mid.excluded_terms and "senior" in mid.excluded_terms
    assert "senior" not in senior.excluded_terms
    assert "tech lead" not in senior.excluded_terms
    assert "estagio rh" in senior.excluded_terms


# --- limpeza -----------------------------------------------------------------


def test_discard_reason_covers_offtopic_excluded_expired_and_stale() -> None:
    assert discard_reason({"match_labels": ["RELEVANCE:OFF_TOPIC"]}, now=NOW) == "off_topic"
    assert discard_reason({"match_labels": ["FIT:EXCLUDE"]}, now=NOW) == "excluded"
    assert (
        discard_reason(
            {"match_labels": [], "application_deadline": "2026-09-01T00:00:00+00:00"},
            now=NOW,
        )
        == "expired"
    )
    old = {"match_labels": [], "published_at": "2026-05-01T00:00:00+00:00"}
    assert discard_reason(old, now=NOW) is None
    assert discard_reason(old, now=NOW, max_age_days=90) == "stale"
    assert discard_reason({"match_labels": ["FIT:READY"]}, now=NOW, max_age_days=90) is None


def test_prune_keeps_tracked_urls_even_if_useless() -> None:
    jobs = [
        {"canonical_url": "https://x.com/a", "match_labels": ["FIT:EXCLUDE"]},
        {"canonical_url": "https://x.com/b", "match_labels": ["FIT:EXCLUDE"]},
        {"canonical_url": "https://x.com/c", "match_labels": ["FIT:READY"]},
    ]

    kept, removed = prune_payloads(jobs, keep_urls={"https://x.com/a"}, now=NOW)

    assert [job["canonical_url"] for job in kept] == [
        "https://x.com/a",
        "https://x.com/c",
    ]
    assert removed == {"excluded": 1}


def _result(records) -> PipelineResult:
    return PipelineResult(
        started_at="2026-09-29T12:00:00+00:00",
        finished_at="2026-09-29T12:01:00+00:00",
        records=tuple(records),
        ambiguous=(),
        source_results=(
            SourceRunResult(
                source_code="gupy",
                status=CollectionStatus.SUCCESS,
                records=tuple(records),
                pages_observed=1,
                cards_observed=len(records),
            ),
        ),
        raw_record_count=len(records),
        duplicate_count=0,
    )


def _mixed_records():
    return [
        _record("Dev Java", "https://x.com/1", ["FIT:READY"]),
        _record("Auxiliar", "https://x.com/2", ["FIT:AMBIGUOUS", "RELEVANCE:OFF_TOPIC"]),
        _record("Dev Sênior", "https://x.com/3", ["FIT:EXCLUDE"]),
    ]


def test_write_outputs_with_prune_drops_useless_and_reports_counts(tmp_path: Path) -> None:
    manifest = write_outputs(_result(_mixed_records()), tmp_path, prune=True)

    lines = [
        json.loads(line)
        for line in manifest.jsonl_path.read_text(encoding="utf-8").splitlines()
    ]
    report = json.loads(manifest.report_path.read_text(encoding="utf-8"))

    assert [line["title"] for line in lines] == ["Dev Java"]
    assert manifest.discarded == 2
    assert report["totals"]["discarded_by_reason"] == {"off_topic": 1, "excluded": 1}


def test_write_outputs_prune_keeps_tracked(tmp_path: Path) -> None:
    manifest = write_outputs(
        _result(_mixed_records()),
        tmp_path,
        prune=True,
        keep_urls={"https://x.com/3"},
    )

    titles = [
        json.loads(line)["title"]
        for line in manifest.jsonl_path.read_text(encoding="utf-8").splitlines()
    ]
    assert titles == ["Dev Java", "Dev Sênior"]


def test_clean_output_dry_run_then_real_cleanup(tmp_path: Path) -> None:
    write_outputs(_result(_mixed_records()), tmp_path)  # sem prune: guarda tudo

    preview = clean_output(tmp_path, dry_run=True)
    assert preview["before"] == 3 and preview["after"] == 1
    assert len((tmp_path / "vagas.jsonl").read_text(encoding="utf-8").splitlines()) == 3

    done = clean_output(tmp_path, keep_urls={"https://x.com/2"})
    lines = (tmp_path / "vagas.jsonl").read_text(encoding="utf-8").splitlines()
    assert done["after"] == 2 and len(lines) == 2
    assert "Dev Java" in (tmp_path / "vagas.csv").read_text(encoding="utf-8")
    report = json.loads((tmp_path / "relatorio-execucao.json").read_text(encoding="utf-8"))
    assert report["totals"]["unique"] == 2


def test_clean_output_without_file_is_a_noop(tmp_path: Path) -> None:
    assert clean_output(tmp_path)["before"] == 0


# --- perfis nomeados -----------------------------------------------------------


def test_profiles_save_activate_list_and_delete(tmp_path: Path) -> None:
    path = tmp_path / "search-preferences.json"

    name = save_profile(path, "  Python  Pleno  ", _prefs())
    save_profile(path, "Java Júnior", _prefs(seniority_levels=("junior",)))
    assert name == "Python Pleno"

    activated = activate_profile(path, "Java Júnior")
    assert activated.seniority_levels == ("junior",)
    assert json.loads(path.read_text(encoding="utf-8"))["seniority_levels"] == ["junior"]
    assert active_profile(path) == "Java Júnior"
    listed = {item["name"]: item["active"] for item in list_profiles(path)}
    assert listed == {"Java Júnior": True, "Python Pleno": False}

    delete_profile(path, "Java Júnior")
    assert active_profile(path) is None
    assert [item["name"] for item in list_profiles(path)] == ["Python Pleno"]


@pytest.mark.parametrize("bad_name", ["", "   ", "a/b", "x" * 41, "***", 7])
def test_profiles_reject_invalid_names(tmp_path: Path, bad_name) -> None:
    with pytest.raises(PreferencesError):
        save_profile(tmp_path / "p.json", bad_name, _prefs())


def test_activate_missing_profile_fails(tmp_path: Path) -> None:
    with pytest.raises(PreferencesError):
        activate_profile(tmp_path / "p.json", "Inexistente")


# --- API ---------------------------------------------------------------------


def _server(tmp_path: Path, *, running=False):
    from job_radar.webapp import SearchController, create_server

    static_dir = tmp_path / "web"
    static_dir.mkdir(exist_ok=True)
    output = tmp_path / "output"
    output.mkdir(exist_ok=True)
    controller = SearchController(output, runner=lambda *_: 0)
    server = create_server(
        "127.0.0.1",
        0,
        controller,
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
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def test_api_presets_and_suggest(tmp_path: Path) -> None:
    server, thread, base = _server(tmp_path)
    try:
        status, presets = _call(f"{base}/api/presets")
        _, suggestion = _call(f"{base}/api/presets/suggest?stacks=java,python&levels=junior")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 200 and len(presets["stacks"]) == len(STACKS)
    assert "java junior" in suggestion["search_terms"]


def test_api_profiles_round_trip(tmp_path: Path) -> None:
    server, thread, base = _server(tmp_path)
    payload = {
        "search_terms": ["python pleno"],
        "seniority_levels": ["pleno"],
        "workplace_models": ["REMOTE"],
        "location_scopes": ["brasil"],
        "technologies": ["python"],
        "excluded_terms": [],
    }
    try:
        status, saved = _call(
            f"{base}/api/profiles", "PUT", {"name": "Python Pleno", "preferences": payload}
        )
        _, current = _call(f"{base}/api/preferences")
        bad_status, _ = _call(
            f"{base}/api/profiles", "PUT", {"name": "", "preferences": payload}
        )
        missing_status, _ = _call(
            f"{base}/api/profiles/activate", "POST", {"name": "Nada"}
        )
        _, after_delete = _call(
            f"{base}/api/profiles/delete", "POST", {"name": "Python Pleno"}
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 200 and saved["active"] == "Python Pleno"
    assert saved["preferences"]["seniority_levels"] == ["pleno"]
    assert current["seniority_levels"] == ["pleno"]
    assert bad_status == 400 and missing_status == 400
    assert after_delete["profiles"] == [] and after_delete["active"] is None


def test_api_cleanup_removes_useless_but_keeps_tracked(tmp_path: Path) -> None:
    write_outputs(_result(_mixed_records()), tmp_path / "output")
    server, thread, base = _server(tmp_path)
    try:
        _put = Request(
            f"{base}/api/tracking",
            data=json.dumps({"url": "https://x.com/3", "status": "SAVED"}).encode(),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        urlopen(_put, timeout=3).read()
        preview_status, preview = _call(f"{base}/api/cleanup", "POST", {"dry_run": True})
        bad_status, _ = _call(f"{base}/api/cleanup", "POST", {"max_age_days": 0})
        status, result = _call(f"{base}/api/cleanup", "POST", {})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert preview_status == 200 and preview["dry_run"] is True
    assert bad_status == 400
    assert status == 200 and result["before"] == 3 and result["after"] == 2
    titles = [
        json.loads(line)["title"]
        for line in (tmp_path / "output" / "vagas.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert titles == ["Dev Java", "Dev Sênior"]


# --- painel (navegador real) -----------------------------------------------------


def test_dashboard_panel_stacks_profiles_and_cleanup(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    write_outputs(_result(_mixed_records()), output)
    static_dir = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
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
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("dialog", lambda dialog: dialog.accept())
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.get_by_role("button", name="Configurar busca").click()
            page.locator("#stack-chips .chip").first.wait_for()

            # níveis pleno/sênior existem e stacks preenchem termos + tecnologias
            assert page.locator("#seniority-mid").count() == 1
            assert page.locator("#seniority-senior").count() == 1
            page.locator("#seniority-internship").uncheck()
            page.locator("#seniority-junior").uncheck()
            page.locator("#seniority-mid").check()
            page.locator('#stack-chips .chip[data-stack="python"]').click()
            page.get_by_role("button", name="Preencher sugestões").click()
            page.wait_for_function(
                "() => document.querySelector('#search-terms').value.includes('python pleno')"
            )
            assert "django" in page.locator("#technologies").input_value()

            # atalho de localidade + salvar como perfil
            page.locator('[data-location="brasil"]').click()
            assert "brasil" in page.locator("#location-scopes").input_value()
            page.locator("#profile-name").fill("Python Pleno")
            page.get_by_role("button", name="Salvar como perfil").click()
            page.get_by_text('Perfil "Python Pleno" salvo e ativado.').wait_for()
            assert page.locator("#profile-select").input_value() == "Python Pleno"
            saved = json.loads(
                (tmp_path / "search-preferences.json").read_text(encoding="utf-8")
            )
            assert saved["seniority_levels"] == ["pleno"]

            # limpeza: menu próprio, prévia e execução
            page.get_by_role("button", name="Limpeza", exact=True).click()
            page.locator("#cleanup-panel").wait_for()
            page.get_by_text("2 seriam removidas agora").wait_for()
            page.get_by_role("button", name="Ver o que seria removido").click()
            page.get_by_text("2 de 3 vagas seriam removidas").wait_for()
            page.get_by_role("button", name="Limpar agora").click()
            page.get_by_text("Restam 1 vagas.").wait_for()
            page.locator("#undo-box").wait_for(state="visible")
            assert page.locator("#cleanup-undo").is_visible()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    remaining = (output / "vagas.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(remaining) == 1


# --- regras de descarte configuráveis -------------------------------------------


def test_rules_disable_individual_reasons() -> None:
    from job_radar.cleanup import CleanupRules

    off_topic = {"match_labels": ["RELEVANCE:OFF_TOPIC"]}
    excluded = {"match_labels": ["FIT:EXCLUDE"]}
    expired = {"match_labels": [], "application_deadline": "2026-09-01T00:00:00+00:00"}
    rules = CleanupRules(off_topic=False, excluded=True, expired=False)

    assert discard_reason(off_topic, now=NOW, rules=rules) is None
    assert discard_reason(excluded, now=NOW, rules=rules) == "excluded"
    assert discard_reason(expired, now=NOW, rules=rules) is None


def test_rules_validation_and_persistence(tmp_path: Path) -> None:
    from job_radar.cleanup import (
        CleanupError,
        CleanupRules,
        load_rules,
        rules_from_dict,
        save_rules,
    )

    prefs = tmp_path / "search-preferences.json"
    assert load_rules(prefs) == CleanupRules()  # sem arquivo: padrão seguro

    save_rules(prefs, CleanupRules(off_topic=False, max_age_days=60))
    assert load_rules(prefs) == CleanupRules(off_topic=False, max_age_days=60)

    (tmp_path / "cleanup-rules.json").write_text("{quebrado", encoding="utf-8")
    assert load_rules(prefs) == CleanupRules()

    for bad in ({"off_topic": "sim"}, {"max_age_days": 0}, {"max_age_days": True}, {"x": 1}):
        with pytest.raises(CleanupError):
            rules_from_dict(bad)


def test_write_outputs_respects_rules(tmp_path: Path) -> None:
    from job_radar.cleanup import CleanupRules

    manifest = write_outputs(
        _result(_mixed_records()),
        tmp_path,
        prune=True,
        rules=CleanupRules(off_topic=False),
    )

    titles = [
        json.loads(line)["title"]
        for line in manifest.jsonl_path.read_text(encoding="utf-8").splitlines()
    ]
    assert titles == ["Dev Java", "Auxiliar"]


def test_api_cleanup_rules_round_trip_and_used_by_cleanup(tmp_path: Path) -> None:
    write_outputs(_result(_mixed_records()), tmp_path / "output")
    server, thread, base = _server(tmp_path)
    try:
        _, defaults = _call(f"{base}/api/cleanup/rules")
        status, saved = _call(
            f"{base}/api/cleanup/rules",
            "PUT",
            {"off_topic": False, "excluded": True, "expired": True, "max_age_days": None},
        )
        bad_status, _ = _call(f"{base}/api/cleanup/rules", "PUT", {"max_age_days": 5000})
        _, preview = _call(f"{base}/api/cleanup", "POST", {"dry_run": True})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert defaults["off_topic"] is True and "off_topic" in defaults["reasons"]
    assert status == 200 and saved["off_topic"] is False
    assert bad_status == 400
    assert preview["removed"] == {"excluded": 1}
    assert preview["removed_labels"]["excluded"].startswith("fora do seu perfil")


def test_dashboard_exclusions_section_saves_rules_and_shows_breakdown(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    write_outputs(_result(_mixed_records()), output)
    static_dir = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
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
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.get_by_role("button", name="Limpeza", exact=True).click()
            page.locator("#rule-off-topic").wait_for()
            page.wait_for_function("() => document.querySelector('#rule-off-topic').checked")
            assert page.get_by_role("heading", name="Manter a lista só com o que presta").is_visible()

            page.locator("#rule-off-topic").uncheck()
            page.get_by_text("Regras salvas").wait_for()
            saved = json.loads(
                (tmp_path / "cleanup-rules.json").read_text(encoding="utf-8")
            )
            assert saved["off_topic"] is False

            page.get_by_role("button", name="Ver o que seria removido").click()
            page.get_by_text("1 de 3 vagas seriam removidas.").wait_for()
            assert "fora do seu perfil" in page.locator("#cleanup-breakdown").inner_text()
            assert "Dev Sênior" in page.locator("#cleanup-samples").inner_text()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

# --- limpeza: descartadas, amostras, backup e desfazer ---------------------------


def test_clean_output_remove_urls_samples_backup_and_undo(tmp_path: Path) -> None:
    from job_radar.cleanup import CleanupError, backup_info, undo_cleanup

    write_outputs(_result(_mixed_records()), tmp_path)

    preview = clean_output(
        tmp_path, keep_urls={"https://x.com/1"}, remove_urls={"https://x.com/1"}, dry_run=True
    )
    assert preview["removed"]["user_discarded"] == 1
    assert {sample["title"] for sample in preview["samples"]} >= {"Dev Java"}
    assert backup_info(tmp_path) is None  # prévia nunca grava backup

    done = clean_output(
        tmp_path, keep_urls={"https://x.com/2"}, remove_urls={"https://x.com/1"}
    )
    assert done["before"] == 3 and done["after"] == 1
    titles = [
        json.loads(line)["title"]
        for line in (tmp_path / "vagas.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert titles == ["Auxiliar"]
    info = backup_info(tmp_path)
    assert info is not None and info["jobs"] == 2

    restored = undo_cleanup(tmp_path)
    assert restored == {"restored": 2, "total": 3}
    assert backup_info(tmp_path) is None
    with pytest.raises(CleanupError):
        undo_cleanup(tmp_path)


def test_api_cleanup_remove_discarded_status_and_undo(tmp_path: Path) -> None:
    write_outputs(_result(_mixed_records()), tmp_path / "output")
    server, thread, base = _server(tmp_path)
    try:
        for url, status in (("https://x.com/1", "DISCARDED"), ("https://x.com/3", "SAVED")):
            put = Request(
                f"{base}/api/tracking",
                data=json.dumps({"url": url, "status": status}).encode(),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            urlopen(put, timeout=3).read()

        _, empty = _call(f"{base}/api/cleanup/status")
        no_undo_status, _ = _call(f"{base}/api/cleanup/undo", "POST", {})
        _, without = _call(f"{base}/api/cleanup", "POST", {"dry_run": True})
        _, with_discarded = _call(
            f"{base}/api/cleanup", "POST", {"dry_run": True, "remove_discarded": True}
        )
        done_status, done = _call(
            f"{base}/api/cleanup", "POST", {"remove_discarded": True}
        )
        _, after = _call(f"{base}/api/cleanup/status")
        undo_status, undone = _call(f"{base}/api/cleanup/undo", "POST", {})
        _, final = _call(f"{base}/api/cleanup/status")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert empty == {"backup": None}
    assert no_undo_status == 400
    assert "user_discarded" not in without["removed"]
    assert with_discarded["removed"]["user_discarded"] == 1
    assert done_status == 200 and done["after"] == 1
    assert after["backup"]["jobs"] == 2
    assert undo_status == 200 and undone == {"restored": 2, "total": 3}
    assert final == {"backup": None}


def test_dashboard_cleanup_menu_undo_and_discarded(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    write_outputs(_result(_mixed_records()), output)
    static_dir = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
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
    try:
        put = Request(
            f"http://127.0.0.1:{server.server_port}/api/tracking",
            data=json.dumps({"url": "https://x.com/1", "status": "DISCARDED"}).encode(),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        urlopen(put, timeout=3).read()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("dialog", lambda dialog: dialog.accept())
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.get_by_role("button", name="Limpeza", exact=True).click()
            page.get_by_text("2 seriam removidas agora").wait_for()
            assert page.locator("#undo-box").is_hidden()

            page.locator("#cleanup-discarded").check()
            page.get_by_text("3 seriam removidas agora").wait_for()

            page.get_by_role("button", name="Limpar agora").click()
            page.get_by_text("Restam 0 vagas.").wait_for()
            page.locator("#undo-box").wait_for(state="visible")

            page.get_by_role("button", name="Desfazer última limpeza").click()
            page.get_by_text("3 vagas devolvidas").wait_for()
            assert page.locator("#undo-box").is_hidden()

            page.keyboard.press("Escape")
            page.locator("#cleanup-panel").wait_for(state="hidden")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
