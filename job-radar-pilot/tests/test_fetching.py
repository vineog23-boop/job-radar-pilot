from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pytest

import job_radar.fetching as fetching
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


@pytest.mark.parametrize(
    "url",
    [
        "https://linkedin.com/jobs",
        "https://www.linkedin.com/jobs",
        "https://br.linkedin.com/jobs",
    ],
)
def test_linkedin_is_manual_only_even_under_source_alias(url: str) -> None:
    calls: list[str] = []
    policy = FetchPolicy(
        http_get=lambda target: calls.append(target),
        browser_fetch=lambda target: calls.append(target),
        robots_allowed=lambda target: calls.append(f"robots:{target}") or True,
        sleep=lambda seconds: None,
    )

    result = policy.fetch(url, replace(_source(), code="portal-alias"))

    assert result.status is CollectionStatus.BLOCKED
    assert result.block_reason is BlockReason.ROBOTS_DENIED
    assert result.attempts == 0
    assert calls == []


def test_linkedin_lookalike_domain_is_not_misclassified() -> None:
    calls: list[str] = []
    policy = FetchPolicy(
        http_get=lambda url: calls.append(url) or FakeResponse(url=url),
        browser_fetch=lambda url: FakeResponse(url=url),
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    )

    result = policy.fetch("https://linkedin.com.example.test/jobs", _source())

    assert result.status is CollectionStatus.SUCCESS
    assert calls == ["https://linkedin.com.example.test/jobs"]


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
    assert result.error == (
        "RATE_LIMITED; signal=http:429; url=https://example.com/jobs"
    )


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
    assert result.error == (
        f"ACCESS_DENIED; signal=http:{status}; url=https://example.com/jobs"
    )


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (FakeResponse(url="https://example.com/login"), BlockReason.LOGIN_REQUIRED),
        (FakeResponse(url="https://secure.example.com/auth"), BlockReason.LOGIN_REQUIRED),
        (FakeResponse(text="Complete o CAPTCHA para continuar"), BlockReason.CAPTCHA),
        (FakeResponse(text="Digite o codigo de verificacao em duas etapas"), BlockReason.TWO_FACTOR),
        (FakeResponse(text="Detectamos atividade incomum na sua conta"), BlockReason.ACTIVITY_ALERT),
    ],
)
def test_detects_interactive_blocks(
    response: FakeResponse, reason: BlockReason
) -> None:
    assert detect_block(response) is reason


@pytest.mark.parametrize("path", ["login", "signin", "sign-in", "auth"])
def test_login_path_uses_exact_segment_and_reports_fixed_signal(path: str) -> None:
    response = FakeResponse(url=f"https://example.com/jobs/{path}?token=secret")
    policy = FetchPolicy(
        http_get=lambda url: response,
        browser_fetch=lambda url: response,
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    )

    result = policy.fetch(response.url, _source())

    assert result.block_reason is BlockReason.LOGIN_REQUIRED
    assert result.error == (
        f"LOGIN_REQUIRED; signal=/{path}; url=https://example.com/jobs/{path}"
    )


def test_login_like_path_is_not_classified_as_authentication() -> None:
    response = FakeResponse(url="https://example.com/jobs/login-help")

    assert detect_block(response) is None


def test_block_detection_ignores_tracking_hashes_and_inactive_captcha_widgets() -> None:
    response = FakeResponse(
        text=(
            '<link href="/icons/abc232fa.png">'
            '<form hidden><div class="g-recaptcha" data-sitekey=""></div></form>'
            '<main><h1>Vagas abertas</h1></main>'
        )
    )

    assert detect_block(response) is None


def test_block_detection_ignores_two_factor_markers_inside_scripts() -> None:
    response = FakeResponse(
        text=(
            '<script>window.routes={twoFactor:"/2fa", label:"two-factor authentication"}</script>'
            '<main><h1>Vagas abertas</h1></main>'
        )
    )

    assert detect_block(response) is None


@pytest.mark.parametrize(
    "hidden_markup",
    [
        '<style>.two-factor::after{content:"2fa"}</style>',
        '<div hidden>Two-factor authentication</div>',
        '<div aria-hidden="true">Two-factor authentication</div>',
        '<div style="display: none">Two-factor authentication</div>',
        '<div style="visibility: hidden">Two-factor authentication</div>',
    ],
)
def test_block_detection_ignores_hidden_two_factor_markers(
    hidden_markup: str,
) -> None:
    response = FakeResponse(
        text=f"<html><body>{hidden_markup}<main>Vagas abertas</main></body></html>"
    )

    assert detect_block(response) is None


