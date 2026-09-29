from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from job_radar.config import ConfigError, load_profile, load_sources
from job_radar.fetching import FetchPolicy
from job_radar.models import CollectionStatus
from job_radar.output import validate_jsonl, write_outputs
from job_radar.pipeline import JobRadarPipeline


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job-radar",
        description="Coletor independente de vagas com Scrapling.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect", help="Coletar vagas das fontes configuradas.")
    collect.add_argument(
        "--source",
        action="append",
        dest="sources",
        metavar="CODE",
        help="Limitar a uma fonte; pode ser repetido.",
    )
    collect.add_argument(
        "--output",
        type=Path,
        default=_project_root() / "output",
        help="Diretorio das saidas.",
    )
    collect.add_argument(
        "--dry-run",
        action="store_true",
        help="Validar e listar fontes sem acessar a rede.",
    )
    validate = commands.add_parser(
        "validate-output", help="Validar um JSONL contra o schema local."
    )
    validate.add_argument("path", type=Path)
    return parser


def _validate_source_codes(requested: Sequence[str] | None, configured: set[str]) -> str | None:
    if not requested:
        return None
    unknown = set(requested) - configured
    if unknown:
        return f"Fonte desconhecida: {', '.join(sorted(unknown))}"
    return None


def _collect(args: argparse.Namespace) -> int:
    project = _project_root()
    try:
        profile = load_profile(project / "config" / "profile.yaml")
        sources = load_sources(project / "config" / "sources.yaml")
    except ConfigError as exc:
        print(f"CONFIG_ERROR: {exc}", file=sys.stderr)
        return 2

    enabled = tuple(source for source in sources if source.enabled)
    source_error = _validate_source_codes(args.sources, {source.code for source in enabled})
    if source_error:
        print(source_error, file=sys.stderr)
        return 2

    selected = tuple(
        source for source in enabled if not args.sources or source.code in args.sources
    )
    if args.dry_run:
        print(f"DRY_RUN: {len(selected)} fontes selecionadas; {len(enabled)} fontes habilitadas")
        for source in selected:
            auth = "auth-manual" if source.requires_auth else "publica"
            print(f"- {source.code}: {source.kind.value}, {auth}, max_pages={source.max_pages}")
        return 0

    pipeline = JobRadarPipeline(
        sources,
        profile,
        fetcher=FetchPolicy(),
    )
    result = pipeline.run(args.sources)
    manifest = write_outputs(result, args.output.resolve())
    for source in result.source_results:
        print(
            f"{source.source_code}: {source.status.value}; "
            f"pages={source.pages_observed}; cards={source.cards_observed}; "
            f"records={len(source.records)}; stop={source.stop_reason or 'EXHAUSTED'}"
        )
    print(f"JSONL: {manifest.jsonl_path}")
    print(f"CSV: {manifest.csv_path}")
    print(f"REPORT: {manifest.report_path}")

    complete_statuses = {CollectionStatus.SUCCESS, CollectionStatus.EMPTY}
    return 0 if all(item.status in complete_statuses for item in result.source_results) else 3


def _validate(path: Path) -> int:
    result = validate_jsonl(path.resolve(), _project_root() / "schemas" / "vagas.schema.json")
    if result.valid:
        print(f"VALID: {result.line_count} linhas")
        return 0
    print(f"INVALID: {result.line_count} linhas; {len(result.errors)} erros")
    for error in result.errors:
        print(f"- {error}")
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "collect":
        return _collect(args)
    return _validate(args.path)


if __name__ == "__main__":
    raise SystemExit(main())
