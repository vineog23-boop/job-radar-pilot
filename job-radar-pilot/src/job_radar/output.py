from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
from typing import Any
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker

from job_radar.identity import canonicalize_url
from job_radar.models import VacancyRecord
from job_radar.pipeline import PipelineResult


class OutputError(RuntimeError):
    """Indica que as saídas não puderam ser validadas ou publicadas."""


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    line_count: int
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OutputManifest:
    jsonl_path: Path
    csv_path: Path
    report_path: Path
    record_count: int
    discarded: int = 0


_CSV_FIELDS = (
    "source",
    "source_job_id",
    "title",
    "company",
    "location",
    "workplace_model",
    "canonical_url",
    "match_labels",
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _schema_path() -> Path:
    return _project_root() / "schemas" / "vagas.schema.json"


def _workspace_root() -> Path:
    return _project_root().parent


def _upstream_commit() -> str:
    repository = (_workspace_root() / "vendor" / "Scrapling").resolve()
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={repository}",
                "-C",
                str(repository),
                "rev-parse",
                "HEAD",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "desconhecido"
    return result.stdout.strip() or "desconhecido"


def _record_payload(record: VacancyRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["workplace_model"] = record.workplace_model.value
    payload["collection_status"] = record.collection_status.value
    payload["canonical_url"] = record.canonical_url or None
    for field in (
        "technologies",
        "requirements",
        "eligibility_notes",
        "evidence_snippets",
        "match_labels",
    ):
        payload[field] = list(payload[field])
    payload["content_hash"] = None
    canonical = json.dumps(
        {key: value for key, value in payload.items() if key != "content_hash"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    payload["content_hash"] = sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def validate_jsonl(path: Path, schema_path: Path) -> ValidationResult:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    line_count = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return ValidationResult(False, 0, (f"Nao foi possivel ler {path.name}: {exc}",))
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        line_count += 1
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"linha {number}: JSON invalido: {exc.msg}")
            continue
        for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path)):
            errors.append(f"linha {number}: {error.message}")
    return ValidationResult(not errors, line_count, tuple(errors))


def _temp_path(output_dir: Path, name: str) -> Path:
    return output_dir / f".{name}.{uuid4().hex}.tmp"


def _previous_payloads(path: Path, refreshed: set[str]) -> list[dict[str, Any]]:
    """Registros da coleta anterior de fontes que NÃO foram refeitas agora."""

    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return []
    kept: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("source") not in refreshed:
            kept.append(payload)
    return kept


def _previous_report_sources(path: Path, refreshed: set[str]) -> list[dict[str, Any]]:
    try:
        previous = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    sources = previous.get("sources") if isinstance(previous, dict) else None
    if not isinstance(sources, list):
        return []
    return [
        item
        for item in sources
        if isinstance(item, dict) and item.get("source") not in refreshed
    ]


def _csv_text(payloads: Any) -> str:
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_CSV_FIELDS, lineterminator="\r\n")
    writer.writeheader()
    for payload in payloads:
        row = {field: payload.get(field) for field in _CSV_FIELDS}
        row["match_labels"] = ";".join(payload.get("match_labels") or [])
        writer.writerow(row)
    return buffer.getvalue()


def rewrite_payloads(output_dir: Path, payloads: list[dict[str, Any]]) -> None:
    """Reescreve ``vagas.jsonl`` e ``vagas.csv`` com os registros informados.

    Valida o JSONL antes de publicar e atualiza os totais do relatório.
    """

    final_jsonl = output_dir / "vagas.jsonl"
    final_csv = output_dir / "vagas.csv"
    final_report = output_dir / "relatorio-execucao.json"
    temp_jsonl = _temp_path(output_dir, final_jsonl.name)
    temp_csv = _temp_path(output_dir, final_csv.name)
    temp_report = _temp_path(output_dir, final_report.name)
    try:
        with temp_jsonl.open("w", encoding="utf-8", newline="\n") as handle:
            for payload in payloads:
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
                handle.write("\n")
        temp_csv.write_text(_csv_text(payloads), encoding="utf-8", newline="")
        validation = validate_jsonl(temp_jsonl, _schema_path())
        if not validation.valid:
            raise OutputError(
                "JSONL rejeitado pelo schema: " + "; ".join(validation.errors)
            )
        report_written = False
        try:
            report = json.loads(final_report.read_text(encoding="utf-8-sig"))
            report.setdefault("totals", {})["unique"] = len(payloads)
            temp_report.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            report_written = True
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
        os.replace(temp_jsonl, final_jsonl)
        os.replace(temp_csv, final_csv)
        if report_written:
            os.replace(temp_report, final_report)
    finally:
        for temporary in (temp_jsonl, temp_csv, temp_report):
            temporary.unlink(missing_ok=True)


