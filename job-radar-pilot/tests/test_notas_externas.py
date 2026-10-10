"""Notas de um avaliador externo (10/10/2026): output/notas.json -> coluna "Nota" no painel.

Contrato: {"versao": 1, "avaliador": "...", "notas": {canonical_url: {"nota": 0-100|null,
"trilha": "...", "eixos": {...}, "motivo": "..."|null}}}."""

from __future__ import annotations

import json
from pathlib import Path

from job_radar.webapp import load_output, output_version


def _write(output: Path, notas: dict | str | None) -> None:
    output.mkdir(parents=True, exist_ok=True)
    jobs = [{"canonical_url": "https://x.com.br/1", "title": "A"}, {"canonical_url": "https://x.com.br/2", "title": "B"}]
    (output / "vagas.jsonl").write_text("\n".join(json.dumps(j) for j in jobs), encoding="utf-8")
    if notas is not None:
        (output / "notas.json").write_text(notas if isinstance(notas, str) else json.dumps(notas), encoding="utf-8")


def test_external_scores_are_attached_by_url(tmp_path: Path) -> None:
    _write(tmp_path, {"versao": 1, "avaliador": "hermes", "notas": {
        "https://x.com.br/1": {"nota": 87, "trilha": "Java júnior", "eixos": {"nivel": 25}, "motivo": None},
    }})
    jobs = {j["canonical_url"]: j for j in load_output(tmp_path)["jobs"]}
    assert jobs["https://x.com.br/1"]["external_score"]["nota"] == 87
    assert "external_score" not in jobs["https://x.com.br/2"]


def test_missing_or_corrupt_scores_never_break_the_panel(tmp_path: Path) -> None:
    _write(tmp_path, None)
    assert len(load_output(tmp_path)["jobs"]) == 2
    _write(tmp_path, "{quebrado")
    result = load_output(tmp_path)
    assert len(result["jobs"]) == 2 and result["read_error"] is None


def test_new_scores_change_the_output_version(tmp_path: Path) -> None:
    _write(tmp_path, None)
    before = output_version(tmp_path)
    (tmp_path / "notas.json").write_text(json.dumps({"versao": 1, "notas": {}}), encoding="utf-8")
    assert output_version(tmp_path) != before


def test_panel_shows_external_score_and_sorts_by_it(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    from test_xlsx_export import _serve

    server, thread = _serve(tmp_path)
    (tmp_path / "output" / "notas.json").write_text(json.dumps({"versao": 1, "avaliador": "hermes", "notas": {
        "https://example.com/vaga/1?a=1&b=2": {"nota": 61, "trilha": "Java júnior", "eixos": {"nível": 25}},
        "https://example.com/vaga/2?a=1&b=2": {"nota": 88, "trilha": "Java júnior", "eixos": {"nível": 25}},
    }}), encoding="utf-8")
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.evaluate("localStorage.removeItem('radar.filters')")
            page.reload()
            page.wait_for_selector("#jobs-table-body tr")
            page.select_option("#sort-order", "score")
            first = page.locator("#jobs-table-body tr").first
            assert "Dev Java 2" in first.inner_text() and "88/100" in first.inner_text()
            page.locator(".title-cell").first.click()
            page.wait_for_selector(".detail-row")
            assert "Nota pelos seus critérios: 88/100 — Java júnior" in page.locator(".detail-row").inner_text()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
