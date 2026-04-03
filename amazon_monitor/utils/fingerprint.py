"""
Playwright stealth / anti-detection helpers.

Patches the Playwright page object to hide automation signals that Amazon
and other bot-detection systems look for:
  - navigator.webdriver = false
  - navigator.plugins populated
  - languages set to real-world values
  - Removed chrome.runtime automation flag
  - Realistic screen/window dimensions
  - Random mouse movement before navigation
"""
from __future__ import annotations

import asyncio
import random
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# JS patch injected into every new page before any navigation
# ------------------------------------------------------------------
_STEALTH_JS = """
// 1. Remove webdriver flag
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// 2. Realistic plugin array
const makePlugin = (name, desc, suffix, type) => {
  const plugin = Object.create(Plugin.prototype);
  Object.defineProperty(plugin, 'name',        {get: () => name});
  Object.defineProperty(plugin, 'description', {get: () => desc});
  Object.defineProperty(plugin, 'filename',    {get: () => suffix});
  const mime = Object.create(MimeType.prototype);
  Object.defineProperty(mime, 'type',          {get: () => type});
  Object.defineProperty(mime, 'suffixes',      {get: () => suffix});
  Object.defineProperty(mime, 'description',   {get: () => desc});
  Object.defineProperty(mime, 'enabledPlugin', {get: () => plugin});
  plugin[0] = mime;
  return plugin;
};
const plugins = [
  makePlugin('PDF Viewer',    'Portable Document Format', 'pdf', 'application/pdf'),
  makePlugin('Chrome PDF Viewer', 'Portable Document Format', 'pdf', 'application/pdf'),
  makePlugin('Chromium PDF Viewer','Portable Document Format','pdf','application/pdf'),
  makePlugin('Microsoft Edge PDF Viewer','Portable Document Format','pdf','application/pdf'),
  makePlugin('WebKit built-in PDF','Portable Document Format','pdf','application/pdf'),
];
Object.defineProperty(navigator, 'plugins', {get: () => plugins});
Object.defineProperty(navigator, 'mimeTypes', {get: () => ({length: 5})});

// 3. Languages
Object.defineProperty(navigator, 'languages', {get: () => ['en-IN', 'en', 'hi']});
Object.defineProperty(navigator, 'language',  {get: () => 'en-IN'});

// 4. Remove chrome.runtime cdc flag
if (window.chrome && window.chrome.runtime) {
  const originalRuntime = window.chrome.runtime;
  window.chrome = { ...window.chrome, runtime: { ...originalRuntime } };
}

// 5. Permissions API spoof
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
  parameters.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : originalQuery(parameters);
"""


async def apply_stealth(page: Any) -> None:
    """Inject stealth JS on every new page before navigation."""
    try:
        await page.add_init_script(_STEALTH_JS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Stealth JS injection failed: %s", exc)


async def human_mouse_movement(page: Any) -> None:
    """
    Simulate brief human-like cursor movement after page load.
    Moves the mouse in a small arc across the viewport.
    """
    try:
        vp = page.viewport_size or {"width": 1280, "height": 720}
        # Random start point near top-left
        sx = random.randint(100, 400)
        sy = random.randint(100, 300)
        # Move in 3—5 small steps
        steps = random.randint(3, 6)
        for i in range(steps):
            tx = sx + random.randint(-60, 180) * (i + 1)
            ty = sy + random.randint(-40, 120) * (i + 1)
            tx = max(10, min(tx, vp["width"] - 10))
            ty = max(10, min(ty, vp["height"] - 10))
            await page.mouse.move(tx, ty)
            await asyncio.sleep(random.uniform(0.05, 0.18))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Mouse movement skipped: %s", exc)


async def random_scroll(page: Any) -> None:
    """Scroll down the page in a natural, jittery fashion."""
    try:
        total = random.randint(200, 700)
        steps = random.randint(3, 7)
        per_step = total // steps
        for _ in range(steps):
            delta = per_step + random.randint(-30, 30)
            await page.evaluate(f"window.scrollBy(0, {delta})")
            await asyncio.sleep(random.uniform(0.15, 0.45))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Scroll skipped: %s", exc)


# Realistic viewport sizes used when launching browser
VIEWPORT_POOL = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 800},
]


def random_viewport() -> dict:
    return random.choice(VIEWPORT_POOL)
