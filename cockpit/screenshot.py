"""
Cockpit Screenshot Service
============================

Captures screenshots of the virtual cockpit UI via Playwright.
Replaces ADB screencap for the HybridStress benchmark.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CockpitScreenshotter:
    """
    Captures screenshots of the cockpit web UI using Playwright.
    The cockpit server must be running on the specified URL.
    """

    def __init__(self, cockpit_url: str = "http://localhost:8420", headless: bool = True):
        self.cockpit_url = cockpit_url
        self.headless = headless
        self._browser = None
        self._page = None
        self._playwright = None

    def start(self):
        """Launch the headless browser and navigate to the cockpit."""
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._page = self._browser.new_page(viewport={"width": 1280, "height": 720})
        self._page.goto(self.cockpit_url)
        self._page.wait_for_load_state("networkidle")
        logger.info(f"Screenshot service started: {self.cockpit_url}")

    def capture(self, save_path: str, wait_ms: int = 500) -> str:
        """
        Capture a screenshot of the cockpit and save to disk.
        Returns the save path.
        """
        if self._page is None:
            self.start()

        # Refresh state display before capture
        self._page.evaluate("() => { if (window.refreshState) window.refreshState(); }")
        time.sleep(wait_ms / 1000.0)

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        self._page.screenshot(path=save_path, full_page=False)
        logger.debug(f"Screenshot captured: {save_path}")
        return save_path

    def refresh(self):
        """Force refresh the page to sync with latest state."""
        if self._page:
            self._page.reload()
            self._page.wait_for_load_state("networkidle")

    def stop(self):
        """Close the browser."""
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        self._page = None
        logger.info("Screenshot service stopped")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


# ---------------------------------------------------------------------------
# Convenience function (replaces capture_screenshot_adb)
# ---------------------------------------------------------------------------

_global_screenshotter: Optional[CockpitScreenshotter] = None


def get_screenshotter(cockpit_url: str = "http://localhost:8420") -> CockpitScreenshotter:
    """Get or create the global screenshotter singleton."""
    global _global_screenshotter
    if _global_screenshotter is None:
        _global_screenshotter = CockpitScreenshotter(cockpit_url)
        _global_screenshotter.start()
    return _global_screenshotter


def capture_screenshot_cockpit(save_path: str, cockpit_url: str = "http://localhost:8420") -> str:
    """Drop-in replacement for capture_screenshot_adb."""
    screenshotter = get_screenshotter(cockpit_url)
    return screenshotter.capture(save_path)


def stop_screenshotter():
    """Shut down the global screenshotter."""
    global _global_screenshotter
    if _global_screenshotter:
        _global_screenshotter.stop()
        _global_screenshotter = None
