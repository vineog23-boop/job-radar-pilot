"""Fonte LinkedIn via API pública de convidado (sem login).

O LinkedIn serve os resultados da busca pública de vagas por endpoints
"jobs-guest" anônimos — os mesmos que a própria página de busca usa antes de
qualquer login. Esta fonte é o **opt-in explícito** do projeto para o domínio:
o ``FetchPolicy`` mantém o bloqueio geral do LinkedIn e só libera requisições
feitas por este adaptador (``kind: linkedin``).

Aviso honesto: o ``robots.txt`` do LinkedIn não permite ``/jobs-guest/`` e os
Termos de Serviço proíbem coleta automatizada. Por isso esta fonte nasce com
throttling alto, poucas páginas e sem enriquecimento de detalhe — uso pessoal
de baixo volume, por conta e risco de quem habilitar. O domínio continua
bloqueado para todos os outros kinds e para qualquer URL fora desta busca.
"""

from __future__ import annotations

from urllib.parse import urlencode, urlsplit, urlunsplit

from job_radar.dates import parse_published_at
from job_radar.identity import canonicalize_url
from job_radar.models import (
    CollectionStatus,
    SourceConfig,
    SourceRunResult,
    VacancyRecord,
)
from job_radar.sources.base import PaginatedAdapter, ParsedPage, extract_value

_GUEST_SEARCH = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)
# A guest API devolve 25 cartões por chamada e pagina com `start` em múltiplos.
_PAGE_SIZE = 25


def normalize_job_url(raw: str) -> str:
    """Link canônico da vaga: só o caminho, sem query de tracking."""
    parsed = urlsplit(raw)
    path = parsed.path.split("?", 1)[0].rstrip("/")
    return canonicalize_url(urlunsplit(("https", "www.linkedin.com", path, "", "")))


def job_url_from_path(path: str) -> str | None:
    """ID numérico da vaga no fim do caminho (…/jobs/view/1234567890)."""
    slug = path.rstrip("/").rsplit("/", 1)[-1]
    candidate = slug.rsplit("-", 1)[-1]
    return candidate if candidate.isdigit() else None


class LinkedinAdapter(PaginatedAdapter):
    """Busca vagas públicas do LinkedIn sem login (guest API).

    A paginação não tem link "próxima": cada página com cartões gera a próxima
    URL somando ``_PAGE_SIZE`` ao offset ``start``, até ``max_pages`` por
    combinação termo × localização ou uma página sem cartões.
    """

    def collect(self, config: SourceConfig, fetcher: object) -> SourceRunResult:
        locations = tuple(config.api.get("locations") or ("Brasil",))
        # O pipeline zera `config.queries` antes de chamar o adaptador (o sweep
        # de termos é dele, por URL); por isso os termos ficam em `api`.
        queries = tuple(config.api.get("queries") or config.queries) or (
            "desenvolvedor",
        )
        records: list[VacancyRecord] = []
        visited: list[str] = []
        cards_observed = 0
        warnings: list[str] = []
        seen_urls: set[str] = set()

        for query in queries:
            for location in locations:
                start = 0
                for _ in range(config.max_pages):
                    url = (
                        f"{_GUEST_SEARCH}?"
                        + urlencode(
                            {"keywords": query, "location": location, "start": start}
                        )
                    )
                    if url in visited:
                        break
                    visited.append(url)
                    fetched = fetcher.fetch(url, config)  # type: ignore[attr-defined]
                    if (
                        fetched.status is not CollectionStatus.SUCCESS
                        or fetched.response is None
                    ):
                        reason = (
                            fetched.block_reason.value
                            if fetched.block_reason is not None
                            else "FETCH_ERROR"
                        )
                        if not records:
                            return SourceRunResult(
                                source_code=config.code,
                                status=fetched.status,
                                records=(),
                                pages_observed=len(visited),
                                cards_observed=0,
                                stop_reason=reason,
                                errors=(fetched.error or reason,),
                                visited_urls=tuple(visited),
                            )
                        warnings.append(f"{query!r}/{location!r}: {reason}")
                        break
                    parsed = self.parse_page(fetched.response, config)
                    cards_observed += parsed.cards_observed
                    for record in parsed.records:
                        if record.canonical_url in seen_urls:
                            continue
                        seen_urls.add(record.canonical_url)
                        records.append(record)
                    if parsed.cards_observed == 0:
                        break
                    start += _PAGE_SIZE

        return SourceRunResult(
            source_code=config.code,
            status=CollectionStatus.SUCCESS if records else CollectionStatus.EMPTY,
            records=tuple(records),
            pages_observed=len(visited),
            cards_observed=cards_observed,
            has_more=False,
            visited_urls=tuple(visited),
            warnings=tuple(warnings),
        )

    def parse_page(self, page: object, config: SourceConfig) -> ParsedPage:
        del config
        cards = page.css("li")  # type: ignore[attr-defined]
        records: list[VacancyRecord] = []
        for card in cards:
            href = extract_value(card, "a.base-card__full-link::attr(href)")
            if not href:
                continue
            url = normalize_job_url(page.urljoin(href))  # type: ignore[attr-defined]
            job_id = job_url_from_path(urlsplit(url).path)
            title = extract_value(card, "h3.base-search-card__title::all-text")
            company = extract_value(card, "h4.base-search-card__subtitle::all-text")
            if not title or not company:
                continue
            location = extract_value(card, "span.job-search-card__location::all-text")
            published = parse_published_at(
                extract_value(card, "time::attr(datetime)")
            )
            records.append(
                VacancyRecord(
                    source="linkedin",
                    source_job_id=job_id,
                    canonical_url=url,
                    title=title,
                    company=company,
                    location=location,
                    published_at=published,
                    match_labels=("EXTRACTION:GUEST_API",),
                )
            )
        return ParsedPage(tuple(records), len(cards))
