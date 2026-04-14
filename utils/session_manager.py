import time
from pathlib import Path
from playwright.async_api import async_playwright

SESSION_FILE    = Path("session.json")
SESSION_MAX_AGE = 8 * 60 * 60   # 8 hours


def session_exists() -> bool:
    if not SESSION_FILE.exists():
        print("[SESSION] No session file found")
        return False
    age_seconds = time.time() - SESSION_FILE.stat().st_mtime
    age_hours   = age_seconds / 3600
    if age_seconds > SESSION_MAX_AGE:
        print("[SESSION] Session expired ({:.1f}h old, max {}h) — will re-login".format(
            age_hours, SESSION_MAX_AGE // 3600))
        return False
    print("[SESSION] Valid session found ({:.1f}h old)".format(age_hours))
    return True


def delete_session():
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
        print("[SESSION] session.json deleted")


async def create_session(base_url: str, viewport: dict):
    """
    Fully automatic login — reads credentials from config/settings.py.
    No manual interaction, no Enter press needed.
    """
    # ── Pull credentials from config ────────────────────────
    from config.settings import LOGIN_EMAIL, LOGIN_PASSWORD

    if not LOGIN_EMAIL or not LOGIN_PASSWORD:
        raise ValueError(
            "[SESSION] LOGIN_EMAIL / LOGIN_PASSWORD not set in config/settings.py"
        )

    print("\n[SESSION] Auto-login starting for: {}".format(LOGIN_EMAIL))

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport=viewport,
            ignore_https_errors=True,
        )
        page = await context.new_page()
        await page.goto(base_url, wait_until="domcontentloaded", timeout=30000)

        # ── Step 1: Email ────────────────────────────────────
        try:
            await page.wait_for_selector(
                "#i0116, input[type='email']", timeout=10000
            )
            await page.fill("#i0116, input[type='email']", LOGIN_EMAIL)
            await page.click(
                "#idSIButton9, input[type='submit'], button:has-text('Next')"
            )
            print("[SESSION] ✓ Email submitted")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print("[SESSION] Email step error: {}".format(e))

        # ── Step 2: Password ─────────────────────────────────
        try:
            await page.wait_for_selector(
                "#i0118, input[type='password']", timeout=10000
            )
            await page.fill("#i0118, input[type='password']", LOGIN_PASSWORD)
            await page.click(
                "#idSIButton9, input[type='submit'], button:has-text('Sign in')"
            )
            print("[SESSION] ✓ Password submitted")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print("[SESSION] Password step error: {}".format(e))

        # ── Step 3: "Stay signed in?" prompt (optional) ──────
        try:
            await page.wait_for_selector(
                "#idSIButton9, button:has-text('Yes')", timeout=6000
            )
            await page.click("#idSIButton9, button:has-text('Yes')")
            print("[SESSION] ✓ Stay signed in clicked")
        except Exception:
            pass  # screen not always shown — safe to ignore

        # ── Step 4: Wait until app URL is reached ────────────
        app_host = base_url.replace("https://", "").replace("http://", "").rstrip("/")
        try:
            await page.wait_for_url(
                lambda u: app_host in u,
                timeout=20000
            )
            print("[SESSION] ✓ App loaded: {}".format(page.url))
        except Exception:
            await page.wait_for_timeout(5000)
            print("[SESSION] ⚠ URL wait timed out — saving anyway: {}".format(page.url))

        # ── Step 5: Save session — no Enter needed ────────────
        await context.storage_state(path=str(SESSION_FILE))
        print("[SESSION] ✓ session.json saved\n")
        await browser.close()


async def load_session(playwright, headless: bool, viewport: dict, args: list):
    browser = await playwright.chromium.launch(headless=headless, args=args)
    context = await browser.new_context(
        storage_state=str(SESSION_FILE),
        viewport=viewport,
        ignore_https_errors=True,
    )
    page = await context.new_page()
    print("[SESSION] Browser loaded with saved session ✓")
    return browser, context, page


def is_redirected_to_sso(url: str) -> bool:
    return "microsoftonline.com" in url.lower()