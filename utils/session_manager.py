import logging
from pathlib import Path
from filelock import FileLock, Timeout
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

AUTH_DIR = Path("playwright/.auth")


def _get_session_file(email: str = None) -> Path:
    """Return the per-user session file path, creating the directory if needed."""
    if email is None:
        from config.settings import LOGIN_EMAIL
        email = LOGIN_EMAIL
    safe = email.lower().replace("@", "_").replace(".", "_")
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    return AUTH_DIR / "session_{}.json".format(safe)


def _get_lock_file(email: str = None) -> Path:
    """Return the per-user lock file path (used to prevent race conditions)."""
    session_file = _get_session_file(email)
    return session_file.with_suffix(".lock")


def get_session_file(email: str = None) -> Path:
    """Public accessor for the per-user session file path."""
    return _get_session_file(email)


def session_exists(email: str = None) -> bool:
    """Return True only if a session file exists for this user (no age check)."""
    f = _get_session_file(email)
    if not f.exists():
        print("[SESSION] No session file found")
        logger.info("No session file found for: %s", email or "default user")
        return False
    print("[SESSION] Session file found for: {}".format(email or "default user"))
    logger.info("Session file found for: %s", email or "default user")
    return True


def delete_session(email: str = None):
    f = _get_session_file(email)
    if f.exists():
        f.unlink()
        print("[SESSION] Session deleted: {}".format(f.name))
        logger.info("Session deleted: %s", f.name)


async def create_session(base_url: str, viewport: dict):
    """
    Fully automatic login — reads credentials from config/settings.py.
    No manual interaction, no Enter press needed.
    Saves session to playwright/.auth/session_<email>.json

    File-locked per user: if two processes attempt login simultaneously,
    the second waits for the first to finish, then reuses the session it created.
    """
    # ── Pull credentials from config ────────────────────────
    from config.settings import LOGIN_EMAIL, LOGIN_PASSWORD, HEADLESS

    if not LOGIN_EMAIL:
        raise ValueError(
            "[SESSION] LOGIN_EMAIL not set in config/settings.py"
        )
    if not LOGIN_PASSWORD:
        raise EnvironmentError(
            "[SESSION] AVERTEX_PASSWORD environment variable is not set. "
            "Set it before running: set AVERTEX_PASSWORD=your_password"
        )

    session_file = _get_session_file(LOGIN_EMAIL)
    lock_file    = _get_lock_file(LOGIN_EMAIL)

    # ── Acquire per-user file lock (timeout after 120s) ──────
    # If another process already holds the lock (i.e., is logging in),
    # we wait. Once released, we check if the session file now exists
    # and skip the full login if so.
    print("[SESSION] Acquiring session lock: {}".format(lock_file.name))
    logger.info("Acquiring session lock: %s", lock_file.name)

    try:
        lock = FileLock(str(lock_file), timeout=120)
    except Exception as e:
        logger.error("Failed to create lock object: %s", e)
        raise

    with lock:
        # ── Second-process fast-path: session was created while we were waiting ──
        if session_file.exists():
            print("[SESSION] Session already created by another process — reusing ✓")
            logger.info("Session reused (created by parallel process): %s", session_file.name)
            return

        print("\n[SESSION] Auto-login starting for: {}".format(LOGIN_EMAIL))
        logger.info("Auto-login starting for: %s", LOGIN_EMAIL)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=HEADLESS,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                context = await browser.new_context(
                    viewport=viewport,
                    ignore_https_errors=True,
                )
                page = await context.new_page()

                try:
                    await page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
                except PlaywrightTimeout as e:
                    logger.error("Timed out loading login page (%s): %s", base_url, e)
                    print("[SESSION] ERROR: Login page load timed out: {}".format(e))
                    raise

                # ── Step 1: Email ────────────────────────────
                try:
                    await page.wait_for_selector(
                        "#i0116, input[type='email']", timeout=10000
                    )
                    await page.fill("#i0116, input[type='email']", LOGIN_EMAIL)
                    await page.click(
                        "#idSIButton9, input[type='submit'], button:has-text('Next')"
                    )
                    print("[SESSION] ✓ Email submitted")
                    logger.info("Email submitted")
                    await page.wait_for_timeout(2000)
                except PlaywrightTimeout as e:
                    logger.error("Email field not found (timeout): %s", e)
                    print("[SESSION] ERROR: Email field not found: {}".format(e))
                    raise

                # ── Step 2: Password ─────────────────────────
                try:
                    await page.wait_for_selector(
                        "#i0118, input[type='password']", timeout=10000
                    )
                    await page.fill("#i0118, input[type='password']", LOGIN_PASSWORD)
                    await page.click(
                        "#idSIButton9, input[type='submit'], button:has-text('Sign in')"
                    )
                    print("[SESSION] ✓ Password submitted")
                    logger.info("Password submitted")
                    await page.wait_for_timeout(2000)
                except PlaywrightTimeout as e:
                    logger.error("Password field not found (timeout): %s", e)
                    print("[SESSION] ERROR: Password field not found: {}".format(e))
                    raise

                # ── Step 3: "Stay signed in?" prompt (optional) ──
                try:
                    await page.wait_for_selector(
                        "#idSIButton9, button:has-text('Yes')", timeout=6000
                    )
                    await page.click("#idSIButton9, button:has-text('Yes')")
                    print("[SESSION] ✓ Stay signed in clicked")
                    logger.info("Stay signed in clicked")
                except PlaywrightTimeout:
                    # Not always shown — expected, safe to skip
                    logger.debug("Stay signed in prompt not shown — skipping")

                # ── Step 4: Wait until app URL is reached ────
                app_host = base_url.replace("https://", "").replace("http://", "").rstrip("/")
                try:
                    await page.wait_for_url(
                        lambda u: app_host in u,
                        timeout=20000
                    )
                    print("[SESSION] ✓ App loaded: {}".format(page.url))
                    logger.info("App loaded after login: %s", page.url)
                except PlaywrightTimeout:
                    # App may have loaded with a slightly different URL — save anyway
                    await page.wait_for_timeout(5000)
                    print("[SESSION] ⚠ URL wait timed out — saving anyway: {}".format(page.url))
                    logger.warning("URL wait timed out after login — saving session anyway: %s", page.url)

                # ── Step 5: Save session per user ────────────
                await context.storage_state(path=str(session_file))
                print("[SESSION] ✓ Session saved: {}\n".format(session_file.name))
                logger.info("Session saved: %s", session_file.name)

            except Exception as e:
                logger.error("create_session failed: %s", e)
                raise
            finally:
                await browser.close()


async def load_session(playwright, headless: bool, viewport: dict, args: list):
    session_file = _get_session_file()
    browser = await playwright.chromium.launch(headless=headless, args=args)
    context = await browser.new_context(
        storage_state=str(session_file),
        viewport=viewport,
        ignore_https_errors=True,
    )
    page = await context.new_page()
    print("[SESSION] Browser loaded with saved session: {} ✓".format(session_file.name))
    logger.info("Browser loaded with saved session: %s", session_file.name)
    return browser, context, page


def is_redirected_to_sso(url: str) -> bool:
    return "microsoftonline.com" in url.lower()
