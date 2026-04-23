import threading

from backend.services.shared_browser import shared_browser_service


class _FakeLocator:
    def inner_text(self, timeout=1500):
        return ""

    @property
    def first(self):
        return self

    def click(self, timeout=15000):
        return None

    def fill(self, text, timeout=15000):
        return None

    def type(self, text, timeout=15000):
        return None

    def wait_for(self, timeout=1000):
        return None


class _FakePage:
    def __init__(self):
        self.url = "https://example.com/"

    def title(self):
        return "Example Domain"

    def locator(self, selector):
        return _FakeLocator()

    def goto(self, url, wait_until="domcontentloaded", timeout=60000):
        self.url = url

    def wait_for_timeout(self, ms):
        return None

    def screenshot(self, path, full_page=False):
        with open(path, "wb") as f:
            f.write(b"fake")


class _FakeContext:
    def __init__(self):
        self.pages = [_FakePage()]

    def new_page(self):
        return self.pages[0]

    def close(self):
        return None


class _FakeChromium:
    def launch_persistent_context(self, **kwargs):
        return _FakeContext()


class _FakePlaywright:
    def __init__(self):
        self.chromium = _FakeChromium()

    def stop(self):
        return None


class _FakeSyncPlaywright:
    def start(self):
        return _FakePlaywright()


def test_shared_browser_session_marshals_actions_to_single_owner_thread(monkeypatch):
    monkeypatch.setattr(
        "backend.services.shared_browser.sync_playwright",
        lambda: _FakeSyncPlaywright(),
        raising=False,
    )
    monkeypatch.setattr(
        "backend.services.shared_browser.SharedBrowserSession._ensure_browser_runtime_installed_locked",
        lambda self: None,
    )

    session = shared_browser_service.get("thread-marshal-test")
    session.stop()

    owner_thread_ids = []
    original_refresh = session._refresh_page_state_locked

    def wrapped_refresh():
        owner_thread_ids.append(threading.get_ident())
        return original_refresh()

    monkeypatch.setattr(session, "_refresh_page_state_locked", wrapped_refresh)

    start_result = session.start("https://example.com")
    assert start_result["success"] is True

    handoff_result = session.handoff()
    assert handoff_result["success"] is True

    results = {}

    def run_resume():
        results["resume"] = session.resume()

    thread = threading.Thread(target=run_resume)
    thread.start()
    thread.join(timeout=5)

    assert thread.is_alive() is False
    assert results["resume"]["success"] is True
    assert session.status()["success"] is True
    assert len(set(owner_thread_ids)) == 1

    session.stop()
