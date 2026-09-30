from __future__ import annotations

from dataclasses import dataclass

from job_radar.fetching import FetchResult
from job_radar.models import CollectionStatus, SourceConfig, SourceKind, WorkplaceModel
from job_radar.sources.rss import RssAdapter

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel><title>x</title>
<item>
  <title>Vaga Home Office: Desenvolvedor Java Júnior na empresa Acme &amp; Cia</title>
  <link>https://www.example.com/dev-java-junior-acme/</link>
  <pubDate>Tue, 29 Sep 2026 06:15:00 -0300</pubDate>
  <category><![CDATA[Tecnologia da Informação — Geral]]></category>
  <description><![CDATA[A Acme abriu vaga home office.]]></description>
  <content:encoded><![CDATA[<p><strong>Empresa:</strong> Acme</p><p><strong>Tipo:</strong> CLT – Tempo Integral</p>]]></content:encoded>
</item>
<item><title>sem link</title></item>
<item>
  <title>Vaga Home Office: Desenvolvedor Java Júnior na empresa Acme &amp; Cia</title>
  <link>https://www.example.com/dev-java-junior-acme/</link>
</item>
</channel></rss>
""".encode()


@dataclass
class _Response:
    body: bytes
    status: int = 200


class _Fetcher:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def fetch(self, url: str, source: SourceConfig) -> FetchResult:
        return FetchResult(
            CollectionStatus.SUCCESS,
            response=_Response(self.body),  # type: ignore[arg-type]
            attempts=1,
        )


def _source() -> SourceConfig:
    return SourceConfig(
        code="rss-x",
        kind=SourceKind.RSS,
        start_url="https://www.example.com/feed/",
        enabled=True,
        min_interval_seconds=1,
        requires_auth=False,
        max_pages=1,
        default_country="BR",
    )


def test_rss_adapter_maps_items_and_skips_invalid_or_duplicates() -> None:
    result = RssAdapter().collect(_source(), _Fetcher(FEED))  # type: ignore[arg-type]
    assert result.status is CollectionStatus.SUCCESS
    assert result.cards_observed == 3
    assert len(result.records) == 1
    record = result.records[0]
    assert record.title == "Desenvolvedor Java Júnior"
    assert record.company == "Acme"
    assert record.employment_type == "CLT – Tempo Integral"
    assert record.workplace_model is WorkplaceModel.REMOTE
    assert record.published_at == "2026-09-29T06:15:00-03:00"


def test_rss_adapter_rejects_non_feed_and_entity_payloads() -> None:
    for body in (b"<html></html>", b"not xml", b'<!DOCTYPE x [<!ENTITY a "b">]><rss></rss>'):
        result = RssAdapter().collect(_source(), _Fetcher(body))  # type: ignore[arg-type]
        assert result.status is CollectionStatus.ERROR
        assert result.stop_reason == "LAYOUT_CHANGED"
