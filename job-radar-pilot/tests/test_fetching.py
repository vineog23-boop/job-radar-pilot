from __future__ import annotations

from dataclasses import dataclass

import pytest

from job_radar.fetching import BlockReason, FetchPolicy, detect_block
from job_radar.models import CollectionStatus, SourceConfig, SourceKind


@dataclass
class FakeResponse:
    status: int = 200
    text: str = "<html><body>Vagas abertas</body></html>"
    url: str = "https://example.com/jobs"


def _source(kind: SourceKind = SourceKind.GENERIC) -> SourceConfig:
    return SourceConfig(
        code="example",
        kind=kind,
        start_url="https://example.com/jobs",
        enabled=True,
        max_pages=2,
        min_interval_seconds=1,
        requires_auth=False,
        selectors={"card": "article", "title": "h2", "url": "a::attr(href)"},
    )


def test_robots_denial_prevents_request() -> None:
    calls: list[str] = []
    policy = FetchPolicy(
        http_get=lambda url: calls.append(url),
        browser_fetch=lambda url: calls.append(url),
        robots_allowed=lambda url: False,
        sleep=lambda seconds: None,
    )

    result = policy.fetch("https://example.com/private", _source())

    assert result.status is CollectionStatus.BLOCKED
    assert result.block_reason is BlockReason.ROBOTS_DENIED
    assert result.attempts == 0
    assert calls == []


def test_timeout_retries_once_with_backoff() -> None:
    attempts = 0
    sleeps: list[float] = []

    def get(url: str) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("cookie=secret full-html=<html>token=abc</html>")
        return FakeResponse()

    policy = FetchPolicy(
        http_get=get,
        browser_fetch=get,
        robots_allowed=lambda url: True,
        sleep=sleeps.append,
    )

    result = policy.fetch("https://example.com/jobs?token=secret", _source())

    assert result.status is CollectionStatus.SUCCESS
    assert result.attempts == 2
    assert sleeps == [1.0]
    assert "secret" not in (result.error or "")
    assert "<html>" not in (result.error or "")


def test_http_429_stops_without_aggressive_retry() -> None:
    attempts = 0

    def get(url: str) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        return FakeResponse(status=429, text="rate limit cookie=secret")

    policy = FetchPolicy(
        http_get=get,
        browser_fetch=get,
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    )

    result = policy.fetch("https://example.com/jobs?token=secret", _source())

    assert result.status is CollectionStatus.BLOCKED
    assert result.block_reason is BlockReason.RATE_LIMITED
    assert result.attempts == 1
    assert attempts == 1
    assert "secret" not in (result.error or "")
    assert "?" not in (result.error or "")


@pytest.mark.parametrize("status", [401, 403])
def test_http_auth_denial_is_typed_block(status: int) -> None:
    policy = FetchPolicy(
        http_get=lambda url: FakeResponse(status=status, text="Access denied"),
        browser_fetch=lambda url: FakeResponse(status=status, text="Access denied"),
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    )

    result = policy.fetch("https://example.com/jobs", _source())

    assert result.status is CollectionStatus.BLOCKED
    assert result.block_reason is not None
    assert result.block_reason.value == "ACCESS_DENIED"
    assert result.attempts == 1


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (FakeResponse(url="https://example.com/login"), BlockReason.LOGIN_REQUIRED),
        (FakeResponse(text="Complete o CAPTCHA para continuar"), BlockReason.CAPTCHA),
        (FakeResponse(text="Digite o codigo de verificacao em duas etapas"), BlockReason.TWO_FACTOR),
        (FakeResponse(text="Detectamos atividade incomum na sua conta"), BlockReason.ACTIVITY_ALERT),
    ],
)
def test_detects_interactive_blocks(
    response: FakeResponse, reason: BlockReason
) -> None:
    assert detect_block(response) is reason


def test_dynamic_source_uses_browser_only() -> None:
    calls: list[str] = []

    def browser(url: str) -> FakeResponse:
        calls.append(f"browser:{url}")
        return FakeResponse()

    policy = FetchPolicy(
        http_get=lambda url: calls.append(f"http:{url}"),
        browser_fetch=browser,
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    )

    result = policy.fetch("https://example.com/jobs", _source(SourceKind.DYNAMIC))

    assert result.status is CollectionStatus.SUCCESS
    assert calls == ["browser:https://example.com/jobs"]


def test_successive_requests_respect_source_interval() -> None:
    sleeps: list[float] = []
    policy = FetchPolicy(
        http_get=lambda url: FakeResponse(url=url),
        browser_fetch=lambda url: FakeResponse(url=url),
        robots_allowed=lambda url: True,
        sleep=sleeps.append,
        monotonic=lambda: 100.0,
    )
    source = _source()

    policy.fetch("https://example.com/jobs/1", source)
    policy.fetch("https://example.com/jobs/2", source)

    assert sleeps == [1.0]
