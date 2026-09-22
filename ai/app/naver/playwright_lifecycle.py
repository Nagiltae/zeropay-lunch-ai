"""장시간 단일 worker 배치에서 Playwright browser/context/page 생명주기를 관리한다."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress

_LIFECYCLE_MARKERS = (
    "TARGET PAGE, CONTEXT OR BROWSER HAS BEEN CLOSED",
    "BROWSER HAS BEEN CLOSED",
    "CONTEXT HAS BEEN CLOSED",
    "PAGE HAS BEEN CLOSED",
    "TARGET CLOSED",
    "CONNECTION CLOSED",
)


def is_playwright_lifecycle_error(error: BaseException) -> bool:
    """Recognize transport/lifecycle failures, not HTTP policy failures."""
    message = str(error).upper()
    return any(marker in message for marker in _LIFECYCLE_MARKERS)


class PlaywrightLifecycle:
    """Reuse one browser in a CLI batch and recover only closed Playwright state."""

    def __init__(
        self,
        playwright,
        *,
        timeout_ms: int = 15_000,
        on_event: Callable[[str], None] | None = None,
    ) -> None:
        self.playwright = playwright
        self.timeout_ms = timeout_ms
        self._on_event = on_event or (lambda _event: None)
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        self.browser = self.playwright.chromium.launch(headless=True)
        self._on_event("browser_start")
        self._create_context_page()
        return self.page

    def _create_context_page(self) -> None:
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.page.set_default_timeout(self.timeout_ms)

    def _browser_connected(self) -> bool:
        try:
            return self.browser is not None and self.browser.is_connected()
        except Exception:
            return False

    def is_usable(self) -> bool:
        if not self._browser_connected() or self.context is None or self.page is None:
            return False
        try:
            return not self.page.is_closed()
        except Exception:
            return False

    def recover_after(self, error: BaseException) -> bool:
        """Recover after a failed item; return whether a restart occurred."""
        if not is_playwright_lifecycle_error(error):
            return False
        if self._browser_connected():
            self._close_context()
            self._create_context_page()
            self._on_event("page_recreate")
            return True
        self._close_browser()
        self.start()
        self._on_event("browser_restart")
        return True

    def recover_if_unusable(self) -> bool:
        if self.is_usable():
            return False
        return self.recover_after(
            RuntimeError("Playwright target page, context or browser has been closed")
        )

    def _close_context(self) -> None:
        if self.context is not None:
            with suppress(Exception):
                self.context.close()
        self.context = None
        self.page = None

    def _close_browser(self) -> None:
        self._close_context()
        if self.browser is not None:
            with suppress(Exception):
                self.browser.close()
        self.browser = None

    def close(self) -> None:
        self._close_browser()
