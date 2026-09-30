from __future__ import annotations

import argparse
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

from job_radar.export_document import build_markdown_report
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


def _fit_state(job: dict[str, Any]) -> str:
    labels = job.get("match_labels") or []
    for state in ("READY", "CONDITIONAL", "EXCLUDE", "AMBIGUOUS"):
        if f"FIT:{state}" in labels:
            return state
    return "AMBIGUOUS"


# Filtro de acompanhamento: "" = todas, "active" = oculta descartadas.
_TRACKED_FILTERS = {
    "active": None,
    "new": None,
    "saved": "SAVED",
    "applied": "APPLIED",
    "discarded": "DISCARDED",
}
_FIT_NAMES = {
    "READY": "Mais compatível",
    "CONDITIONAL": "Condicional",
    "AMBIGUOUS": "Dados insuficientes",
    "EXCLUDE": "Fora do perfil",
}
_TRACKING_NAMES = {"SAVED": "Salva", "APPLIED": "Aplicada", "DISCARDED": "Descartada"}
# Filtro de aderência: "" = relevantes (esconde o que não é de TI), "all" = tudo.
_MATCH_FILTERS = {"", "all", "ready", "review", "exclude", "offtopic"}
_REASON_LABELS = (
    ("RELEVANCE:OFF_TOPIC", "fora da área de tecnologia"),
    ("SENIORITY_MISMATCH:", "nível acima do desejado"),
    ("LOCATION_MISMATCH:", "fora das localidades escolhidas"),
    ("WORKPLACE_MISMATCH:", "modelo de trabalho diferente"),
    ("LOCATION_UNCLEAR:", "local não confirmado"),
    ("WORKPLACE_UNCLEAR:", "modelo de trabalho não confirmado"),
    ("SENIORITY_UNCLEAR:", "faixa de nível ampla (júnior/pleno)"),
    ("ELIGIBILITY_UNCLEAR:", "vaga com público restrito"),
)


def is_off_topic(job: dict[str, Any]) -> bool:
    return "RELEVANCE:OFF_TOPIC" in (job.get("match_labels") or [])


def fit_reasons(job: dict[str, Any]) -> list[str]:
    """Explica em português por que a vaga não é 'Mais compatível'."""

    labels = [str(label) for label in job.get("match_labels") or []]
    reasons = [
        text
        for prefix, text in _REASON_LABELS
        if any(label.startswith(prefix) for label in labels)
    ]
    if not reasons and _fit_state(job) == "AMBIGUOUS":
        reasons.append("poucos dados para avaliar")
    return reasons


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
        writer.writerow(
            {
                "aderencia": _FIT_NAMES.get(_fit_state(job), "Dados insuficientes"),
                "acompanhamento": _TRACKING_NAMES.get(entry.get("status", ""), ""),
                "titulo": job.get("title") or "",
                "empresa": job.get("company") or "",
                "local": job.get("location") or job.get("remote_scope") or "",
                "modalidade": job.get("workplace_model") or "",
                "senioridade": job.get("seniority") or "",
                "tecnologias": ", ".join(job.get("technologies") or []),
                "publicada_em": job.get("published_at") or "",
                "fonte": job.get("source") or "",
                "url": job.get("canonical_url") or "",
                "nota": entry.get("note", ""),
                "motivo": "; ".join(fit_reasons(job)),
            }
        )
    return buffer.getvalue().encode("utf-8-sig")


def filter_jobs_for_export(
    jobs: Sequence[dict[str, Any]],
    *,
    text: str = "",
    source: str = "",
    match: str = "",
    tracked: str = "",
    tracking: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    normalized_filter = _normalized_search_text(text)
    tracking = tracking or {}
    result: list[dict[str, Any]] = []
    for job in jobs:
        if source and job.get("source") != source:
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
        state = _fit_state(job)
        off_topic = is_off_topic(job)
        if match == "offtopic":
            if not off_topic:
                continue
        elif match != "all" and off_topic:
            continue
        if match == "ready" and state != "READY":
            continue
        if match == "review" and state not in {"CONDITIONAL", "AMBIGUOUS"}:
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
    return command


def run_collection(
    output_dir: Path,
    sources: list[str] | None,
    workers: int,
    on_line: ProgressCallback,
) -> int:
    return stream_process(
        build_collection_command(output_dir, sources, workers=workers),
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
        except Exception as exc:  # noqa: BLE001 - boundary de thread
            exit_code = 1
            status = "ERROR"
            error = str(exc)
        with self._lock:
            self._exit_code = exit_code
            self._status = status
            self._error = error
            self._finished_at = datetime.now(timezone.utc).isoformat()

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
                "exit_code": self._exit_code,
                "started_at": self._started_at,
                "finished_at": self._finished_at,
                "error": self._error,
                "sources": dict(self._sources),
                "logs": list(self._logs),
            }
        return {**state, **output}

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
    ) -> bytes:
        jobs = self._filtered_jobs(
            text=text, source=source, match=match, tracked=tracked, tracking=tracking
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
        )

    def export_csv(
        self,
        *,
        text: str = "",
        source: str = "",
        match: str = "",
        tracked: str = "",
        tracking: dict[str, dict[str, str]] | None = None,
    ) -> bytes:
        jobs = self._filtered_jobs(
            text=text, source=source, match=match, tracked=tracked, tracking=tracking
        )
        return build_jobs_csv(jobs, tracking or {})


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

        def _read_json_body(self) -> dict[str, Any]:
            content_type = self.headers.get("Content-Type", "").split(";", maxsplit=1)[0]
            if content_type != "application/json":
                raise TypeError("Use application/json.")
            content_length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= content_length <= 16_384:
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
            return filters

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

            sources = load_sources(_project_root() / "config" / "sources.yaml")
            return {
                "sources": [
                    {
                        "code": source.code,
                        "kind": source.kind.value,
                        "tech_focus": source.tech_focus,
                    }
                    for source in sources
                    if source.enabled
                ]
            }

        def _load_linkedin_plan(self) -> dict[str, object]:
            from job_radar.manual_search import build_linkedin_search_plan
            from job_radar.preferences import preferences_from_dict

            preferences = preferences_from_dict(self._load_preferences_payload())
            return build_linkedin_search_plan(preferences)

        def do_GET(self) -> None:  # noqa: N802 - contrato BaseHTTPRequestHandler
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
                    payload = self._load_linkedin_plan()
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
            }
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

        def do_POST(self) -> None:  # noqa: N802 - contrato BaseHTTPRequestHandler
            path = self.path.split("?", maxsplit=1)[0]
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

        def do_PUT(self) -> None:  # noqa: N802 - contrato BaseHTTPRequestHandler
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
            if path != "/api/preferences":
                self._json(404, {"error": "Recurso nao encontrado."})
                return
            try:
                from job_radar.preferences import (
                    preferences_to_dict,
                    save_preferences,
                    validate_preferences_payload,
                )

                payload = self._read_json_body()
                preferences = validate_preferences_payload(payload)
                save_preferences(preferences, path=preferences_path)
            except TypeError as exc:
                self._json(415, {"error": str(exc)})
                return
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, preferences_to_dict(preferences))

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
