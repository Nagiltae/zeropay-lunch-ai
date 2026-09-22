"""단일 Playwright worker의 browser/context/page 재사용과 복구 판정을 검증한다."""

from app.naver.playwright_lifecycle import PlaywrightLifecycle, is_playwright_lifecycle_error


class FakePage:
    def __init__(self):
        self.closed = False
        self.timeout = None

    def set_default_timeout(self, timeout):
        self.timeout = timeout

    def is_closed(self):
        return self.closed


class FakeContext:
    def __init__(self):
        self.pages_created = []
        self.closed = False

    def new_page(self):
        page = FakePage()
        self.pages_created.append(page)
        return page

    def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self):
        self.connected = True
        self.contexts = []
        self.closed = False

    def new_context(self):
        context = FakeContext()
        self.contexts.append(context)
        return context

    def is_connected(self):
        return self.connected

    def close(self):
        self.closed = True
        self.connected = False


class FakeChromium:
    def __init__(self):
        self.browsers = []

    def launch(self, *, headless):
        assert headless is True
        browser = FakeBrowser()
        self.browsers.append(browser)
        return browser


class FakePlaywright:
    def __init__(self):
        self.chromium = FakeChromium()


def test_batch_reuses_browser_and_recovers_closed_page_without_new_browser():
    events = []
    session = PlaywrightLifecycle(FakePlaywright(), on_event=events.append)
    first_page = session.start()
    first_page.closed = True

    assert session.recover_if_unusable() is True
    assert len(session.playwright.chromium.browsers) == 1
    assert events == ["browser_start", "page_recreate"]
    assert session.is_usable()
    session.close()


def test_browser_disconnect_restarts_only_for_lifecycle_failure():
    events = []
    session = PlaywrightLifecycle(FakePlaywright(), on_event=events.append)
    session.start()
    session.browser.connected = False

    assert session.recover_after(
        RuntimeError("Target page, context or browser has been closed")
    ) is True
    assert len(session.playwright.chromium.browsers) == 2
    assert events == ["browser_start", "browser_start", "browser_restart"]
    session.close()


def test_non_lifecycle_error_does_not_restart():
    session = PlaywrightLifecycle(FakePlaywright())
    session.start()
    assert session.recover_after(RuntimeError("selector not found")) is False
    assert len(session.playwright.chromium.browsers) == 1
    assert is_playwright_lifecycle_error(RuntimeError("Target closed"))
    assert not is_playwright_lifecycle_error(RuntimeError("HTTP 429 BLOCKED"))
    session.close()