def test_visible_parser_handles_void_tags_without_hiding_following_content() -> None:
    response = FakeResponse(
        text=(
            '<html><head><meta charset="utf-8"></head><body>'
            '<input type="hidden"><br>Two-factor authentication'
            "</body></html>"
        )
    )

    assert detect_block(response) is BlockReason.TWO_FACTOR


def test_visible_two_factor_marker_remains_detectable() -> None:
    response = FakeResponse(
        text="<html><body><main>Use 2FA para continuar</main></body></html>"
    )

    assert detect_block(response) is BlockReason.TWO_FACTOR


def test_fetch_reports_fixed_visible_block_signal_without_response_body() -> None:
    response = FakeResponse(
        text=(
            '<script>const token="secret";</script>'
            '<main>Two-factor authentication necessária</main>'
        )
    )
    policy = FetchPolicy(
        http_get=lambda url: response,
        browser_fetch=lambda url: response,
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    )

    result = policy.fetch("https://example.com/jobs?token=secret", _source())

    assert result.block_reason is BlockReason.TWO_FACTOR
    assert result.error == (
        "TWO_FACTOR; signal=two-factor authentication; "
        "url=https://example.com/jobs"
    )
    assert "secret" not in result.error


class FakeSession:
    def __init__(self) -> None:
        self.entered = 0
        self.exited = 0
        self.urls: list[str] = []
        self.fetch_kwargs: list[dict[str, object]] = []

    def __enter__(self) -> "FakeSession":
        self.entered += 1
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.exited += 1

    def get(self, url: str) -> FakeResponse:
        self.urls.append(url)
        return FakeResponse(url=url)

    def fetch(self, url: str, **kwargs: object) -> FakeResponse:
        self.urls.append(url)
        self.fetch_kwargs.append(dict(kwargs))
        return FakeResponse(url=url)


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


def test_gupy_source_uses_browser_only() -> None:
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

    result = policy.fetch("https://portal.gupy.io/", _source(SourceKind.GUPY))

    assert result.status is CollectionStatus.SUCCESS
    assert calls == ["browser:https://portal.gupy.io/"]


def test_scrapling_dynamic_session_rejects_zero_retries() -> None:
    from scrapling.engines._browsers._controllers import DynamicSession

    with pytest.raises(TypeError, match="retries"):
        DynamicSession(retries=0)


def test_default_browser_fetch_uses_retry_count_accepted_by_scrapling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scrapling.fetchers import DynamicFetcher

    captured: dict[str, object] = {}

    def fake_fetch(cls: type, url: str, **kwargs: object) -> FakeResponse:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse(url=url)

    monkeypatch.setattr(DynamicFetcher, "fetch", classmethod(fake_fetch))

    response = FetchPolicy._default_browser_fetch("https://example.com/jobs")

    assert response.url == "https://example.com/jobs"
    assert captured == {
        "url": "https://example.com/jobs",
        "kwargs": {
            "headless": True,
            "network_idle": False,
            "timeout": 30_000,
            "retries": 1,
        },
    }


def test_default_robots_policy_reads_plain_text_response_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scrapling.fetchers import Fetcher

    @dataclass
    class RobotsResponse:
        status: int = 200
        text: str = ""
        body: bytes = b"User-agent: *\nDisallow: /private\nAllow: /jobs\n"

    monkeypatch.setattr(
        Fetcher,
        "get",
        classmethod(lambda cls, url, **kwargs: RobotsResponse()),
    )

    assert FetchPolicy._default_robots_allowed("https://example.com/jobs") is True
    assert FetchPolicy._default_robots_allowed("https://example.com/private") is False


def test_collection_error_keeps_exception_type_without_sensitive_details() -> None:
    def get(url: str) -> FakeResponse:
        raise RuntimeError("cookie=secret full-html=<html>token=abc</html>")

    policy = FetchPolicy(
        http_get=get,
        browser_fetch=get,
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    )

    result = policy.fetch("https://example.com/jobs?token=secret", _source())

    assert result.status is CollectionStatus.ERROR
    assert result.attempts == 1
    assert "RuntimeError" in (result.error or "")
    assert "secret" not in (result.error or "")
    assert "<html>" not in (result.error or "")


