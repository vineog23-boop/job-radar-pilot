from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from time import monotonic as system_monotonic, sleep as system_sleep
from typing import Any, Callable, Protocol
import unicodedata
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from job_radar.models import CollectionStatus, SourceConfig, SourceKind


class ResponseLike(Protocol):
    status: int
    text: str
    url: str


class BlockReason(StrEnum):
    ROBOTS_DENIED = "ROBOTS_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    CAPTCHA = "CAPTCHA"
    TWO_FACTOR = "TWO_FACTOR"
    ACTIVITY_ALERT = "ACTIVITY_ALERT"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True, slots=True)
class FetchResult:
    status: CollectionStatus
    response: ResponseLike | None = None
    block_reason: BlockReason | None = None
    error: str | None = None
    attempts: int = 0


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        "".join(character for character in decomposed if not unicodedata.combining(character)).split()
    )


def _safe_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def detect_block(response: ResponseLike) -> BlockReason | None:
    if response.status == 429:
        return BlockReason.RATE_LIMITED

    path = urlsplit(str(response.url)).path.casefold()
    if any(segment in path for segment in ("/login", "/signin", "/sign-in")):
        return BlockReason.LOGIN_REQUIRED

    text = _normalize(str(response.text))
    if any(marker in text for marker in ("captcha", "nao sou um robo", "i am not a robot")):
        return BlockReason.CAPTCHA
    if any(
        marker in text
        for marker in (
            "codigo de verificacao em duas etapas",
            "autenticacao de dois fatores",
            "two-factor authentication",
            "2fa",
        )
    ):
        return BlockReason.TWO_FACTOR
    if any(
        marker in text
        for marker in (
            "atividade incomum",
            "atividade suspeita",
            "unusual activity",
            "suspicious activity",
        )
    ):
        return BlockReason.ACTIVITY_ALERT
    return None


class FetchPolicy:
    def __init__(
        self,
        *,
        http_get: Callable[[str], ResponseLike] | None = None,
        browser_fetch: Callable[[str], ResponseLike] | None = None,
        robots_allowed: Callable[[str], bool] | None = None,
        sleep: Callable[[float], None] = system_sleep,
        monotonic: Callable[[], float] = system_monotonic,
        max_attempts: int = 2,
    ) -> None:
        self._http_get = http_get or self._default_http_get
        self._browser_fetch = browser_fetch or self._default_browser_fetch
        self._robots_allowed = robots_allowed or self._default_robots_allowed
        self._sleep = sleep
        self._monotonic = monotonic
        self._max_attempts = max_attempts
        self._last_request_at: dict[str, float] = {}

    @staticmethod
    def _default_http_get(url: str) -> ResponseLike:
        from scrapling.fetchers import Fetcher

        return Fetcher.get(url, timeout=30, retries=0, stealthy_headers=True)

    @staticmethod
    def _default_browser_fetch(url: str) -> ResponseLike:
        from scrapling.fetchers import DynamicFetcher

        return DynamicFetcher.fetch(
            url,
            headless=True,
            network_idle=True,
            timeout=30_000,
            retries=0,
        )

    @staticmethod
    def _default_robots_allowed(url: str) -> bool:
        from scrapling.fetchers import Fetcher

        parsed = urlsplit(url)
        robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
        try:
            response: Any = Fetcher.get(
                robots_url,
                timeout=10,
                retries=0,
                stealthy_headers=True,
            )
        except Exception:
            return False
        if int(response.status) >= 400:
            return int(response.status) == 404
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(str(response.text).splitlines())
        return parser.can_fetch("JobRadarPilot/0.1", url)

    def _throttle(self, source: SourceConfig) -> None:
        previous = self._last_request_at.get(source.code)
        now = self._monotonic()
        if previous is not None:
            remaining = source.min_interval_seconds - (now - previous)
            if remaining > 0:
                self._sleep(remaining)

    def fetch(self, url: str, source: SourceConfig) -> FetchResult:
        safe_url = _safe_url(url)
        if not self._robots_allowed(url):
            return FetchResult(
                status=CollectionStatus.BLOCKED,
                block_reason=BlockReason.ROBOTS_DENIED,
                error=f"ROBOTS_DENIED em {safe_url}",
            )

        self._throttle(source)
        request = (
            self._browser_fetch
            if source.kind is SourceKind.DYNAMIC
            else self._http_get
        )
        for attempt in range(1, self._max_attempts + 1):
            self._last_request_at[source.code] = self._monotonic()
            try:
                response = request(url)
            except TimeoutError:
                if attempt < self._max_attempts:
                    self._sleep(max(source.min_interval_seconds, float(attempt)))
                    continue
                return FetchResult(
                    status=CollectionStatus.BLOCKED,
                    block_reason=BlockReason.TIMEOUT,
                    error=f"Timeout ao acessar {safe_url}",
                    attempts=attempt,
                )
            except Exception:
                return FetchResult(
                    status=CollectionStatus.ERROR,
                    error=f"Falha de coleta em {safe_url}",
                    attempts=attempt,
                )

            block = detect_block(response)
            if block is not None:
                return FetchResult(
                    status=CollectionStatus.BLOCKED,
                    response=None,
                    block_reason=block,
                    error=f"{block.value} em {safe_url}",
                    attempts=attempt,
                )
            return FetchResult(
                status=CollectionStatus.SUCCESS,
                response=response,
                attempts=attempt,
            )

        raise AssertionError("Loop de tentativas encerrou sem resultado.")
