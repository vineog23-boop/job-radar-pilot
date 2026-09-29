from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import subprocess
import sys
from threading import Lock, Thread, Timer
from typing import Any, Callable, Sequence
import webbrowser


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
CollectionRunner = Callable[[Path, list[str] | None, ProgressCallback], int]


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
    executable: Path | None = None,
) -> list[str]:
    command = [
        str(executable or Path(sys.executable)),
        "-m",
        "job_radar.cli",
        "collect",
        "--output",
        str(output_dir),
    ]
    for source in sources or []:
        command.extend(["--source", source])
    return command


def run_collection(
    output_dir: Path,
    sources: list[str] | None,
    on_line: ProgressCallback,
) -> int:
    return stream_process(build_collection_command(output_dir, sources), on_line)


class SearchController:
    def __init__(
        self,
        output_dir: Path,
        runner: CollectionRunner = run_collection,
    ) -> None:
        self._output_dir = output_dir
        self._runner = runner
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
            exit_code = self._runner(self._output_dir, sources, self._on_line)
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


def _dashboard_handler(
    controller: SearchController,
    static_dir: Path,
) -> type[BaseHTTPRequestHandler]:
    static_files = {
        "/": ("index.html", "text/html; charset=utf-8"),
        "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    }

    class DashboardHandler(BaseHTTPRequestHandler):
        def _write(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._write(status, "application/json; charset=utf-8", body)

        def do_GET(self) -> None:  # noqa: N802 - contrato BaseHTTPRequestHandler
            path = self.path.split("?", maxsplit=1)[0]
            if path == "/api/state":
                self._json(200, controller.snapshot())
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
            content_type = self.headers.get("Content-Type", "").split(";", maxsplit=1)[0]
            if content_type != "application/json":
                self._json(415, {"error": "Use application/json."})
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length > 16_384:
                    raise ValueError("Corpo excede o limite permitido.")
                payload = json.loads(self.rfile.read(content_length) or b"{}")
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
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
                return

            if not controller.start(sources):
                self._json(409, {"error": "Uma busca ja esta em andamento."})
                return
            self._json(202, {"accepted": True})

        def log_message(self, format: str, *args: Any) -> None:
            return

    return DashboardHandler


def create_server(
    host: str,
    port: int,
    controller: SearchController,
    static_dir: Path,
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(
        (host, port),
        _dashboard_handler(controller, static_dir),
    )


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interface local do Radar de Vagas.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
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
    controller = SearchController(project / "output")
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