def test_playwright_named_timeout_retries_once() -> None:
    browser_timeout = type("TimeoutError", (Exception,), {})
    attempts = 0

    def get(url: str) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise browser_timeout("Page.goto exceeded")
        return FakeResponse(url=url)

    policy = FetchPolicy(
        http_get=get,
        browser_fetch=get,
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    )

    result = policy.fetch("https://example.com/jobs", _source())

    assert result.status is CollectionStatus.SUCCESS
    assert result.attempts == 2
    assert "?" not in (result.error or "")


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


def test_default_profile_root_is_outside_project_under_local_app_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert fetching.default_profile_root() == tmp_path / "JobRadar" / "profiles"


def test_policy_reuses_one_static_session_and_closes_it_after_collection() -> None:
    session = FakeSession()
    factory_calls = 0

    def factory() -> FakeSession:
        nonlocal factory_calls
        factory_calls += 1
        return session

    with FetchPolicy(
        http_session_factory=factory,
        browser_session_factory=lambda **kwargs: FakeSession(),
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    ) as policy:
        first = policy.fetch("https://example.com/jobs/1", _source())
        second = policy.fetch("https://example.com/jobs/2", _source())

        assert first.status is CollectionStatus.SUCCESS
        assert second.status is CollectionStatus.SUCCESS
        assert session.exited == 0

    assert factory_calls == 1
    assert session.urls == [
        "https://example.com/jobs/1",
        "https://example.com/jobs/2",
    ]
    assert session.entered == 1
    assert session.exited == 1


def test_authenticated_collection_reuses_source_profile_and_closes_browser(
    tmp_path: Path,
) -> None:
    session = FakeSession()
    factory_kwargs: list[dict[str, object]] = []

    def factory(**kwargs: object) -> FakeSession:
        factory_kwargs.append(dict(kwargs))
        return session

    authenticated = replace(
        _source(SourceKind.DYNAMIC),
        code="nube",
        requires_auth=True,
    )

    with FetchPolicy(
        browser_session_factory=factory,
        profile_root=tmp_path,
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    ) as policy:
        policy.fetch("https://example.com/jobs/1", authenticated)
        policy.fetch("https://example.com/jobs/2", authenticated)

    assert factory_kwargs == [
        {
            "headless": True,
            "network_idle": False,
            "timeout": 30_000,
            "retries": 1,
            "user_data_dir": str(tmp_path / "nube"),
        }
    ]
    assert session.urls == [
        "https://example.com/jobs/1",
        "https://example.com/jobs/2",
    ]
    assert session.fetch_kwargs == [
        {
            "network_idle": False,
            "timeout": 30_000,
            "wait_selector": "article",
        },
        {
            "network_idle": False,
            "timeout": 30_000,
            "wait_selector": "article",
        },
    ]
    assert session.exited == 1


def test_same_authenticated_profile_cannot_be_opened_in_parallel(tmp_path: Path) -> None:
    first_session = FakeSession()
    second_factory_calls = 0
    authenticated = replace(
        _source(SourceKind.DYNAMIC),
        code="nube",
        requires_auth=True,
    )
    first = FetchPolicy(
        browser_session_factory=lambda **kwargs: first_session,
        profile_root=tmp_path,
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    )

    def second_factory(**kwargs: object) -> FakeSession:
        nonlocal second_factory_calls
        second_factory_calls += 1
        return FakeSession()

    second = FetchPolicy(
        browser_session_factory=second_factory,
        profile_root=tmp_path,
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    )
    try:
        assert first.fetch("https://example.com/jobs", authenticated).status is CollectionStatus.SUCCESS

        result = second.fetch("https://example.com/jobs", authenticated)

        assert result.status is CollectionStatus.ERROR
        assert "ProfileInUseError" in (result.error or "")
        assert second_factory_calls == 0
    finally:
        first.close()
        second.close()


def test_bootstrap_auth_opens_headful_profile_waits_and_closes(
    tmp_path: Path,
) -> None:
    session = FakeSession()
    events: list[str] = []
    factory_kwargs: list[dict[str, object]] = []
    authenticated = replace(
        _source(SourceKind.DYNAMIC),
        code="nube",
        requires_auth=True,
    )

    def factory(**kwargs: object) -> FakeSession:
        factory_kwargs.append(dict(kwargs))
        return session

    def wait_for_user(message: str) -> str:
        events.append(message)
        assert session.urls == [authenticated.start_url]
        assert session.exited == 0
        return ""

    profile = fetching.bootstrap_auth(
        authenticated,
        profile_root=tmp_path,
        browser_session_factory=factory,
        input_func=wait_for_user,
    )

    assert profile == tmp_path / "nube"
    assert profile.is_dir()
    assert factory_kwargs == [
        {
            "headless": False,
            "network_idle": False,
            "timeout": 30_000,
            "retries": 1,
            "user_data_dir": str(tmp_path / "nube"),
        }
    ]
    assert len(events) == 1
    assert "senha" not in events[0].casefold()
    assert session.exited == 1