def write_outputs(
    result: PipelineResult,
    output_dir: Path,
    *,
    merge_unrefreshed: bool = False,
    prune: bool = False,
    keep_urls: Any = (),
    max_age_days: int | None = None,
    rules: Any = None,
) -> OutputManifest:
    """Grava JSONL, CSV e relatório.

    Com ``merge_unrefreshed`` (busca parcial), preserva as vagas e o status das
    fontes que não foram consultadas agora, para não apagar a coleta anterior.
    Com ``prune``, vagas inúteis (fora da área, fora do perfil, vencidas) nem
    entram no arquivo; as marcadas em ``keep_urls`` são sempre mantidas.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    final_jsonl = output_dir / "vagas.jsonl"
    final_csv = output_dir / "vagas.csv"
    final_report = output_dir / "relatorio-execucao.json"
    temp_jsonl = _temp_path(output_dir, final_jsonl.name)
    temp_csv = _temp_path(output_dir, final_csv.name)
    temp_report = _temp_path(output_dir, final_report.name)
    temporary_files = (temp_jsonl, temp_csv, temp_report)
    payloads_list = [_record_payload(record) for record in result.records]
    carried_sources: list[dict[str, Any]] = []
    carried_count = 0
    if merge_unrefreshed:
        refreshed = {source.source_code for source in result.source_results}
        carried = _previous_payloads(final_jsonl, refreshed)
        carried_count = len(carried)
        payloads_list.extend(carried)
        carried_sources = _previous_report_sources(final_report, refreshed)
    discarded: dict[str, int] = {}
    if prune:
        from job_radar.cleanup import prune_payloads

        payloads_list, discarded = prune_payloads(
            payloads_list,
            keep_urls=keep_urls,
            max_age_days=max_age_days,
            rules=rules,
        )
    payloads = tuple(payloads_list)

    try:
        with temp_jsonl.open("w", encoding="utf-8", newline="\n") as handle:
            for payload in payloads:
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
                handle.write("\n")

        with temp_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS)
            writer.writeheader()
            for payload in payloads:
                row = {field: payload[field] for field in _CSV_FIELDS}
                row["match_labels"] = ";".join(payload["match_labels"])
                writer.writerow(row)

        report = {
            "scrapling_version": importlib.metadata.version("scrapling"),
            "upstream_commit": _upstream_commit(),
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "totals": {
                "raw": result.raw_record_count + carried_count,
                "unique": len(payloads),
                "ambiguous": len(result.ambiguous),
                "duplicates": result.duplicate_count,
                "discarded": sum(discarded.values()),
                "discarded_by_reason": discarded,
            },
            "sources": carried_sources
            + [
                {
                    "source": source.source_code,
                    "status": source.status.value,
                    "pages_observed": source.pages_observed,
                    "cards_observed": source.cards_observed,
                    "records": len(source.records),
                    "has_more": source.has_more,
                    "stop_reason": source.stop_reason,
                    "errors": list(source.errors),
                    "warnings": list(source.warnings),
                    "visited_urls": [
                        canonicalize_url(url) for url in source.visited_urls
                    ],
                }
                for source in result.source_results
            ],
        }
        temp_report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        validation = validate_jsonl(temp_jsonl, _schema_path())
        if not validation.valid:
            raise OutputError(
                "JSONL rejeitado pelo schema: " + "; ".join(validation.errors)
            )

        os.replace(temp_jsonl, final_jsonl)
        os.replace(temp_csv, final_csv)
        os.replace(temp_report, final_report)
    finally:
        for temporary in temporary_files:
            temporary.unlink(missing_ok=True)

    return OutputManifest(
        final_jsonl,
        final_csv,
        final_report,
        len(payloads),
        sum(discarded.values()),
    )
