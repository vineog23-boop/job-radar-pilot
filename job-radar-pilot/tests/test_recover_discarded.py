"""Vagas podadas na coleta podem voltar quando o perfil fica mais amplo.

A coleta descarta "fora do perfil"/"fora da área" para não poluir a lista,
mas guarda essas vagas em ``vagas-descartadas-na-coleta.jsonl``. Reaplicar o
perfil (ou só ver o impacto) também as reclassifica e devolve as que passam.
"""

from __future__ import annotations

import json
from pathlib import Path

from job_radar.cleanup import DISCARDED_NAME, CleanupRules
from job_radar.models import CollectionStatus, SearchProfile, SourceRunResult, VacancyRecord
from job_radar.output import write_outputs
from job_radar.pipeline import PipelineResult
from job_radar.reclassify import reclassify_output


def _record(title: str, url: str, labels: list[str], source: str = "gupy", **extra) -> VacancyRecord:
    values = dict(
        source=source,
        source_job_id=url[-1],
        canonical_url=url,
        title=title,
        company="Acme",
        description_summary=extra.pop("description_summary", "Back-end com Java"),
        location="Remoto",
        remote_scope="Brasil",
        observed_at="2026-09-29T12:00:00+00:00",
        match_labels=tuple(labels),
        collection_status=CollectionStatus.SUCCESS,
    )
    values.update(extra)
    return VacancyRecord(**values)


def _result(records, sources=("gupy",)) -> PipelineResult:
    return PipelineResult(
        started_at="2026-09-29T12:00:00+00:00",
        finished_at="2026-09-29T12:01:00+00:00",
        records=tuple(records),
        ambiguous=(),
        source_results=tuple(
            SourceRunResult(
                source_code=code,
                status=CollectionStatus.SUCCESS,
                records=tuple(r for r in records if r.source == code),
            )
            for code in sources
        ),
        raw_record_count=len(records),
        duplicate_count=0,
    )


RECORDS = [
    _record("Desenvolvedor Java Júnior", "https://x.com/1", ["FIT:READY"]),
    _record("Desenvolvedor Java Pleno", "https://x.com/2", ["FIT:EXCLUDE", "SENIORITY_MISMATCH:pleno"]),
    _record(
        "Auxiliar Administrativo",
        "https://x.com/3",
        ["FIT:AMBIGUOUS", "RELEVANCE:OFF_TOPIC"],
        description_summary="Rotinas de escritório",
    ),
]

JUNIOR = SearchProfile(
    positive_keywords=("java",),
    seniority_levels=("junior",),
    location_scopes=("remoto-brasil",),
)
JUNIOR_AND_PLENO = SearchProfile(
    positive_keywords=("java",),
    seniority_levels=("junior", "pleno"),
    location_scopes=("remoto-brasil",),
)
COUNTRIES = {"gupy": "BR", "nube": "BR"}


def _urls(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        json.loads(line)["canonical_url"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_collection_keeps_pruned_jobs_in_discarded_file(tmp_path: Path) -> None:
    write_outputs(_result(RECORDS), tmp_path, prune=True)

    assert _urls(tmp_path / "vagas.jsonl") == ["https://x.com/1"]
    assert sorted(_urls(tmp_path / DISCARDED_NAME)) == ["https://x.com/2", "https://x.com/3"]


def test_reapply_broader_profile_recovers_pruned_job(tmp_path: Path) -> None:
    write_outputs(_result(RECORDS), tmp_path, prune=True)

    preview = reclassify_output(tmp_path, JUNIOR_AND_PLENO, COUNTRIES, dry_run=True)
    assert preview["recovered"] == 1
    assert _urls(tmp_path / "vagas.jsonl") == ["https://x.com/1"]  # prévia não grava

    result = reclassify_output(tmp_path, JUNIOR_AND_PLENO, COUNTRIES)

    assert result["recovered"] == 1
    assert result["total"] == 2
    assert _urls(tmp_path / "vagas.jsonl") == ["https://x.com/1", "https://x.com/2"]
    assert _urls(tmp_path / DISCARDED_NAME) == ["https://x.com/3"]  # fora de TI fica


def test_reapply_same_profile_recovers_nothing(tmp_path: Path) -> None:
    write_outputs(_result(RECORDS), tmp_path, prune=True)

    result = reclassify_output(tmp_path, JUNIOR, COUNTRIES)

    assert result["recovered"] == 0
    assert _urls(tmp_path / "vagas.jsonl") == ["https://x.com/1"]
    assert len(_urls(tmp_path / DISCARDED_NAME)) == 2


def test_reapply_respects_cleanup_rules(tmp_path: Path) -> None:
    write_outputs(_result(RECORDS), tmp_path, prune=True)

    result = reclassify_output(
        tmp_path,
        JUNIOR_AND_PLENO,
        COUNTRIES,
        rules=CleanupRules(off_topic=False),
    )

    # Com "fora de TI" liberado nas regras, ela também volta.
    assert result["recovered"] == 2


def test_partial_run_keeps_discarded_jobs_of_other_sources(tmp_path: Path) -> None:
    first = RECORDS + [
        _record("Dev Java Pleno Nube", "https://y.com/4", ["FIT:EXCLUDE"], source="nube"),
    ]
    write_outputs(_result(first, sources=("gupy", "nube")), tmp_path, prune=True)

    write_outputs(
        _result([RECORDS[0]], sources=("gupy",)),
        tmp_path,
        prune=True,
        merge_unrefreshed=True,
    )

    assert _urls(tmp_path / DISCARDED_NAME) == ["https://y.com/4"]


def test_full_run_without_pruning_clears_discarded_file(tmp_path: Path) -> None:
    write_outputs(_result(RECORDS), tmp_path, prune=True)

    write_outputs(_result(RECORDS), tmp_path, prune=False)

    assert _urls(tmp_path / DISCARDED_NAME) == []
    assert len(_urls(tmp_path / "vagas.jsonl")) == 3


def test_dashboard_preview_and_reapply_report_recovered(tmp_path: Path) -> None:
    from threading import Thread
    from urllib.request import Request, urlopen

    from job_radar.webapp import SearchController, create_server

    output = tmp_path / "output"
    write_outputs(_result(RECORDS), output, prune=True)
    static_dir = tmp_path / "web"
    static_dir.mkdir()
    server = create_server(
        "127.0.0.1",
        0,
        SearchController(output, runner=lambda *_: 0),
        static_dir,
        preferences_path=tmp_path / "prefs" / "search-preferences.json",
        tracking_path=tmp_path / "prefs" / "tracking.json",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    prefs = {
        "search_terms": ["java"],
        "seniority_levels": ["junior", "pleno"],
        "workplace_models": [],
        "location_scopes": ["remoto-brasil"],
        "technologies": ["java"],
    }

    def call(path: str, method: str) -> dict:
        request = Request(
            base + path,
            data=json.dumps(prefs).encode(),
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    try:
        preview = call("/api/preferences/preview", "POST")
        saved = call("/api/preferences?reapply=1", "PUT")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert preview["recovered"] == 1
    assert saved["reapplied"]["recovered"] == 1
    assert "https://x.com/2" in _urls(output / "vagas.jsonl")
