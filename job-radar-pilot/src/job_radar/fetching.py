from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from enum import StrEnum
import os
from pathlib import Path
import re
from time import monotonic as system_monotonic, sleep as system_sleep
from typing import Any, Callable, ContextManager, Protocol
import unicodedata
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from job_radar.models import CollectionStatus, SourceConfig, SourceKind


_PROFILE_READY_MARKER = ".job-radar.auth-ready"


class ResponseLike(Protocol):
    status: int
    text: str
    url: str


class BlockReason(StrEnum):
    ROBOTS_DENIED = "ROBOTS_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    ACCESS_DENIED = "ACCESS_DENIED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    CAPTCHA = "CAPTCHA"
    TWO_FACTOR = "TWO_FACTOR"
    ACTIVITY_ALERT = "ACTIVITY_ALERT"
    TIMEOUT = "TIMEOUT"


class ProfileInUseError(RuntimeError):
    """Impede duas instancias de Chromium de usarem o mesmo perfil."""


class _ProfileLock:
    def __init__(self, profile_dir: Path) -> None:
        self._profile_dir = profile_dir
        self._file: Any | None = None

    def __enter__(self) -> "_ProfileLock":
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        lock_file = self._profile_dir / ".job-radar.profile.lock"
        handle = lock_file.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover - a aplicacao principal roda no Windows
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as error:
            handle.close()
            raise ProfileInUseError(
                f"Perfil do portal ja esta em uso: {self._profile_dir.name}"
            ) from error
        self._file = handle
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._file is None:
            return
        try:
            self._file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - a aplicacao principal roda no Windows
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None


@dataclass(frozen=True, slots=True)
class FetchResult:
    status: CollectionStatus
    response: ResponseLike | None = None
    block_reason: BlockReason | None = None
    error: str | None = None
    attempts: int = 0


def default_profile_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA indisponivel para perfis autenticados")
    return Path(local_app_data) / "JobRadar" / "profiles"


def _profile_directory(source_code: str, profile_root: Path | None = None) -> Path:
    if re.fullmatch(r"[a-z0-9][a-z0-9-]*", source_code) is None:
        raise ValueError("Codigo de fonte invalido para perfil autenticado")
    return (profile_root or default_profile_root()) / source_code


def _default_http_session_factory() -> ContextManager[Any]:
    from scrapling.fetchers import FetcherSession

    return FetcherSession(timeout=30, retries=1, stealthy_headers=True)


def _default_browser_session_factory(**kwargs: object) -> ContextManager[Any]:
    from scrapling.fetchers import DynamicSession

    return DynamicSession(**kwargs)


def _scroll_infojobs_until_stable(page: Any) -> None:
    selector = ".js_vacanciesGridFragment > .js_rowCard"
    previous = -1
    stable_rounds = 0
    for _ in range(8):
        count = page.locator(selector).count()
        if count == previous:
            stable_rounds += 1
        else:
            stable_rounds = 0
            previous = count
        if stable_rounds >= 1:
            break
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(700)


def _load_ciee_until_stable(page: Any) -> None:
    card_selector = "a.vaga-row[href*='codigoVaga=']"
    previous = -1
    for _ in range(12):
        count = page.locator(card_selector).count()
        button = page.locator(".btn-exibir-mais-vagas")
        if count == previous or button.count() == 0 or not button.last.is_visible():
            break
        previous = count
        try:
            button.last.click(force=True, timeout=5_000)
        except Exception:
            break
        page.wait_for_timeout(600)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        "".join(character for character in decomposed if not unicodedata.combining(character)).split()
    )


def _safe_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _response_text(response: object) -> str:
    text = getattr(response, "text", "")
    if text:
        return str(text)
    body = getattr(response, "body", b"")
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body or "")


