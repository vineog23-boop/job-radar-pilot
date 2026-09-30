from __future__ import annotations

import argparse
from dataclasses import replace
import ipaddress
from pathlib import Path
import socket
import sys
from typing import Sequence
from urllib.parse import urlsplit, urlunsplit

import yaml

from job_radar.config import ConfigError, load_profile, load_sources
from job_radar.fetching import (
    BROWSER_LOCALE,
    BROWSER_TIMEZONE,
    HTTP_ACCEPT_LANGUAGE,
    FetchPolicy,
    ProfileInUseError,
    bootstrap_auth,
)
from job_radar.enrich import DEFAULT_ENRICH_LIMIT
from job_radar.history import SeenHistory
from job_radar.models import CollectionStatus, SourceKind
from job_radar.output import validate_jsonl, write_outputs
from job_radar.pipeline import JobRadarPipeline
from job_radar.preferences import (
    PreferencesError,
    apply_preferences,
    load_preferences,
)
from job_radar.selector_suggestion import suggest_from_page
from job_radar.tracking import TrackingError, TrackingStore


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
        "--tech-only",
        action="store_true",
        help="Coletar apenas os portais focados em tecnologia (busca rapida).",
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
    collect.add_argument(
        "--workers",
        type=int,
        choices=range(1, 5),
        default=1,
        help="Fontes coletadas em paralelo (1 a 4; padrao: 1).",
    )
    collect.add_argument(
        "--enrich-limit",
        type=int,
        default=DEFAULT_ENRICH_LIMIT,
        help=(
            "Vagas candidatas enriquecidas pela pagina de detalhe "
            f"(0 desliga; padrao: {DEFAULT_ENRICH_LIMIT})."
        ),
    )
    collect.add_argument(
        "--keep-all",
        action="store_true",
        help=(
            "Manter no arquivo tambem as vagas inuteis (fora da area, fora do "
            "perfil, vencidas). Por padrao elas sao descartadas."
        ),
    )
    collect.add_argument(
        "--max-age-days",
        type=int,
        default=None,
        help="Descartar vagas publicadas ha mais de N dias (padrao: nao descartar).",
    )
    collect.add_argument(
        "--no-history",
        action="store_true",
        help="Nao ler nem gravar o historico local de vagas ja vistas.",
    )
    validate = commands.add_parser(
        "validate-output", help="Validar um JSONL contra o schema local."
    )
    validate.add_argument("path", type=Path)
    auth = commands.add_parser(
        "auth", help="Abrir login manual e preservar a sessao local de um portal."
    )
    auth.add_argument("source", metavar="SOURCE")
    suggest = commands.add_parser(
        "suggest-selectors",
        help="Sugerir seletores sem alterar a configuracao.",
    )
    suggest.add_argument("target", metavar="SOURCE_OR_URL")
    suggest.add_argument("--text", required=True, help="Titulo visivel de uma vaga.")
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
        preferences = load_preferences(
            default_profile=profile,
            default_search_terms=(
                query
                for source in sources
                if source.enabled and not source.fixed_queries
                for query in source.queries
            ),
        )
        profile = apply_preferences(profile, preferences)
    except (ConfigError, PreferencesError) as exc:
        print(f"CONFIG_ERROR: {exc}", file=sys.stderr)
        return 2

    enabled = tuple(source for source in sources if source.enabled)
    source_error = _validate_source_codes(args.sources, {source.code for source in enabled})
    if source_error:
        print(source_error, file=sys.stderr)
        return 2

    requested_codes = set(args.sources or ())
    if getattr(args, "tech_only", False) and not requested_codes:
        requested_codes = {source.code for source in enabled if source.tech_focus}
        if not requested_codes:
            print("Nenhuma fonte marcada com tech_focus.", file=sys.stderr)
            return 2
        args.sources = sorted(requested_codes)
    selected = tuple(
        source for source in enabled if not requested_codes or source.code in requested_codes
    )
    if args.dry_run:
        print(
            f"DRY_RUN: {len(selected)} fontes selecionadas; "
            f"{len(enabled)} fontes habilitadas; {len(sources)} fontes configuradas"
        )
        for source in selected:
            auth = "auth-manual" if source.requires_auth else "publica"
            blocked_domains = ",".join(source.browser.blocked_domains) or "-"
            print(
                f"- {source.code}: {source.kind.value}, {auth}, "
                f"max_pages={source.max_pages}, locale={BROWSER_LOCALE}, "
                f"timezone={BROWSER_TIMEZONE}, "
                f"accept_language={HTTP_ACCEPT_LANGUAGE}, block_ads=false, "
                f"disable_resources={str(source.browser.disable_resources).lower()}, "
                f"blocked_domains={blocked_domains}, "
                f"scroll_to_load={str(source.browser.scroll_to_load).lower()}"
            )
        return 0

    def print_source_progress(source: object) -> None:
        print(
            f"{source.source_code}: {source.status.value}; "
            f"pages={source.pages_observed}; cards={source.cards_observed}; "
            f"records={len(source.records)}; "
            f"stop={source.stop_reason or 'EXHAUSTED'}",
            flush=True,
        )
        for warning in source.warnings:
            print(
                f"WARNING {source.source_code}: {warning}",
                flush=True,
            )

    history = None if getattr(args, "no_history", False) else SeenHistory()
    if args.workers == 1:
        with FetchPolicy() as fetcher:
            pipeline = JobRadarPipeline(
                sources,
                profile,
                fetcher=fetcher,
                workers=1,
                on_source_done=print_source_progress,
                history=history,
                enrich_limit=args.enrich_limit,
            )
            result = pipeline.run(args.sources)
    else:
        pipeline = JobRadarPipeline(
            sources,
            profile,
            fetcher_factory=FetchPolicy,
            workers=args.workers,
            on_source_done=print_source_progress,
            history=history,
            enrich_limit=args.enrich_limit,
        )
        result = pipeline.run(args.sources)
    for item in result.source_results:
        for warning in item.warnings:
            if warning.startswith("SOURCE_COUNT_"):
                print(f"WARNING {item.source_code}: {warning}", flush=True)
    keep_urls: frozenset[str] = frozenset()
    try:
        keep_urls = frozenset(TrackingStore().load())
    except TrackingError:
        pass
    manifest = write_outputs(
        result,
        args.output.resolve(),
        merge_unrefreshed=bool(args.sources),
        prune=not getattr(args, "keep_all", False),
        keep_urls=keep_urls,
        max_age_days=getattr(args, "max_age_days", None),
    )
    if manifest.discarded:
        print(f"DISCARDED: {manifest.discarded} vagas inuteis nao foram salvas.")
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


