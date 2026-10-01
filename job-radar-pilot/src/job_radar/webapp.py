from __future__ import annotations

import argparse
from contextlib import nullcontext
import csv
import io
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import subprocess
import sys
from threading import Lock, Thread, Timer
from typing import Any, Callable, Sequence
import unicodedata
from urllib.parse import parse_qs, urlsplit
import webbrowser

from job_radar.dates import parse_iso_datetime
from job_radar.export_document import build_markdown_report
from job_radar.fit import fit_name, fit_reasons, fit_state, is_off_topic, job_technologies
from job_radar.output_lock import BUSY_MESSAGE, OutputBusyError, OutputLock
from job_radar.text_cleaning import spreadsheet_safe
from job_radar.tracking import TrackingError, TrackingStore


_PROGRESS_LINE = re.compile(
    r"^(?P<source>[a-z0-9-]+): (?P<status>[A-Z_]+); "
    r"pages=(?P<pages>\d+); cards=(?P<cards>\d+); "
    r"records=(?P<records>\d+); stop=(?P<stop_reason>[A-Z_]+)$"
)


def parse_progress_line(line: str) -> dict[str, Any] | None:
    match = _PROGRESS_LINE.fullmatch(line.strip())
    if match is None:
        return None
    values = match.groupdict()
    return {
        "source": values["source"],
        "status": values["status"],
        "pages": int(values["pages"]),
        "cards": int(values["cards"]),
        "records": int(values["records"]),
        "stop_reason": values["stop_reason"],
    }


def load_output(output_dir: Path) -> dict[str, Any]:
    jobs_path = output_dir / "vagas.jsonl"
    report_path = output_dir / "relatorio-execucao.json"
    jobs: list[dict[str, Any]] = []
    report: dict[str, Any] = {}

    try:
        if jobs_path.exists():
            jobs = [
                json.loads(line)
                for line in jobs_path.read_text(encoding="utf-8-sig").splitlines()
                if line.strip()
            ]
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"jobs": [], "report": {}, "read_error": str(exc)}

    return {"jobs": jobs, "report": report, "read_error": None}


ProgressCallback = Callable[[str], None]
# Mesmo código de cli.EXIT_BUSY (sem importar a CLI inteira no painel).
_EXIT_BUSY = 5
CollectionRunner = Callable[[Path, list[str] | None, int, ProgressCallback], int]


class OutputReadError(RuntimeError):
    """Impede que uma saida local corrompida pareca um relatorio vazio valido."""


def _normalized_search_text(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or "").casefold())
    return " ".join(
        "".join(
            character
            for character in decomposed
            if not unicodedata.combining(character)
        ).split()
    )


# Filtro de acompanhamento: "" = todas, "active" = oculta descartadas.
_TRACKED_FILTERS = {
    "active": None,
    "new": None,
    "saved": "SAVED",
    "applied": "APPLIED",
    "discarded": "DISCARDED",
}
_TRACKING_NAMES = {"SAVED": "Salva", "APPLIED": "Aplicada", "DISCARDED": "Descartada"}
# Filtro de aderência: "" = relevantes (esconde o que não é de TI), "all" = tudo.
_MATCH_FILTERS = {"", "all", "ready", "fit", "review", "otherstack", "exclude", "offtopic"}
_CSV_COLUMNS = (
    "aderencia",
    "acompanhamento",
    "titulo",
    "empresa",
    "local",
    "modalidade",
    "senioridade",
    "tecnologias",
    "publicada_em",
    "fonte",
    "url",
    "nota",
    "motivo",
)


def build_jobs_csv(
    jobs: Sequence[dict[str, Any]],
    tracking: dict[str, dict[str, str]],
) -> bytes:
    """CSV com ';' e BOM para abrir direto no Excel em pt-BR."""
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=_CSV_COLUMNS, delimiter=";", lineterminator="\r\n"
    )
    writer.writeheader()
    for job in jobs:
        entry = tracking.get(str(job.get("canonical_url")), {})
        row = {
            "aderencia": fit_name(job),
            "acompanhamento": _TRACKING_NAMES.get(entry.get("status", ""), ""),
            "titulo": job.get("title") or "",
            "empresa": job.get("company") or "",
            "local": job.get("location") or job.get("remote_scope") or "",
            "modalidade": job.get("workplace_model") or "",
            "senioridade": job.get("seniority") or "",
            "tecnologias": ", ".join(job_technologies(job)),
            "publicada_em": job.get("published_at") or "",
            "fonte": job.get("source") or "",
            "url": job.get("canonical_url") or "",
            "nota": entry.get("note", ""),
            "motivo": "; ".join(fit_reasons(job)),
        }
        writer.writerow({key: spreadsheet_safe(value) for key, value in row.items()})
    return buffer.getvalue().encode("utf-8-sig")