def detect_block(response: ResponseLike) -> BlockReason | None:
    if response.status == 429:
        return BlockReason.RATE_LIMITED
    if response.status in {401, 403}:
        return BlockReason.ACCESS_DENIED

    path = urlsplit(str(response.url)).path.casefold()
    if any(segment in path for segment in ("/login", "/signin", "/sign-in")) or path in {
        "/auth",
        "/auth/",
    }:
        return BlockReason.LOGIN_REQUIRED

    text = _normalize(_response_text(response))
    if any(
        marker in text
        for marker in (
            "captcha para continuar",
            "complete o captcha",
            "nao sou um robo",
            "i am not a robot",
        )
    ):
        return BlockReason.CAPTCHA
    if any(
        marker in text
        for marker in (
            "codigo de verificacao em duas etapas",
            "autenticacao de dois fatores",
            "two-factor authentication",
        )
    ) or re.search(r"(?<![a-z0-9])2fa(?![a-z0-9])", text):
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


def bootstrap_auth(
    source: SourceConfig,
    *,
    profile_root: Path | None = None,
    browser_session_factory: Callable[..., ContextManager[Any]] | None = None,
    input_func: Callable[[str], str] = input,
) -> Path:
    """Abre login manual e preserva apenas o perfil local do navegador."""

    profile_dir = _profile_directory(source.code, profile_root)
    factory = browser_session_factory or _default_browser_session_factory
    options: dict[str, object] = {
        "headless": False,
        "network_idle": False,
        "timeout": 30_000,
        "retries": 1,
        "user_data_dir": str(profile_dir),
    }
    with _ProfileLock(profile_dir):
        with factory(**options) as session:
            session.fetch(
                source.start_url,
                network_idle=False,
                timeout=30_000,
            )
            input_func(
                "Conclua o login, CAPTCHA ou 2FA diretamente no navegador; "
                "depois pressione Enter aqui para salvar a sessao e fechar."
            )
        (profile_dir / _PROFILE_READY_MARKER).touch(exist_ok=True)
    return profile_dir