def _auth(args: argparse.Namespace) -> int:
    project = _project_root()
    try:
        sources = load_sources(project / "config" / "sources.yaml")
    except ConfigError as exc:
        print(f"CONFIG_ERROR: {exc}", file=sys.stderr)
        return 2

    source = next(
        (item for item in sources if item.enabled and item.code == args.source),
        None,
    )
    if source is None:
        print(f"Fonte desconhecida: {args.source}", file=sys.stderr)
        return 2

    print(
        "AUTH_MANUAL: conclua login, CAPTCHA ou 2FA somente na janela do navegador."
    )
    try:
        bootstrap_auth(source)
    except ProfileInUseError:
        print(f"AUTH_BUSY: o perfil de {source.code} ja esta em uso", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"AUTH_ERROR: {type(exc).__name__}", file=sys.stderr)
        return 3
    print(
        f"AUTH_PROFILE_SAVED_UNVERIFIED: {source.code}; "
        "o login sera confirmado pela proxima coleta"
    )
    return 0


def _origin(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.casefold()
    host = (parsed.hostname or "").casefold()
    if not scheme or not host:
        return None
    netloc = f"[{host}]" if ":" in host else host
    if port is not None and not (scheme == "https" and port == 443):
        netloc = f"{netloc}:{port}"
    return urlunsplit((scheme, netloc, "", "", ""))


def _resolved_addresses(hostname: str) -> tuple[str, ...]:
    addresses = {
        str(item[4][0])
        for item in socket.getaddrinfo(
            hostname,
            443,
            type=socket.SOCK_STREAM,
        )
    }
    return tuple(sorted(addresses))


def _is_global_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return (
        address.is_global
        and not address.is_link_local
        and not address.is_loopback
        and not address.is_multicast
        and not address.is_private
        and not address.is_reserved
        and not address.is_unspecified
    )


def _validate_raw_target_syntax(value: str) -> str:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("URL invalida") from exc
    if parsed.scheme.casefold() != "https" or not parsed.netloc or not parsed.hostname:
        raise ValueError("URL deve usar HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL com credenciais nao e permitida")
    hostname = parsed.hostname.casefold()
    if hostname == "localhost" or hostname.endswith(".localhost") or "%" in hostname:
        raise ValueError("Host local nao e permitido")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if not _is_global_address(str(literal)):
            raise ValueError("Endereco nao global nao e permitido")
    return hostname


def _validate_raw_target_resolution(hostname: str) -> None:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        try:
            addresses = _resolved_addresses(hostname)
        except OSError as exc:
            raise ValueError("Nao foi possivel resolver o host") from exc
        if not addresses or any(not _is_global_address(item) for item in addresses):
            raise ValueError("DNS resolveu endereco nao global")


def _validate_raw_target(value: str) -> str:
    hostname = _validate_raw_target_syntax(value)
    _validate_raw_target_resolution(hostname)
    return value


def _suggest_target(
    target: str,
    sources: Sequence[object],
) -> tuple[str, object, bool]:
    configured = next(
        (source for source in sources if getattr(source, "code", None) == target),
        None,
    )
    if configured is not None:
        source = replace(configured, adaptive=False)
        return str(getattr(source, "start_url")), source, False

    hostname = _validate_raw_target_syntax(target)
    raw_url = target
    raw_origin = _origin(raw_url)
    configured = next(
        (
            source
            for source in sources
            if _origin(str(getattr(source, "start_url", ""))) == raw_origin
        ),
        None,
    )
    if configured is None:
        raise ValueError("URL deve pertencer a uma fonte configurada")
    if getattr(configured, "kind", None) not in {
        SourceKind.GENERIC,
        SourceKind.INDEED,
    }:
        raise ValueError(
            "URL crua nao e permitida para fonte com transporte de navegador"
        )
    _validate_raw_target_resolution(hostname)
    source = replace(configured, start_url=raw_url, adaptive=False)
    return raw_url, source, True


def _suggest_selectors(args: argparse.Namespace) -> int:
    project = _project_root()
    try:
        sources = load_sources(project / "config" / "sources.yaml")
        target_url, source, _raw_url = _suggest_target(args.target, sources)
    except (ConfigError, ValueError) as exc:
        print(f"SUGGEST_ERROR: {exc}", file=sys.stderr)
        return 2

    with FetchPolicy() as fetcher:
        fetched = fetcher.fetch(target_url, source)
    if fetched.status is not CollectionStatus.SUCCESS or fetched.response is None:
        print(
            f"SUGGEST_ERROR: coleta terminou em {fetched.status.value}",
            file=sys.stderr,
        )
        return 2
    if _origin(str(getattr(fetched.response, "url", ""))) != _origin(target_url):
        print("SUGGEST_ERROR: resposta mudou de origem", file=sys.stderr)
        return 2

    try:
        suggestion = suggest_from_page(fetched.response, args.text)
    except (AttributeError, TypeError, ValueError):
        print("SUGGEST_ERROR: pagina nao pode ser analisada", file=sys.stderr)
        return 2
    if suggestion is None:
        print("SUGGEST_ERROR: texto visivel nao encontrado", file=sys.stderr)
        return 2

    payload = {
        "selectors": {
            "card": suggestion.card,
            "title": suggestion.title,
            "url": suggestion.url,
        },
        "cards_found": suggestion.cards_found,
        "validation": {
            "title": f"{suggestion.title_matches}/{suggestion.cards_found}",
            "url": f"{suggestion.url_matches}/{suggestion.cards_found}",
        },
    }
    print(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).rstrip())
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "collect":
        return _collect(args)
    if args.command == "auth":
        return _auth(args)
    if args.command == "suggest-selectors":
        return _suggest_selectors(args)
    return _validate(args.path)


if __name__ == "__main__":
    raise SystemExit(main())