def test_bootstrap_auth_rejects_linkedin_before_creating_profile(tmp_path: Path) -> None:
    source = replace(
        _source(SourceKind.DYNAMIC),
        code="portal-alias",
        start_url="https://www.linkedin.com/login",
        requires_auth=True,
    )

    with pytest.raises(ValueError, match="manual"):
        fetching.bootstrap_auth(source, profile_root=tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_gupy_session_uses_bounded_readiness_action_without_card_timeout() -> None:
    session = FakeSession()
    source = _source(SourceKind.GUPY)

    with FetchPolicy(
        browser_session_factory=lambda **kwargs: session,
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    ) as policy:
        result = policy.fetch("https://portal.gupy.io/job-search/", source)

    assert result.status is CollectionStatus.SUCCESS
    assert len(session.fetch_kwargs) == 1
    options = dict(session.fetch_kwargs[0])
    action = options.pop("page_action")
    assert getattr(action, "__name__") == "_wait_gupy_results"
    assert options == {
        "network_idle": False,
        "timeout": 30_000,
        "wait_selector": "body",
    }


def test_infojobs_session_receives_bounded_scroll_action() -> None:
    session = FakeSession()
    source = replace(
        _source(SourceKind.DYNAMIC),
        code="infojobs",
        selectors={
            "card": ".js_vacanciesGridFragment > .js_rowCard",
            "title": ".js_vacancyTitle::all-text",
            "url": "a[href*='/vaga-de-']::attr(href)",
        },
    )

    with FetchPolicy(
        browser_session_factory=lambda **kwargs: session,
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    ) as policy:
        result = policy.fetch(source.start_url, source)

    assert result.status is CollectionStatus.SUCCESS
    action = session.fetch_kwargs[0].get("page_action")
    assert callable(action)
    assert getattr(action, "__name__") == "_scroll_infojobs_until_stable"


def test_infojobs_scroll_stops_when_card_count_stabilizes() -> None:
    counts = iter((21, 41, 41, 61, 61, 61))
    scrolls: list[str] = []

    class Locator:
        def count(self) -> int:
            return next(counts)

    class Page:
        def locator(self, selector: str) -> Locator:
            assert selector == ".js_vacanciesGridFragment > .js_rowCard"
            return Locator()

        def evaluate(self, script: str) -> None:
            scrolls.append(script)

        def wait_for_timeout(self, milliseconds: int) -> None:
            assert milliseconds == 700

    fetching._scroll_infojobs_until_stable(Page())

    assert len(scrolls) == 5


def test_gupy_readiness_action_tolerates_delayed_cards() -> None:
    counts = iter((0, 0, 2))
    waits: list[int] = []

    class Locator:
        def __init__(self, selector: str) -> None:
            self.selector = selector

        def count(self) -> int:
            assert self.selector == "#job-listing-results li"
            return next(counts)

    class Page:
        def locator(self, selector: str) -> Locator:
            return Locator(selector)

        def wait_for_timeout(self, milliseconds: int) -> None:
            waits.append(milliseconds)

    fetching._wait_gupy_results(Page())

    assert waits == [500, 500]


def test_gupy_readiness_action_stops_after_four_seconds_without_results() -> None:
    waits: list[int] = []

    class Locator:
        def count(self) -> int:
            return 0

    class Page:
        def locator(self, selector: str) -> Locator:
            assert selector == "#job-listing-results li"
            return Locator()

        def wait_for_timeout(self, milliseconds: int) -> None:
            waits.append(milliseconds)

    fetching._wait_gupy_results(Page())

    assert waits == [500] * 8


def test_ciee_load_more_waits_for_delayed_card_growth() -> None:
    counts = iter((6, 6, 12, 12, 18, 18, 18, 18, 18, 18, 18))
    clicks: list[bool] = []
    waits: list[int] = []

    class CardLocator:
        def count(self) -> int:
            return next(counts)

    class ButtonLocator:
        @property
        def last(self) -> "ButtonLocator":
            return self

        def count(self) -> int:
            return 1

        def is_visible(self) -> bool:
            return True

        def click(self, **kwargs: object) -> None:
            clicks.append(bool(kwargs.get("force")))

    class Page:
        def locator(self, selector: str) -> CardLocator | ButtonLocator:
            if selector == "a.vaga-row[href*='codigoVaga=']":
                return CardLocator()
            assert selector == ".btn-exibir-mais-vagas"
            return ButtonLocator()

        def wait_for_timeout(self, milliseconds: int) -> None:
            waits.append(milliseconds)

    fetching._load_ciee_until_stable(Page())

    assert clicks == [True, True, True]
    assert waits == [500] * 8


def test_robots_parser_is_cached_per_origin_but_evaluates_each_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scrapling.fetchers import Fetcher

    robots_calls: list[str] = []

    @dataclass
    class RobotsResponse:
        status: int = 200
        text: str = ""
        body: bytes = b"User-agent: *\nAllow: /public\nDisallow: /private\n"

    def fetch_robots(cls: type, url: str, **kwargs: object) -> RobotsResponse:
        robots_calls.append(url)
        return RobotsResponse()

    monkeypatch.setattr(Fetcher, "get", classmethod(fetch_robots))
    policy = FetchPolicy(
        http_get=lambda url: FakeResponse(url=url),
        browser_fetch=lambda url: FakeResponse(url=url),
        sleep=lambda seconds: None,
    )

    public = policy.fetch("https://example.com/public/1", _source())
    private = policy.fetch("https://example.com/private/1", _source())
    another_public = policy.fetch("https://example.com/public/2", _source())

    assert public.status is CollectionStatus.SUCCESS
    assert private.status is CollectionStatus.BLOCKED
    assert private.block_reason is BlockReason.ROBOTS_DENIED
    assert another_public.status is CollectionStatus.SUCCESS
    assert robots_calls == ["https://example.com/robots.txt"]


def test_public_source_reuses_profile_created_by_auth(tmp_path: Path) -> None:
    auth_session = FakeSession()
    source = replace(_source(SourceKind.GENERIC), code="infojobs")
    fetching.bootstrap_auth(
        source,
        profile_root=tmp_path,
        browser_session_factory=lambda **kwargs: auth_session,
        input_func=lambda message: "",
    )
    collection_session = FakeSession()
    collection_options: list[dict[str, object]] = []

    def collection_factory(**kwargs: object) -> FakeSession:
        collection_options.append(dict(kwargs))
        return collection_session

    with FetchPolicy(
        http_get=lambda url: FakeResponse(url=url),
        browser_session_factory=collection_factory,
        profile_root=tmp_path,
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    ) as policy:
        result = policy.fetch(source.start_url, source)

    assert result.status is CollectionStatus.SUCCESS
    assert collection_options == [
        {
            "headless": True,
            "network_idle": False,
            "timeout": 30_000,
            "retries": 1,
            "user_data_dir": str(tmp_path / "infojobs"),
        }
    ]
    assert collection_session.urls == [source.start_url]


def test_public_persisted_profile_cannot_be_opened_in_parallel(tmp_path: Path) -> None:
    source = replace(_source(SourceKind.GENERIC), code="infojobs")
    fetching.bootstrap_auth(
        source,
        profile_root=tmp_path,
        browser_session_factory=lambda **kwargs: FakeSession(),
        input_func=lambda message: "",
    )
    first = FetchPolicy(
        http_get=lambda url: FakeResponse(url=url),
        browser_session_factory=lambda **kwargs: FakeSession(),
        profile_root=tmp_path,
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    )
    second_factory_calls = 0

    def second_factory(**kwargs: object) -> FakeSession:
        nonlocal second_factory_calls
        second_factory_calls += 1
        return FakeSession()

    second = FetchPolicy(
        http_get=lambda url: FakeResponse(url=url),
        browser_session_factory=second_factory,
        profile_root=tmp_path,
        robots_allowed=lambda url: True,
        sleep=lambda seconds: None,
    )
    try:
        assert first.fetch(source.start_url, source).status is CollectionStatus.SUCCESS

        result = second.fetch(source.start_url, source)

        assert result.status is CollectionStatus.ERROR
        assert "ProfileInUseError" in (result.error or "")
        assert second_factory_calls == 0
    finally:
        first.close()
        second.close()