def build_jobs_ai_text(
    jobs: Sequence[dict[str, Any]],
    tracking: dict[str, dict[str, str]],
    filters: Sequence[tuple[str, str]] = (),
    now: datetime | None = None,
) -> bytes:
    """Markdown enxuto, ordenado por score, para colar em outra IA revisar."""

    from job_radar.xlsx_export import WORKPLACE_NAMES, job_score, level_name

    now = now or datetime.now(timezone.utc)
    ranked = sorted(jobs, key=lambda job: -job_score(job, now))
    lines = [
        "# Vagas de TI para revisão",
        "",
        "Cada linha é uma vaga já filtrada pelo perfil do candidato. Score 0-100 "
        "(aderência ao perfil + recência). Revise a coerência de cargo, nível e "
        "modelo de trabalho e aponte as que mais valem a candidatura. Não invente "
        "dados que não estão na tabela.",
        "",
        "Filtros aplicados: " + "; ".join(f"{name}: {value}" for name, value in filters),
        "",
        "| # | Score | Cargo | Empresa | Nível | Modelo | Local | Tecnologias | Publicada | Link |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    def cell(value: Any) -> str:
        return str(value or "—").replace("|", "/").replace("\n", " ").strip() or "—"

    for index, job in enumerate(ranked, start=1):
        published = str(job.get("published_at") or "")[:10] or "—"
        status = tracking.get(str(job.get("canonical_url")), {}).get("status")
        title = cell(job.get("title")) + (f" [{_TRACKING_NAMES[status]}]" if status in _TRACKING_NAMES else "")
        lines.append(
            "| " + " | ".join(
                [
                    str(index),
                    str(job_score(job, now)),
                    title,
                    cell(job.get("company")),
                    cell(level_name(job)),
                    WORKPLACE_NAMES.get(str(job.get("workplace_model")), "—"),
                    cell(job.get("location") or job.get("remote_scope")),
                    cell(", ".join(job_technologies(job))),
                    published,
                    cell(job.get("canonical_url")),
                ]
            ) + " |"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


_LEVEL_CODES = {"estagio", "junior", "pleno", "senior"}
_WORKPLACE_CODES = {"REMOTE", "HYBRID", "ONSITE"}


def _passes_extra_filters(
    job: dict[str, Any],
    min_score: int,
    levels: Sequence[str],
    workplaces: Sequence[str],
    max_age_days: int | None,
    now: datetime,
) -> bool:
    from job_radar.xlsx_export import job_score

    if min_score and job_score(job, now) < min_score:
        return False
    if workplaces and job.get("workplace_model") not in workplaces:
        return False
    if levels:
        labels = job.get("match_labels") or []
        found = {str(job.get("seniority") or "").casefold()} | {
            str(label).removeprefix("SENIORITY_MATCH:")
            for label in labels
            if str(label).startswith("SENIORITY_MATCH:")
        }
        if not found & set(levels):
            return False
    if max_age_days is not None:
        published = parse_iso_datetime(job.get("published_at"))
        # Sem data publicada não dá para provar que é recente: fica de fora.
        if published is None or (now - published).days > max_age_days:
            return False
    return True


def filter_jobs_for_export(
    jobs: Sequence[dict[str, Any]],
    *,
    text: str = "",
    source: str = "",
    match: str = "",
    tracked: str = "",
    tracking: dict[str, dict[str, str]] | None = None,
    min_score: int = 0,
    levels: Sequence[str] = (),
    workplaces: Sequence[str] = (),
    max_age_days: int | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    normalized_filter = _normalized_search_text(text)
    tracking = tracking or {}
    now = now or datetime.now(timezone.utc)
    result: list[dict[str, Any]] = []
    for job in jobs:
        if source and job.get("source") != source:
            continue
        if not _passes_extra_filters(job, min_score, levels, workplaces, max_age_days, now):
            continue
        tracked_status = tracking.get(str(job.get("canonical_url")), {}).get("status")
        if tracked == "active" and tracked_status == "DISCARDED":
            continue
        if tracked == "new" and (
            tracked_status or "STATUS:NEW" not in (job.get("match_labels") or [])
        ):
            continue
        if tracked in _TRACKED_FILTERS and tracked not in {"active", "new"}:
            if tracked_status != _TRACKED_FILTERS[tracked]:
                continue
        state = fit_state(job)
        off_topic = is_off_topic(job)
        if match == "offtopic":
            if not off_topic:
                continue
        elif match != "all" and off_topic:
            continue
        if match == "ready" and state != "READY":
            continue
        if match == "fit" and state not in {"READY", "CONDITIONAL"}:
            continue
        if match == "review" and state not in {"CONDITIONAL", "AMBIGUOUS"}:
            continue
        if match == "otherstack" and state != "OTHER_STACK":
            continue
        if match == "exclude" and state != "EXCLUDE":
            continue
        if normalized_filter:
            searchable = _normalized_search_text(
                json.dumps(
                    {
                        key: job.get(key)
                        for key in (
                            "title",
                            "company",
                            "location",
                            "technologies",
                            "match_labels",
                            "description_summary",
                            "requirements",
                            "evidence_snippets",
                            "seniority",
                            "remote_scope",
                        )
                    },
                    ensure_ascii=False,
                )
            )
            if normalized_filter not in searchable:
                continue
        result.append(job)
    return result


_MATCH_NAMES = {
    "": "Relevantes (só tecnologia)",
    "all": "Todas",
    "ready": "Só mais compatíveis",
    "fit": "Mais compatíveis e a revisar",
    "review": "A revisar",
    "otherstack": "Outra stack",
    "exclude": "Fora do perfil",
    "offtopic": "Fora da área de tecnologia",
}
_TRACKED_NAMES = {
    "": "Todas",
    "active": "Sem as descartadas",
    "new": "Só novas",
    "saved": "Só salvas",
    "applied": "Só aplicadas",
    "discarded": "Só descartadas",
}


def describe_export_filters(
    *,
    text: str = "",
    source: str = "",
    match: str = "",
    tracked: str = "",
    min_score: int = 0,
    levels: Sequence[str] = (),
    workplaces: Sequence[str] = (),
    max_age_days: int | None = None,
) -> list[tuple[str, str]]:
    return [
        ("Aderência", _MATCH_NAMES.get(match, match)),
        ("Acompanhamento", _TRACKED_NAMES.get(tracked, tracked)),
        ("Score mínimo", str(min_score) if min_score else "sem mínimo"),
        ("Nível", ", ".join(levels) if levels else "todos"),
        ("Modelo de trabalho", ", ".join(workplaces) if workplaces else "todos"),
        (
            "Publicadas nos últimos",
            f"{max_age_days} dias" if max_age_days else "qualquer data",
        ),
        ("Portal", source or "todos"),
        ("Busca por texto", text or "—"),
    ]


def stream_process(command: list[str], on_line: ProgressCallback) -> int:
    process = subprocess.Popen(  # noqa: S603 - comando montado internamente
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        on_line(line.rstrip())
    return process.wait()


def build_collection_command(
    output_dir: Path,
    sources: list[str] | None,
    *,
    workers: int = 1,
    executable: Path | None = None,
    control_file: Path | None = None,
) -> list[str]:
    command = [
        str(executable or Path(sys.executable)),
        "-m",
        "job_radar.cli",
        "collect",
        "--output",
        str(output_dir),
        "--workers",
        str(workers),
    ]
    for source in sources or []:
        command.extend(["--source", source])
    if control_file is not None:
        command.extend(["--control-file", str(control_file)])
    return command


def run_collection(
    output_dir: Path,
    sources: list[str] | None,
    workers: int,
    on_line: ProgressCallback,
) -> int:
    from job_radar.run_control import CONTROL_FILE_NAME

    return stream_process(
        build_collection_command(
            output_dir,
            sources,
            workers=workers,
            control_file=output_dir / CONTROL_FILE_NAME,
        ),
        on_line,
    )


class SearchController:
    def __init__(
        self,
        output_dir: Path,
        runner: CollectionRunner = run_collection,
        *,
        workers: int = 1,
    ) -> None:
        if workers < 1 or workers > 4:
            raise ValueError("workers deve estar entre 1 e 4")
        self._output_dir = output_dir
        self._runner = runner
        self._workers = workers
        self._lock = Lock()
        self._thread: Thread | None = None
        self._status = "IDLE"
        self._exit_code: int | None = None
        self._started_at: str | None = None
        self._finished_at: str | None = None
        self._error: str | None = None
        self._sources: dict[str, dict[str, Any]] = {}
        self._logs: list[str] = []
        self._control = "run"

    @property
    def _control_path(self) -> Path:
        from job_radar.run_control import CONTROL_FILE_NAME

        return self._output_dir / CONTROL_FILE_NAME

    def control(self, action: str) -> str | None:
        """pause / resume / stop da busca em andamento; devolve o erro, se houver."""

        from job_radar.run_control import write_state

        states = {"pause": "pause", "resume": "run", "stop": "stop"}
        if action not in states:
            return "Ação inválida."
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                return "Nenhuma busca em andamento."
            if self._control == "stop":
                return "A busca já está sendo encerrada."
            write_state(self._control_path, states[action])
            self._control = states[action]
        return None

    def start(self, sources: list[str] | None = None) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._status = "RUNNING"
            self._exit_code = None
            self._started_at = datetime.now(timezone.utc).isoformat()
            self._finished_at = None
            self._error = None
            self._sources = {}
            self._logs = []
            self._control = "run"
            try:
                from job_radar.run_control import write_state

                write_state(self._control_path, "run")
            except OSError:
                pass
            self._thread = Thread(
                target=self._run,
                args=(sources,),
                name="job-radar-search",
                daemon=True,
            )
            self._thread.start()
            return True

    def _run(self, sources: list[str] | None) -> None:
        try:
            exit_code = self._runner(
                self._output_dir,
                sources,
                self._workers,
                self._on_line,
            )
            status = "DONE" if exit_code == 0 else "PARTIAL" if exit_code == 3 else "ERROR"
            error = None if exit_code in {0, 3} else f"Coleta encerrou com codigo {exit_code}."
            if exit_code == _EXIT_BUSY:
                error = BUSY_MESSAGE
        except Exception as exc:  # noqa: BLE001 - boundary de thread
            exit_code = 1
            status = "ERROR"
            error = str(exc)
        with self._lock:
            if self._control == "stop" or exit_code == 4:
                status = "STOPPED"
                error = None
            self._exit_code = exit_code
            self._status = status
            self._error = error
            self._finished_at = datetime.now(timezone.utc).isoformat()
            self._control = "run"
            try:
                from job_radar.run_control import write_state

                write_state(self._control_path, "run")
            except OSError:
                pass

    def _on_line(self, line: str) -> None:
        progress = parse_progress_line(line)
        with self._lock:
            self._logs = [*self._logs[-79:], line]
            if progress is not None:
                self._sources[progress["source"]] = progress

    def snapshot(self) -> dict[str, Any]:
        output = load_output(self._output_dir)
        with self._lock:
            state = {
                "status": self._status,
                "paused": self._status == "RUNNING" and self._control == "pause",
                "stopping": self._status == "RUNNING" and self._control == "stop",
                "exit_code": self._exit_code,
                "started_at": self._started_at,
                "finished_at": self._finished_at,
                "error": self._error,
                "sources": dict(self._sources),
                "logs": list(self._logs),
            }
        return {**state, **output}

    def run_flags(self) -> dict[str, bool]:
        with self._lock:
            running = self._status == "RUNNING"
            return {
                "paused": running and self._control == "pause",
                "stopping": running and self._control == "stop",
            }

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def wait(self, timeout: float | None = None) -> bool:
        with self._lock:
            thread = self._thread
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def export_markdown(
        self,
        *,
        text: str = "",
        source: str = "",
        match: str = "",
        tracked: str = "",
        tracking: dict[str, dict[str, str]] | None = None,
        **extra: Any,
    ) -> bytes:
        jobs = self._filtered_jobs(
            text=text, source=source, match=match, tracked=tracked, tracking=tracking, **extra
        )
        output = load_output(self._output_dir)
        generated_at = datetime.now().astimezone().strftime("%d/%m/%Y %H:%M")
        report = output["report"] if isinstance(output["report"], dict) else {}
        sources = report.get("sources", [])
        if not isinstance(sources, list):
            sources = []
        return build_markdown_report(
            jobs,
            generated_at=generated_at,
            sources=sources,
            applied_filters={"text": text, "source": source, "match": match},
        ).encode("utf-8-sig")

    def _filtered_jobs(
        self,
        *,
        text: str,
        source: str,
        match: str,
        tracked: str,
        tracking: dict[str, dict[str, str]] | None,
        **extra: Any,
    ) -> list[dict[str, Any]]:
        output = load_output(self._output_dir)
        if output["read_error"]:
            raise OutputReadError(f"Nao foi possivel ler a saida local: {output['read_error']}")
        return filter_jobs_for_export(
            output["jobs"],
            text=text,
            source=source,
            match=match,
            tracked=tracked,
            tracking=tracking,
            **extra,
        )

    def export_csv(
        self,
        *,
        text: str = "",
        source: str = "",
        match: str = "",
        tracked: str = "",
        tracking: dict[str, dict[str, str]] | None = None,
        **extra: Any,
    ) -> bytes:
        jobs = self._filtered_jobs(
            text=text, source=source, match=match, tracked=tracked, tracking=tracking, **extra
        )
        return build_jobs_csv(jobs, tracking or {})

    def export_xlsx(
        self,
        *,
        text: str = "",
        source: str = "",
        match: str = "",
        tracked: str = "",
        tracking: dict[str, dict[str, str]] | None = None,
        **extra: Any,
    ) -> bytes:
        from job_radar.xlsx_export import build_jobs_xlsx

        jobs = self._filtered_jobs(
            text=text, source=source, match=match, tracked=tracked, tracking=tracking, **extra
        )
        return build_jobs_xlsx(
            jobs,
            tracking or {},
            filters=describe_export_filters(
                text=text, source=source, match=match, tracked=tracked, **extra
            ),
            reasons_for=fit_reasons,
        )

    def export_ai(
        self,
        *,
        text: str = "",
        source: str = "",
        match: str = "",
        tracked: str = "",
        tracking: dict[str, dict[str, str]] | None = None,
        **extra: Any,
    ) -> bytes:
        jobs = self._filtered_jobs(
            text=text, source=source, match=match, tracked=tracked, tracking=tracking, **extra
        )
        return build_jobs_ai_text(
            jobs,
            tracking or {},
            describe_export_filters(
                text=text, source=source, match=match, tracked=tracked, **extra
            ),
        )

    def count_export(
        self,
        *,
        text: str = "",
        source: str = "",
        match: str = "",
        tracked: str = "",
        tracking: dict[str, dict[str, str]] | None = None,
        **extra: Any,
    ) -> int:
        return len(
            self._filtered_jobs(
                text=text, source=source, match=match, tracked=tracked, tracking=tracking, **extra
            )
        )


# Nomes pelos quais o próprio navegador do usuário chega ao painel local.
_LOCAL_HOST_NAMES = ("127.0.0.1", "localhost")


def _dashboard_handler(
    controller: SearchController,
    static_dir: Path,
    preferences_path: Path | None,
    tracking_path: Path | None = None,
) -> type[BaseHTTPRequestHandler]:
    tracking_store = TrackingStore(tracking_path)
    static_files = {
        "/": ("index.html", "text/html; charset=utf-8"),
        "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    }

    class DashboardHandler(BaseHTTPRequestHandler):
        def _allowed_hosts(self) -> set[str]:
            port = self.server.server_address[1]
            return {f"{name}:{port}" for name in _LOCAL_HOST_NAMES}

        def _request_refusal(self, *, needs_json: bool) -> tuple[int, str] | None:
            """Barra DNS rebinding (Host), outro site (Origin) e formulários (CSRF)."""

            host = (self.headers.get("Host") or "").strip().casefold()
            allowed = self._allowed_hosts()
            if host not in allowed:
                return 403, "Endereco nao permitido: abra o painel por http://127.0.0.1."
            if not needs_json:
                return None
            origin = self.headers.get("Origin")
            if origin is not None and origin.strip().casefold() not in {
                f"http://{item}" for item in allowed
            }:
                return 403, "Pedido de outro site recusado."
            content_type = self.headers.get("Content-Type", "").split(";", maxsplit=1)[0]
            if content_type.strip().casefold() != "application/json":
                return 415, "Use application/json."
            return None

        def _guarded(self, route: Callable[[], None], *, needs_json: bool) -> None:
            refusal = self._request_refusal(needs_json=needs_json)
            if refusal is not None:
                status, message = refusal
                self._json(status, {"error": message})
                return
            route()

        def do_GET(self) -> None:  # noqa: N802 - contrato BaseHTTPRequestHandler
            self._guarded(self._route_get, needs_json=False)

        def do_POST(self) -> None:  # noqa: N802 - contrato BaseHTTPRequestHandler
            self._guarded(self._route_post, needs_json=True)

        def do_PUT(self) -> None:  # noqa: N802 - contrato BaseHTTPRequestHandler
            self._guarded(self._route_put, needs_json=True)

        def _write(
            self,
            status: int,
            content_type: str,
            body: bytes,
            *,
            headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._write(status, "application/json; charset=utf-8", body)

        def _read_json_body(self, limit: int = 16_384) -> dict[str, Any]:
            content_type = self.headers.get("Content-Type", "").split(";", maxsplit=1)[0]
            if content_type != "application/json":
                raise TypeError("Use application/json.")
            content_length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= content_length <= limit:
                raise ValueError("Corpo excede o limite permitido.")
            payload = json.loads(self.rfile.read(content_length) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("O corpo deve ser um objeto JSON.")
            return payload

        @staticmethod
        def _export_filters(query: str) -> dict[str, str] | str:
            parameters = parse_qs(query, keep_blank_values=True)
            filters = {
                name: parameters.get(name, [""])[-1]
                for name in ("text", "source", "match", "tracked")
            }
            if len(filters["text"]) > 200:
                return "Filtro de texto excede o limite."
            if filters["source"] and not re.fullmatch(r"[a-z0-9-]+", filters["source"]):
                return "Filtro de portal invalido."
            if filters["match"] not in _MATCH_FILTERS:
                return "Filtro de aderencia invalido."
            if filters["tracked"] and filters["tracked"] not in _TRACKED_FILTERS:
                return "Filtro de acompanhamento invalido."
            extras = DashboardHandler._extra_export_filters(parameters)
            if isinstance(extras, str):
                return extras
            return {**filters, **extras}

        @staticmethod
        def _extra_export_filters(parameters: dict[str, list[str]]) -> dict[str, Any] | str:
            def last(name: str) -> str:
                return parameters.get(name, [""])[-1].strip()

            extras: dict[str, Any] = {}
            if last("min_score"):
                value = last("min_score")
                if not value.isdigit() or not 0 <= int(value) <= 100:
                    return "Score minimo invalido."
                extras["min_score"] = int(value)
            if last("max_age_days"):
                value = last("max_age_days")
                if not value.isdigit() or not 1 <= int(value) <= 3650:
                    return "Periodo invalido."
                extras["max_age_days"] = int(value)
            levels = [v for v in last("levels").casefold().split(",") if v]
            if not set(levels) <= _LEVEL_CODES:
                return "Nivel invalido."
            if levels:
                extras["levels"] = tuple(levels)
            workplaces = [v for v in last("workplaces").upper().split(",") if v]
            if not set(workplaces) <= _WORKPLACE_CODES:
                return "Modelo de trabalho invalido."
            if workplaces:
                extras["workplaces"] = tuple(workplaces)
            return extras

        def _load_preferences_payload(self) -> dict[str, Any]:
            from job_radar.config import load_profile, load_sources
            from job_radar.preferences import load_preferences, preferences_to_dict

            project = _project_root()
            profile = load_profile(project / "config" / "profile.yaml")
            sources = load_sources(project / "config" / "sources.yaml")
            search_terms = tuple(
                dict.fromkeys(
                    query
                    for source in sources
                    if source.enabled and not source.fixed_queries
                    for query in source.queries
                )
            )
            preferences = load_preferences(
                default_profile=profile,
                default_search_terms=search_terms,
                path=preferences_path,
            )
            return preferences_to_dict(preferences)

        def _load_sources_payload(self) -> dict[str, object]:
            from job_radar.config import load_sources
            from job_radar.pipeline import _supports_queries

            sources = load_sources(_project_root() / "config" / "sources.yaml")
            return {
                "sources": [
                    {
                        "code": source.code,
                        "kind": source.kind.value,
                        "tech_focus": source.tech_focus,
                        "text_search": _supports_queries(source) and not source.fixed_queries,
                    }
                    for source in sources
                    if source.enabled
                ]
            }

        def _load_linkedin_plan(self, period: str = "week") -> dict[str, object]:
            from job_radar.manual_search import build_linkedin_search_plan
            from job_radar.preferences import preferences_from_dict

            preferences = preferences_from_dict(self._load_preferences_payload())
            return build_linkedin_search_plan(preferences, period=period)

        def _post_linkedin_import(self) -> None:
            from job_radar.config import load_profile
            from job_radar.linkedin_import import MAX_TEXT_CHARS, import_into_output
            from job_radar.preferences import apply_preferences, preferences_from_dict

            try:
                payload = self._read_json_body(limit=MAX_TEXT_CHARS * 2)
                text = payload.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Cole links de vagas, o texto de um alerta ou o CSV.")
                if controller.is_running():
                    self._json(409, {"error": "Espere a busca terminar para importar."})
                    return
                profile = apply_preferences(
                    load_profile(_project_root() / "config" / "profile.yaml"),
                    preferences_from_dict(self._load_preferences_payload()),
                )
                with OutputLock(controller.output_dir):
                    result = import_into_output(controller.output_dir, text, profile)
            except OutputBusyError as exc:
                self._json(409, {"error": str(exc)})
                return
            except TypeError as exc:
                self._json(415, {"error": str(exc)})
                return
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, result)

        def _route_get(self) -> None:
            request_url = urlsplit(self.path)
            path = request_url.path
            if path == "/api/state":
                self._json(200, controller.snapshot())
                return
            if path == "/api/preferences":
                try:
                    payload = self._load_preferences_payload()
                except (OSError, ValueError) as exc:
                    self._json(500, {"error": str(exc)})
                    return
                self._json(200, payload)
                return
            if path == "/api/presets":
                from job_radar.presets import load_custom_stacks, presets_payload

                self._json(
                    200,
                    presets_payload(load_custom_stacks(self._resolved_preferences_path())),
                )
                return
            if path == "/api/preferences/insights":
                from job_radar.preferences import preferences_from_dict
                from job_radar.reclassify import insights, read_payloads

                try:
                    profile, _ = self._profile_for(
                        preferences_from_dict(self._load_preferences_payload())
                    )
                    payload = insights(read_payloads(controller.output_dir), profile)
                except (OSError, ValueError) as exc:
                    self._json(500, {"error": str(exc)})
                    return
                self._json(200, payload)
                return
            if path == "/api/presets/terms":
                from job_radar.presets import (
                    MAX_SEARCH_TERMS,
                    load_custom_stacks,
                    recommended_terms,
                    term_catalog,
                )

                query = parse_qs(request_url.query)
                ids = [
                    item
                    for name in ("stacks", "levels")
                    for item in [query.get(name, [""])[-1]]
                ]
                stacks = [s for s in ids[0].split(",") if re.fullmatch(r"[a-z0-9-]{1,60}", s)]
                levels = [s for s in ids[1].split(",") if re.fullmatch(r"[a-z]{1,20}", s)]
                groups = term_catalog(
                    stacks, levels, load_custom_stacks(self._resolved_preferences_path())
                )
                self._json(
                    200,
                    {
                        "groups": groups,
                        "recommended": recommended_terms(groups),
                        "limit": MAX_SEARCH_TERMS,
                    },
                )
                return
            if path == "/api/presets/suggest":
                from job_radar.presets import load_custom_stacks, suggest

                query = parse_qs(request_url.query)

                def _csv_param(name: str) -> list[str]:
                    return [
                        item
                        for item in query.get(name, [""])[-1].split(",")
                        if re.fullmatch(r"[a-z0-9-]{1,60}", item)
                    ]

                self._json(
                    200,
                    suggest(
                        _csv_param("stacks"),
                        _csv_param("levels"),
                        load_custom_stacks(self._resolved_preferences_path()),
                    ),
                )
                return
            if path == "/api/profiles":
                self._json(200, self._profiles_payload())
                return
            if path == "/api/cleanup/status":
                from job_radar.cleanup import backup_info

                self._json(200, {"backup": backup_info(controller.output_dir)})
                return
            if path == "/api/cleanup/rules":
                self._json(200, self._rules_payload())
                return
            if path == "/api/sources":
                try:
                    payload = self._load_sources_payload()
                except (OSError, ValueError) as exc:
                    self._json(500, {"error": str(exc)})
                    return
                self._json(200, payload)
                return
            if path == "/api/linkedin-searches":
                try:
                    period = parse_qs(request_url.query).get("period", ["week"])[-1]
                    payload = self._load_linkedin_plan(period)
                except (OSError, ValueError) as exc:
                    self._json(500, {"error": str(exc)})
                    return
                self._json(200, payload)
                return
            if path == "/api/tracking":
                try:
                    self._json(200, {"jobs": tracking_store.load()})
                except TrackingError as exc:
                    self._json(500, {"error": str(exc)})
                return
            exports = {
                "/api/export/markdown": (
                    controller.export_markdown,
                    "text/markdown; charset=utf-8",
                    "relatorio-vagas.md",
                ),
                "/api/export/csv": (
                    controller.export_csv,
                    "text/csv; charset=utf-8",
                    "vagas.csv",
                ),
                "/api/export/ai": (
                    controller.export_ai,
                    "text/markdown; charset=utf-8",
                    "vagas-para-ia.md",
                ),
                "/api/export/xlsx": (
                    controller.export_xlsx,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "vagas-" + datetime.now().strftime("%Y-%m-%d") + ".xlsx",
                ),
            }
            if path == "/api/export/count":
                filters = self._export_filters(request_url.query)
                if isinstance(filters, str):
                    self._json(400, {"error": filters})
                    return
                try:
                    count = controller.count_export(
                        **filters, tracking=tracking_store.load()
                    )
                except (OutputReadError, TrackingError) as exc:
                    self._json(500, {"error": str(exc)})
                    return
                self._json(200, {"count": count})
                return
            if path in exports:
                exporter, content_type, filename = exports[path]
                filters = self._export_filters(request_url.query)
                if isinstance(filters, str):
                    self._json(400, {"error": filters})
                    return
                try:
                    tracking = tracking_store.load()
                    document = exporter(**filters, tracking=tracking)
                except (OutputReadError, TrackingError) as exc:
                    self._json(500, {"error": str(exc)})
                    return
                self._write(
                    200,
                    content_type,
                    document,
                    headers={
                        "Content-Disposition": f'attachment; filename="{filename}"'
                    },
                )
                return
            static = static_files.get(path)
            if static is None:
                self._json(404, {"error": "Recurso nao encontrado."})
                return
            filename, content_type = static
            try:
                body = (static_dir / filename).read_bytes()
            except OSError:
                self._json(404, {"error": "Arquivo da interface nao encontrado."})
                return
            self._write(200, content_type, body)

        def _profile_for(self, preferences: Any) -> tuple[Any, dict[str, str | None]]:
            """Perfil efetivo (profile.yaml + preferências) e país padrão por portal."""

            from job_radar.config import load_profile, load_sources
            from job_radar.preferences import apply_preferences

            project = _project_root()
            profile = apply_preferences(
                load_profile(project / "config" / "profile.yaml"), preferences
            )
            countries = {
                source.code: source.default_country
                for source in load_sources(project / "config" / "sources.yaml")
            }
            return profile, countries

        def _post_preferences_preview(self) -> None:
            from job_radar.preferences import PreferencesError, validate_preferences_payload
            from job_radar.reclassify import reclassify_output

            try:
                preferences = validate_preferences_payload(self._read_json_body(limit=65_536))
                profile, countries = self._profile_for(preferences)
                result = reclassify_output(
                    controller.output_dir,
                    profile,
                    countries,
                    dry_run=True,
                    rules=self._cleanup_rules(),
                )
            except TypeError as exc:
                self._json(415, {"error": str(exc)})
                return
            except (PreferencesError, OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, result)

        def _post_stacks(self, action: str) -> None:
            from job_radar.presets import (
                StackError,
                delete_custom_stack,
                make_custom_stack,
                presets_payload,
                save_custom_stack,
            )

            path = self._resolved_preferences_path()
            try:
                payload = self._read_json_body()
                if action == "delete":
                    stacks = delete_custom_stack(path, payload.get("id"))
                    created = None
                else:
                    stack = make_custom_stack(
                        payload.get("label"),
                        payload.get("technologies"),
                        payload.get("queries", ()),
                    )
                    stacks = save_custom_stack(path, stack)
                    created = stack.id
            except TypeError as exc:
                self._json(415, {"error": str(exc)})
                return
            except (StackError, OSError, ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {**presets_payload(stacks), "created": created})

        def _resolved_preferences_path(self) -> Path:
            from job_radar.preferences import preferences_path as default_path

            return preferences_path or default_path()

        def _profiles_payload(self) -> dict[str, Any]:
            from job_radar.profiles import active_profile, list_profiles

            path = self._resolved_preferences_path()
            return {"profiles": list_profiles(path), "active": active_profile(path)}

        def _post_profiles(self, action: str) -> None:
            from job_radar.preferences import PreferencesError, validate_preferences_payload
            from job_radar.profiles import (
                activate_profile,
                delete_profile,
                save_profile,
            )

            path = self._resolved_preferences_path()
            try:
                payload = self._read_json_body(limit=65_536)
                if action == "save":
                    preferences = validate_preferences_payload(
                        payload.get("preferences") or {}
                    )
                    name = save_profile(path, payload.get("name"), preferences)
                    activate_profile(path, name)
                elif action == "activate":
                    activate_profile(path, payload.get("name"))
                else:
                    delete_profile(path, payload.get("name"))
            except TypeError as exc:
                self._json(415, {"error": str(exc)})
                return
            except (PreferencesError, OSError, ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            body = self._profiles_payload()
            if action != "delete":
                body["preferences"] = self._load_preferences_payload()
            self._json(200, body)

        def _cleanup_rules(self) -> Any:
            from job_radar.cleanup import load_rules

            return load_rules(self._resolved_preferences_path())

        def _rules_payload(self) -> dict[str, Any]:
            from job_radar.cleanup import REASON_NAMES, load_rules

            rules = load_rules(self._resolved_preferences_path())
            return {**rules.to_dict(), "reasons": REASON_NAMES}

        def _put_cleanup_rules(self) -> None:
            from job_radar.cleanup import CleanupError, rules_from_dict, save_rules

            try:
                rules = rules_from_dict(self._read_json_body())
                save_rules(self._resolved_preferences_path(), rules)
            except TypeError as exc:
                self._json(415, {"error": str(exc)})
                return
            except (CleanupError, OSError, ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, self._rules_payload())

        def _post_cleanup(self) -> None:
            from job_radar.cleanup import CleanupRules, clean_output, load_rules

            try:
                payload = self._read_json_body()
                rules = load_rules(self._resolved_preferences_path())
                if "max_age_days" in payload:
                    max_age = payload["max_age_days"]
                    if max_age is not None and (
                        isinstance(max_age, bool)
                        or not isinstance(max_age, int)
                        or not 1 <= max_age <= 3650
                    ):
                        raise ValueError("max_age_days deve ser um inteiro de 1 a 3650.")
                    rules = CleanupRules(
                        rules.off_topic, rules.excluded, rules.expired, max_age
                    )
                dry_run = bool(payload.get("dry_run", False))
                if controller.is_running():
                    self._json(409, {"error": "Espere a busca terminar para limpar."})
                    return
                try:
                    tracked = tracking_store.load()
                except TrackingError as exc:
                    # Sem o acompanhamento não dá para proteger as vagas salvas.
                    self._json(
                        409,
                        {"error": f"{exc} Corrija o arquivo de acompanhamento antes de limpar."},
                    )
                    return
                remove_urls: set[str] = set()
                if payload.get("remove_discarded") is True:
                    remove_urls = {
                        url for url, entry in tracked.items()
                        if entry.get("status") == "DISCARDED"
                    }
                # A prévia só lê; a limpeza de verdade regrava o arquivo.
                with nullcontext() if dry_run else OutputLock(controller.output_dir):
                    result = clean_output(
                        controller.output_dir,
                        keep_urls=set(tracked) - remove_urls,
                        rules=rules,
                        dry_run=dry_run,
                        remove_urls=remove_urls,
                    )
            except OutputBusyError as exc:
                self._json(409, {"error": str(exc)})
                return
            except TypeError as exc:
                self._json(415, {"error": str(exc)})
                return
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, result)

        def _post_cleanup_undo(self) -> None:
            from job_radar.cleanup import CleanupError, undo_cleanup

            if controller.is_running():
                self._json(409, {"error": "Espere a busca terminar para desfazer."})
                return
            try:
                with OutputLock(controller.output_dir):
                    result = undo_cleanup(controller.output_dir)
            except OutputBusyError as exc:
                self._json(409, {"error": str(exc)})
                return
            except (CleanupError, OSError, ValueError) as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, result)

        def _route_post(self) -> None:
            path = self.path.split("?", maxsplit=1)[0]
            if path == "/api/cleanup/undo":
                self._post_cleanup_undo()
                return
            if path == "/api/preferences/preview":
                self._post_preferences_preview()
                return
            if path in {"/api/stacks", "/api/stacks/delete"}:
                self._post_stacks("delete" if path.endswith("/delete") else "save")
                return
            if path in {"/api/search/pause", "/api/search/resume", "/api/search/stop"}:
                error = controller.control(path.rsplit("/", 1)[-1])
                if error:
                    self._json(409, {"error": error})
                else:
                    self._json(200, {"status": "ok", **controller.run_flags()})
                return
            if path in {"/api/profiles/activate", "/api/profiles/delete"}:
                self._post_profiles(path.rsplit("/", 1)[-1])
                return
            if path == "/api/cleanup":
                self._post_cleanup()
                return
            if path == "/api/linkedin/import":
                self._post_linkedin_import()
                return
            if path != "/api/search":
                self._json(404, {"error": "Recurso nao encontrado."})
                return
            try:
                payload = self._read_json_body()
                sources = payload.get("sources")
                if sources is not None and (
                    not isinstance(sources, list)
                    or not all(
                        isinstance(source, str)
                        and re.fullmatch(r"[a-z0-9-]+", source)
                        for source in sources
                    )
                ):
                    raise ValueError("Lista de fontes invalida.")
            except TypeError as exc:
                self._json(415, {"error": str(exc)})
                return
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
                return

            if not controller.start(sources):
                self._json(409, {"error": "Uma busca ja esta em andamento."})
                return
            self._json(202, {"accepted": True})

        def _route_put(self) -> None:
            path = self.path.split("?", maxsplit=1)[0]
            if path == "/api/tracking":
                try:
                    payload = self._read_json_body()
                    entries = tracking_store.set_status(
                        payload.get("url"),
                        payload.get("status"),
                        note=payload.get("note"),
                        now=datetime.now(timezone.utc),
                    )
                except TypeError as exc:
                    self._json(415, {"error": str(exc)})
                    return
                except (ValueError, json.JSONDecodeError) as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self._json(200, {"jobs": entries})
                return
            if path == "/api/profiles":
                self._post_profiles("save")
                return
            if path == "/api/cleanup/rules":
                self._put_cleanup_rules()
                return
            if path != "/api/preferences":
                self._json(404, {"error": "Recurso nao encontrado."})
                return
            try:
                from job_radar.preferences import (
                    preferences_to_dict,
                    save_preferences,
                    validate_preferences_payload,
                )

                payload = self._read_json_body(limit=65_536)
                preferences = validate_preferences_payload(payload)
                save_preferences(preferences, path=preferences_path)
            except TypeError as exc:
                self._json(415, {"error": str(exc)})
                return
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            body: dict[str, Any] = dict(preferences_to_dict(preferences))
            query = parse_qs(urlsplit(self.path).query)
            if query.get("reapply", [""])[-1] == "1":
                body["reapplied"] = None
                if controller.is_running():
                    body["reapply_skipped"] = "Busca em andamento: a próxima coleta já usa o perfil novo."
                else:
                    from job_radar.reclassify import reclassify_output

                    try:
                        profile, countries = self._profile_for(preferences)
                        with OutputLock(controller.output_dir):
                            body["reapplied"] = reclassify_output(
                                controller.output_dir,
                                profile,
                                countries,
                                rules=self._cleanup_rules(),
                            )
                    except OutputBusyError as exc:
                        body["reapply_skipped"] = str(exc)
                    except (OSError, ValueError, RuntimeError) as exc:
                        body["reapply_skipped"] = f"Não foi possível reaplicar: {exc}"
            self._json(200, body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return DashboardHandler


def create_server(
    host: str,
    port: int,
    controller: SearchController,
    static_dir: Path,
    *,
    preferences_path: Path | None = None,
    tracking_path: Path | None = None,
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(
        (host, port),
        _dashboard_handler(controller, static_dir, preferences_path, tracking_path),
    )


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interface local do Radar de Vagas.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--no-browser", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost"}:
        print("A interface aceita apenas o host local 127.0.0.1.", file=sys.stderr)
        return 2
    if not 1 <= args.port <= 65_535:
        print("A porta deve estar entre 1 e 65535.", file=sys.stderr)
        return 2

    project = _project_root()
    controller = SearchController(project / "output", workers=args.workers)
    try:
        server = create_server(
            args.host,
            args.port,
            controller,
            Path(__file__).resolve().parent / "web",
        )
    except OSError as exc:
        print(f"Nao foi possivel iniciar a interface: {exc}", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Radar de Vagas rodando em {url}")
    print("Pressione Ctrl+C para encerrar.")
    if not args.no_browser:
        Timer(0.25, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("Interface encerrada.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
