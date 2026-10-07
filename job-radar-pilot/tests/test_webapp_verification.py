from contextlib import contextmanager
import json
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from job_radar.output_lock import OutputBusyError, OutputLock
from job_radar.webapp import SearchController, create_server


@contextmanager
def _api(tmp_path, controller):
    static = tmp_path / "web"
    static.mkdir(exist_ok=True)
    server = create_server("127.0.0.1", 0, controller, static)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(path, payload=None, method="GET"):
        data = None if payload is None else json.dumps(payload).encode()
        req = Request(
            f"http://127.0.0.1:{server.server_port}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urlopen(req, timeout=2)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    try:
        yield request
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_verify_api_progress_and_exclusion_cover_entire_background_run(tmp_path):
    entered, release = Event(), Event()

    def runner(output, progress):
        progress(1, 2, {"LINK:LIVE": 1, "LINK:DEAD": 0, "LINK:UNKNOWN": 0})
        entered.set()
        release.wait(5)
        return {
            "checked": 2,
            "total": 2,
            "LINK:LIVE": 1,
            "LINK:DEAD": 1,
            "LINK:UNKNOWN": 0,
        }

    controller = SearchController(
        tmp_path / "output", runner=lambda *_: 0, verification_runner=runner
    )
    try:
        with _api(tmp_path, controller) as api:
            assert api("/api/verify-links", {}, "POST")[0] == 202
            assert entered.wait(2)
            status, state = api("/api/state")
            assert status == 200
            assert state["verification"]["status"] == "RUNNING"
            assert state["verification"]["checked"] == 1
            assert state["verification"]["total"] == 2
            assert state["verification"]["counts"]["LINK:LIVE"] == 1
            for path, payload, method in (
                ("/api/verify-links", {}, "POST"),
                ("/api/search", {}, "POST"),
                ("/api/cleanup", {}, "POST"),
                ("/api/cleanup/undo", {}, "POST"),
                (
                    "/api/linkedin/import",
                    {"text": "https://linkedin.com/jobs/view/1"},
                    "POST",
                ),
                ("/api/preferences?reapply=1", {}, "PUT"),
            ):
                assert api(path, payload, method)[0] == 409, path
            with pytest.raises(OutputBusyError):
                with OutputLock(controller.output_dir):
                    pass
            release.set()
            assert controller.wait_verification(2)
            finished = api("/api/state")[1]["verification"]
            assert finished["status"] == "DONE"
            assert finished["checked"] == 2
            assert finished["counts"]["LINK:DEAD"] == 1
    finally:
        release.set()


def test_verify_rejects_collection_before_cli_acquires_output_lock(tmp_path):
    entered, release = Event(), Event()

    def runner(*_):
        entered.set()
        release.wait(5)
        return 0

    controller = SearchController(tmp_path / "output", runner=runner)
    assert controller.start()
    try:
        assert entered.wait(2)
        with _api(tmp_path, controller) as api:
            assert api("/api/verify-links", {}, "POST")[0] == 409
    finally:
        release.set()
        assert controller.wait(2)


def test_verify_failure_releases_output_lock_and_allows_collection(tmp_path):
    def runner(*_):
        raise ValueError("Saída ilegível")

    controller = SearchController(
        tmp_path / "output", runner=lambda *_: 0, verification_runner=runner
    )
    with _api(tmp_path, controller) as api:
        assert api("/api/verify-links", {}, "POST")[0] == 202
        assert controller.wait_verification(2)
        state = api("/api/state")[1]["verification"]
        assert state["status"] == "ERROR"
        assert "Saída ilegível" in state["error"]
        with OutputLock(controller.output_dir):
            pass
        assert api("/api/search", {}, "POST")[0] == 202
        assert controller.wait(2)


def test_dashboard_verification_shows_progress_and_releases_buttons(tmp_path):
    from pathlib import Path
    from playwright.sync_api import expect, sync_playwright

    release = Event()

    def runner(output, progress):
        progress(1, 2, {"LINK:LIVE": 1, "LINK:DEAD": 0, "LINK:UNKNOWN": 0})
        release.wait(10)
        return {"checked": 2, "LINK:LIVE": 1, "LINK:UNKNOWN": 1}

    controller = SearchController(
        tmp_path / "output", runner=lambda *_: 0, verification_runner=runner
    )
    web = Path(__file__).resolve().parents[1] / "src" / "job_radar" / "web"
    server = create_server("127.0.0.1", 0, controller, web)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            button = page.get_by_role(
                "button", name="Verificar disponibilidade", exact=True
            )
            expect(button).to_be_visible(timeout=2000)
            button.click()
            expect(page.locator("#verification-status")).to_contain_text(
                "1 de 2", timeout=3000
            )
            expect(button).to_be_disabled()
            expect(page.locator("#search-button")).to_be_disabled()
            release.set()
            assert controller.wait_verification(2)
            expect(page.locator("#verification-status")).to_contain_text(
                "1 ativa", timeout=3000
            )
            expect(page.locator("#verification-status")).to_contain_text(
                "1 não comprovada"
            )
            expect(button).to_be_enabled()
            assert (
                page.evaluate(
                    "activityState({observed_at: new Date(Date.now()+86400000).toISOString()})"
                )
                == "UNKNOWN"
            )
            assert (
                page.evaluate(
                    'activityState({match_labels:["LINK:LIVE", "LINK_CHECK_METHOD:JOB_DETAIL_V2", "LINK_CHECKED_AT:"+new Date().toISOString()]})'
                )
                == "ACTIVE_CONFIRMED"
            )
            browser.close()
    finally:
        release.set()
        controller.wait_verification(2)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_external_output_lock_rejects_verification_without_stale_running_status(
    tmp_path,
):
    controller = SearchController(tmp_path / "output", runner=lambda *_: 0)
    with _api(tmp_path, controller) as api:
        with OutputLock(controller.output_dir):
            assert api("/api/verify-links", {}, "POST")[0] == 409
        assert api("/api/state")[1]["verification"]["status"] == "IDLE"