class FetchPolicy:
    def __init__(
        self,
        *,
        http_get: Callable[[str], ResponseLike] | None = None,
        browser_fetch: Callable[[str], ResponseLike] | None = None,
        http_session_factory: Callable[[], ContextManager[Any]] | None = None,
        browser_session_factory: Callable[..., ContextManager[Any]] | None = None,
        profile_root: Path | None = None,
        robots_allowed: Callable[[str], bool] | None = None,
        sleep: Callable[[float], None] = system_sleep,
        monotonic: Callable[[], float] = system_monotonic,
        max_attempts: int = 2,
    ) -> None:
        self._http_get = http_get
        self._browser_fetch = browser_fetch
        self._http_session_factory = http_session_factory or _default_http_session_factory
        self._browser_session_factory = (
            browser_session_factory or _default_browser_session_factory
        )
        self._profile_root = profile_root
        self._custom_robots_allowed = robots_allowed
        self._sleep = sleep
        self._monotonic = monotonic
        self._max_attempts = max_attempts
        self._last_request_at: dict[str, float] = {}
        self._robots_policies: dict[
            tuple[str, str], Callable[[str], bool]
        ] = {}
        self._robots_decisions: dict[str, bool] = {}
        self._resources = ExitStack()
        self._http_session: Any | None = None
        self._browser_sessions: dict[str, Any] = {}
        self._closed = False

    def __enter__(self) -> "FetchPolicy":
        if self._closed:
            raise RuntimeError("FetchPolicy ja foi encerrado")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._resources.close()
        self._http_session = None
        self._browser_sessions.clear()
        self._closed = True

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
            network_idle=False,
            timeout=30_000,
            retries=1,
        )

    @staticmethod
    def _default_robots_policy(url: str) -> Callable[[str], bool]:
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
            return lambda target_url: False
        if int(response.status) >= 400:
            allowed = int(response.status) == 404
            return lambda target_url: allowed
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(_response_text(response).splitlines())
        return lambda target_url: parser.can_fetch("JobRadarPilot/0.1", target_url)

    @staticmethod
    def _default_robots_allowed(url: str) -> bool:
        return FetchPolicy._default_robots_policy(url)(url)

    def _throttle(self, source: SourceConfig) -> None:
        previous = self._last_request_at.get(source.code)
        now = self._monotonic()
        if previous is not None:
            remaining = source.min_interval_seconds - (now - previous)
            if remaining > 0:
                self._sleep(remaining)

    def _is_robots_allowed(self, url: str) -> bool:
        parsed = urlsplit(url)
        target_url = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")
        )
        if self._custom_robots_allowed is not None:
            if target_url not in self._robots_decisions:
                self._robots_decisions[target_url] = self._custom_robots_allowed(url)
            return self._robots_decisions[target_url]

        key = (parsed.scheme.casefold(), parsed.netloc.casefold())
        if key not in self._robots_policies:
            self._robots_policies[key] = self._default_robots_policy(url)
        return self._robots_policies[key](target_url)

    def _open_http_session(self) -> Any:
        if self._http_session is None:
            with ExitStack() as opening:
                session = opening.enter_context(self._http_session_factory())
                owned = opening.pop_all()
            self._resources.callback(owned.close)
            self._http_session = session
        return self._http_session

    def _profile_for(self, source: SourceConfig) -> Path | None:
        try:
            profile_dir = _profile_directory(source.code, self._profile_root)
        except RuntimeError:
            if source.requires_auth:
                raise
            return None
        if source.requires_auth or (profile_dir / _PROFILE_READY_MARKER).is_file():
            return profile_dir
        return None

    def _open_browser_session(
        self, source: SourceConfig, profile_dir: Path | None
    ) -> Any:
        session_key = source.code if profile_dir is not None else "__public__"
        if session_key in self._browser_sessions:
            return self._browser_sessions[session_key]

        options: dict[str, object] = {
            "headless": True,
            "network_idle": False,
            "timeout": 30_000,
            "retries": 1,
        }
        with ExitStack() as opening:
            if profile_dir is not None:
                opening.enter_context(_ProfileLock(profile_dir))
                options["user_data_dir"] = str(profile_dir)
            session = opening.enter_context(self._browser_session_factory(**options))
            owned = opening.pop_all()
        self._resources.callback(owned.close)
        self._browser_sessions[session_key] = session
        return session

    def _request(self, url: str, source: SourceConfig) -> ResponseLike:
        profile_dir = self._profile_for(source)
        uses_browser = profile_dir is not None or source.kind in {
            SourceKind.DYNAMIC,
            SourceKind.GUPY,
        }
        if not uses_browser:
            if self._http_get is not None:
                return self._http_get(url)
            return self._open_http_session().get(url)

        if self._browser_fetch is not None:
            return self._browser_fetch(url)
        wait_selector = (
            "a[href*='/job/']"
            if source.kind is SourceKind.GUPY
            else source.selectors.get("card")
        )
        request_timeout = 60_000 if source.code == "eureca" else 30_000
        fetch_options: dict[str, object] = {
            "network_idle": False,
            "timeout": request_timeout,
        }
        if wait_selector:
            fetch_options["wait_selector"] = wait_selector
        if source.code == "infojobs":
            fetch_options["page_action"] = _scroll_infojobs_until_stable
        elif source.code == "ciee":
            fetch_options["page_action"] = _load_ciee_until_stable
        return self._open_browser_session(source, profile_dir).fetch(
            url, **fetch_options
        )

    def fetch(self, url: str, source: SourceConfig) -> FetchResult:
        safe_url = _safe_url(url)
        if not self._is_robots_allowed(url):
            return FetchResult(
                status=CollectionStatus.BLOCKED,
                block_reason=BlockReason.ROBOTS_DENIED,
                error=f"ROBOTS_DENIED em {safe_url}",
            )

        self._throttle(source)
        for attempt in range(1, self._max_attempts + 1):
            self._last_request_at[source.code] = self._monotonic()
            try:
                response = self._request(url, source)
            except Exception as error:
                is_timeout = isinstance(error, TimeoutError) or (
                    type(error).__name__ == "TimeoutError"
                )
                if is_timeout and attempt < self._max_attempts:
                    self._sleep(max(source.min_interval_seconds, float(attempt)))
                    continue
                if is_timeout:
                    return FetchResult(
                        status=CollectionStatus.BLOCKED,
                        block_reason=BlockReason.TIMEOUT,
                        error=f"{type(error).__name__} ao acessar {safe_url}",
                        attempts=attempt,
                    )
                return FetchResult(
                    status=CollectionStatus.ERROR,
                    error=f"Falha de coleta ({type(error).__name__}) em {safe_url}",
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
