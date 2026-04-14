# # # # import time
# # # # from pathlib import Path
# # # # from playwright.async_api import async_playwright

# # # # SESSION_FILE    = Path("session.json")
# # # # SESSION_MAX_AGE = 8 * 60 * 60   # 8 hours


# # # # def session_exists() -> bool:
# # # #     if not SESSION_FILE.exists():
# # # #         print("[SESSION] No session file found")
# # # #         return False
# # # #     age_seconds = time.time() - SESSION_FILE.stat().st_mtime
# # # #     age_hours   = age_seconds / 3600
# # # #     if age_seconds > SESSION_MAX_AGE:
# # # #         print("[SESSION] Session expired ({:.1f}h old, max {}h) — will re-login".format(
# # # #             age_hours, SESSION_MAX_AGE // 3600))
# # # #         return False
# # # #     print("[SESSION] Valid session found ({:.1f}h old)".format(age_hours))
# # # #     return True


# # # # def delete_session():
# # # #     if SESSION_FILE.exists():
# # # #         SESSION_FILE.unlink()
# # # #         print("[SESSION] session.json deleted")


# # # # async def create_session(base_url: str, viewport: dict):
# # # #     """
# # # #     Fully automatic login — reads credentials from config/settings.py.
# # # #     No manual interaction, no Enter press needed.
# # # #     """
# # # #     # ── Pull credentials from config ────────────────────────
# # # #     from config.settings import LOGIN_EMAIL, LOGIN_PASSWORD

# # # #     if not LOGIN_EMAIL or not LOGIN_PASSWORD:
# # # #         raise ValueError(
# # # #             "[SESSION] LOGIN_EMAIL / LOGIN_PASSWORD not set in config/settings.py"
# # # #         )

# # # #     print("\n[SESSION] Auto-login starting for: {}".format(LOGIN_EMAIL))

# # # #     async with async_playwright() as p:
# # # #         browser = await p.chromium.launch(
# # # #             headless=False,
# # # #             args=["--disable-blink-features=AutomationControlled"],
# # # #         )
# # # #         context = await browser.new_context(
# # # #             viewport=viewport,
# # # #             ignore_https_errors=True,
# # # #         )
# # # #         page = await context.new_page()
# # # #         await page.goto(base_url, wait_until="domcontentloaded", timeout=30000)

# # # #         # ── Step 1: Email ────────────────────────────────────
# # # #         try:
# # # #             await page.wait_for_selector(
# # # #                 "#i0116, input[type='email']", timeout=10000
# # # #             )
# # # #             await page.fill("#i0116, input[type='email']", LOGIN_EMAIL)
# # # #             await page.click(
# # # #                 "#idSIButton9, input[type='submit'], button:has-text('Next')"
# # # #             )
# # # #             print("[SESSION] ✓ Email submitted")
# # # #             await page.wait_for_timeout(2000)
# # # #         except Exception as e:
# # # #             print("[SESSION] Email step error: {}".format(e))

# # # #         # ── Step 2: Password ─────────────────────────────────
# # # #         try:
# # # #             await page.wait_for_selector(
# # # #                 "#i0118, input[type='password']", timeout=10000
# # # #             )
# # # #             await page.fill("#i0118, input[type='password']", LOGIN_PASSWORD)
# # # #             await page.click(
# # # #                 "#idSIButton9, input[type='submit'], button:has-text('Sign in')"
# # # #             )
# # # #             print("[SESSION] ✓ Password submitted")
# # # #             await page.wait_for_timeout(2000)
# # # #         except Exception as e:
# # # #             print("[SESSION] Password step error: {}".format(e))

# # # #         # ── Step 3: "Stay signed in?" prompt (optional) ──────
# # # #         try:
# # # #             await page.wait_for_selector(
# # # #                 "#idSIButton9, button:has-text('Yes')", timeout=6000
# # # #             )
# # # #             await page.click("#idSIButton9, button:has-text('Yes')")
# # # #             print("[SESSION] ✓ Stay signed in clicked")
# # # #         except Exception:
# # # #             pass  # screen not always shown — safe to ignore

# # # #         # ── Step 4: Wait until app URL is reached ────────────
# # # #         app_host = base_url.replace("https://", "").replace("http://", "").rstrip("/")
# # # #         try:
# # # #             await page.wait_for_url(
# # # #                 lambda u: app_host in u,
# # # #                 timeout=20000
# # # #             )
# # # #             print("[SESSION] ✓ App loaded: {}".format(page.url))
# # # #         except Exception:
# # # #             await page.wait_for_timeout(5000)
# # # #             print("[SESSION] ⚠ URL wait timed out — saving anyway: {}".format(page.url))

# # # #         # ── Step 5: Save session — no Enter needed ────────────
# # # #         await context.storage_state(path=str(SESSION_FILE))
# # # #         print("[SESSION] ✓ session.json saved\n")
# # # #         await browser.close()


# # # # async def load_session(playwright, headless: bool, viewport: dict, args: list):
# # # #     browser = await playwright.chromium.launch(  channel="msedge",headless=headless, args=args)
# # # #     context = await browser.new_context(
# # # #         storage_state=str(SESSION_FILE),
# # # #         viewport=viewport,
# # # #         ignore_https_errors=True,
# # # #     )
# # # #     page = await context.new_page()
# # # #     print("[SESSION] Browser loaded with saved session ✓")
# # # #     return browser, context, page


# # # # def is_redirected_to_sso(url: str) -> bool:
# # # #     return "microsoftonline.com" in url.lower()

# # # """
# # # utils/session_manager.py
# # # ========================
# # # Persistent browser session manager using Playwright's storageState API.

# # # HOW IT WORKS:
# # # ─────────────
# # #   Run 1 → headless Chromium launches, performs SSO login,
# # #            saves cookies + localStorage to session.json

# # #   Run 2 → browser context is restored from session.json,
# # #            app opens already logged in  ✓

# # #   Run 3 → Microsoft silently refreshes tokens via cookie,
# # #            no login screen appears      ✓

# # #   Stale  → session.json is detected as expired/redirected-to-SSO,
# # #            file is deleted, next run triggers fresh login

# # # PUBLIC API (called from main.py and utils/login.py):
# # # ─────────────────────────────────────────────────────
# # #   session_exists()          → bool   — True if session.json is fresh
# # #   create_session(...)       → None   — headless login, saves session.json
# # #   load_session(...)         → (browser, context, page)
# # #   is_redirected_to_sso(url) → bool   — True if URL is Microsoft SSO
# # #   delete_session()          → None   — removes session.json
# # # """

# # # import os
# # # import json
# # # import asyncio
# # # from pathlib import Path
# # # from datetime import datetime, timedelta

# # # from playwright.async_api import async_playwright, Playwright

# # # # ── Config ────────────────────────────────────────────────────
# # # SESSION_FILE    = Path("session.json")        # stored in project root
# # # SESSION_MAX_AGE = timedelta(hours=8)          # re-login after 8 hours
# # # SSO_DOMAIN      = "microsoftonline.com"       # used for redirect detection

# # # # ── Credentials (imported lazily to avoid circular import) ───
# # # def _get_credentials():
# # #     from config.settings import LOGIN_EMAIL, LOGIN_PASSWORD, BASE_URL
# # #     return LOGIN_EMAIL, LOGIN_PASSWORD, BASE_URL


# # # # ============================================================
# # # # PUBLIC HELPERS
# # # # ============================================================

# # # def session_exists() -> bool:
# # #     """
# # #     Returns True if session.json exists AND was written within SESSION_MAX_AGE.
# # #     A missing file, empty file, or stale file all return False.
# # #     """
# # #     if not SESSION_FILE.exists():
# # #         return False
# # #     try:
# # #         stat = SESSION_FILE.stat()
# # #         if stat.st_size == 0:
# # #             return False
# # #         age = datetime.now() - datetime.fromtimestamp(stat.st_mtime)
# # #         if age > SESSION_MAX_AGE:
# # #             print("[SESSION] session.json is {:.0f} min old — will refresh".format(
# # #                 age.total_seconds() / 60))
# # #             return False
# # #         # Basic validity check: must be parseable JSON with a 'cookies' key
# # #         data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
# # #         if not data.get("cookies"):
# # #             return False
# # #         print("[SESSION] Valid session found ({:.0f} min old)".format(
# # #             age.total_seconds() / 60))
# # #         return True
# # #     except Exception as e:
# # #         print("[SESSION] Could not read session.json: {}".format(e))
# # #         return False


# # # def delete_session() -> None:
# # #     """Remove session.json so the next run triggers a fresh login."""
# # #     try:
# # #         if SESSION_FILE.exists():
# # #             SESSION_FILE.unlink()
# # #             print("[SESSION] session.json deleted")
# # #     except Exception as e:
# # #         print("[SESSION] Could not delete session.json: {}".format(e))


# # # def is_redirected_to_sso(url: str) -> bool:
# # #     """Returns True when the browser has been redirected to Microsoft SSO."""
# # #     return SSO_DOMAIN in url.lower()


# # # # ============================================================
# # # # CREATE SESSION  (headless auto-login)
# # # # ============================================================

# # # async def create_session(
# # #     base_url: str,
# # #     viewport: dict,
# # #     headless: bool = True,
# # #     timeout_ms: int = 60_000,
# # # ) -> None:
# # #     """
# # #     Launch a headless browser, perform full SSO login, then persist
# # #     cookies + localStorage to session.json.

# # #     Called automatically from main.py when session_exists() is False.
# # #     No manual steps required.

# # #     Args:
# # #         base_url   — app root URL (e.g. "https://app.example.com")
# # #         viewport   — {"width": ..., "height": ...}
# # #         headless   — True for background login (default)
# # #         timeout_ms — max ms to wait for each SSO step
# # #     """
# # #     email, password, _ = _get_credentials()

# # #     print("\n[SESSION] ═══════════════════════════════════════")
# # #     print("[SESSION]  Auto-login started")
# # #     print("[SESSION]  Email   : {}".format(email))
# # #     print("[SESSION]  URL     : {}".format(base_url))
# # #     print("[SESSION] ═══════════════════════════════════════\n")

# # #     async with async_playwright() as p:
# # #         browser = await p.chromium.launch(
# # #             headless=headless,
# # #             args=["--disable-blink-features=AutomationControlled"],
# # #         )
# # #         context = await browser.new_context(
# # #             viewport=viewport,
# # #             ignore_https_errors=True,
# # #         )
# # #         page = await context.new_page()

# # #         # ── Navigate to app (triggers SSO redirect) ───────────
# # #         print("[SESSION] Navigating to app...")
# # #         await page.goto(base_url, wait_until="domcontentloaded", timeout=30_000)
# # #         await page.wait_for_timeout(2000)

# # #         # ── Wait for SSO page ──────────────────────────────────
# # #         print("[SESSION] Waiting for SSO login page...")
# # #         try:
# # #             await page.wait_for_url("**microsoftonline.com**", timeout=15_000)
# # #         except Exception:
# # #             # May already be on SSO or the app skipped it
# # #             pass

# # #         current_url = page.url
# # #         print("[SESSION] Current URL: {}".format(current_url[:80]))

# # #         # ── If already on app (no SSO) → save immediately ────
# # #         if SSO_DOMAIN not in current_url:
# # #             print("[SESSION] App accessible without SSO — saving session")
# # #             await _save_storage_state(context)
# # #             await browser.close()
# # #             return

# # #         # ── Step 1: Email ─────────────────────────────────────
# # #         print("[SESSION] Filling email...")
# # #         try:
# # #             await page.wait_for_selector("input[type='email'], #i0116",
# # #                                          timeout=timeout_ms)
# # #             email_inp = page.locator("input[type='email'], #i0116").first
# # #             await email_inp.fill(email)
# # #             await page.wait_for_timeout(500)

# # #             # Click "Next"
# # #             next_btn = page.locator("input[type='submit'], button:has-text('Next')").first
# # #             await next_btn.click(timeout=5000)
# # #             print("[SESSION] Email submitted")
# # #             await page.wait_for_timeout(2000)
# # #         except Exception as e:
# # #             print("[SESSION] Email step error: {}".format(e))

# # #         # ── Step 2: Password ──────────────────────────────────
# # #         print("[SESSION] Filling password...")
# # #         try:
# # #             await page.wait_for_selector("input[type='password'], #i0118",
# # #                                          timeout=timeout_ms)
# # #             pw_inp = page.locator("input[type='password'], #i0118").first
# # #             await pw_inp.fill(password)
# # #             await page.wait_for_timeout(500)

# # #             # Click "Sign in"
# # #             signin_btn = page.locator(
# # #                 "input[type='submit'][value*='Sign' i], "
# # #                 "button:has-text('Sign in')"
# # #             ).first
# # #             await signin_btn.click(timeout=5000)
# # #             print("[SESSION] Password submitted")
# # #             await page.wait_for_timeout(3000)
# # #         except Exception as e:
# # #             print("[SESSION] Password step error: {}".format(e))

# # #         # ── Step 3: "Stay signed in?" (KMSI) ─────────────────
# # #         print("[SESSION] Checking for 'Stay signed in' prompt...")
# # #         try:
# # #             yes_sel = (
# # #                 "input[type='submit'][value='Yes' i], "
# # #                 "button:has-text('Yes'), "
# # #                 "button:has-text('Stay signed in')"
# # #             )
# # #             # Wait up to 6 s — this prompt is optional
# # #             await page.wait_for_selector(yes_sel, timeout=6000)
# # #             yes_btn = page.locator(yes_sel).first
# # #             await yes_btn.click(timeout=5000)
# # #             print("[SESSION] Clicked 'Stay signed in'")
# # #             await page.wait_for_timeout(3000)
# # #         except Exception:
# # #             print("[SESSION] No 'Stay signed in' prompt — continuing")

# # #         # ── Wait for app to fully load ────────────────────────
# # #         print("[SESSION] Waiting for app redirect...")
# # #         try:
# # #             await page.wait_for_function(
# # #                 "() => !window.location.href.includes('microsoftonline.com')",
# # #                 timeout=30_000,
# # #             )
# # #         except Exception:
# # #             pass

# # #         final_url = page.url
# # #         print("[SESSION] Final URL: {}".format(final_url[:80]))

# # #         if SSO_DOMAIN in final_url:
# # #             print("[SESSION] ✗ Still on SSO — check credentials in config/settings.py")
# # #             await browser.close()
# # #             raise RuntimeError(
# # #                 "SSO login failed. Verify LOGIN_EMAIL / LOGIN_PASSWORD in config/settings.py"
# # #             )

# # #         # ── Save session ──────────────────────────────────────
# # #         await _save_storage_state(context)
# # #         await browser.close()
# # #         print("[SESSION] ✓ Login successful — session.json saved\n")


# # # async def _save_storage_state(context) -> None:
# # #     """Persist the browser context (cookies + localStorage) to session.json."""
# # #     try:
# # #         await context.storage_state(path=str(SESSION_FILE))
# # #         size = SESSION_FILE.stat().st_size
# # #         print("[SESSION] session.json written ({} bytes)".format(size))
# # #     except Exception as e:
# # #         print("[SESSION] Could not save session.json: {}".format(e))
# # #         raise


# # # # ============================================================
# # # # LOAD SESSION  (restore persistent context)
# # # # ============================================================

# # # async def load_session(
# # #     playwright: Playwright,
# # #     headless: bool,
# # #     viewport: dict,
# # #     args: list = None,
# # # ):
# # #     """
# # #     Launch a browser context pre-loaded with the saved session.

# # #     Returns:
# # #         (browser, context, page)  — ready to use, already authenticated
# # #     """
# # #     if not SESSION_FILE.exists():
# # #         raise FileNotFoundError(
# # #             "session.json not found. Call create_session() first."
# # #         )

# # #     print("[SESSION] Loading session from session.json...")

# # #     browser = await playwright.chromium.launch(
# # #         headless=headless,
# # #         args=args or ["--disable-blink-features=AutomationControlled"],
# # #     )
# # #     context = await browser.new_context(
# # #         viewport=viewport,
# # #         storage_state=str(SESSION_FILE),   # ← injects cookies + localStorage
# # #         ignore_https_errors=True,
# # #     )
# # #     page = await context.new_page()
# # #     print("[SESSION] Context restored ✓")
# # #     return browser, context, page


# # # # ============================================================
# # # # SAVE SESSION  (call after any action that refreshes tokens)
# # # # ============================================================

# # # async def save_session(context) -> None:
# # #     """
# # #     Optionally call this after a successful run to refresh session.json
# # #     with the latest cookies (extends effective session lifetime).

# # #     Usage in main.py (optional):
# # #         await save_session(context)
# # #     """
# # #     await _save_storage_state(context)
# # #     print("[SESSION] Session refreshed ✓")

# # """
# # utils/session_manager.py
# # ========================
# # Persistent Browser Context — credentials browser profile mein save hoti hain.
# # session.json ki zaroorat NAHI.

# # HOW IT WORKS:
# # ─────────────
# #   Run 1 → browser_profile/ folder create hota hai (real Chrome profile)
# #            SSO login hota hai → credentials profile mein save
# #            Browser band hone par bhi profile disk pe rehta hai

# #   Run 2 → same profile load → already logged in ✓
# #            No session.json, no cookie injection

# #   Run 3 → Microsoft silently refresh karta hai via profile cookies ✓

# # PUBLIC API (same as before — main.py mein koi change nahi):
# # ─────────────────────────────────────────────────────────────
# #   session_exists()          → bool
# #   create_session(...)       → None
# #   load_session(...)         → (browser, context, page)
# #   is_redirected_to_sso(url) → bool
# #   delete_session()          → None
# # """

# # # import shutil
# # # from pathlib import Path

# # # # ── Browser profile folder (project root ke andar) ───────────
# # # PROFILE_DIR = Path("browser_profile")   # real browser profile yahan save hota hai
# # # SSO_DOMAIN  = "microsoftonline.com"


# # # def _get_credentials():
# # #     from config.settings import LOGIN_EMAIL, LOGIN_PASSWORD, BASE_URL
# # #     return LOGIN_EMAIL, LOGIN_PASSWORD, BASE_URL


# # # # ============================================================
# # # # PUBLIC HELPERS
# # # # ============================================================

# # # def session_exists() -> bool:
# # #     """
# # #     Returns True if browser_profile/ folder exist karta hai aur usme data hai.
# # #     session.json check NAHI — real browser profile folder check hota hai.
# # #     """
# # #     if not PROFILE_DIR.exists():
# # #         print("[SESSION] No browser profile found — first run, login required")
# # #         return False

# # #     contents = list(PROFILE_DIR.iterdir())
# # #     if not contents:
# # #         print("[SESSION] Browser profile empty — will re-login")
# # #         return False

# # #     print("[SESSION] Browser profile found ✓ — login will be skipped")
# # #     return True


# # # def delete_session() -> None:
# # #     """
# # #     Poora browser_profile/ folder delete karo.
# # #     Next run mein fresh login hoga.
# # #     """
# # #     try:
# # #         if PROFILE_DIR.exists():
# # #             shutil.rmtree(PROFILE_DIR)
# # #             print("[SESSION] browser_profile/ deleted — next run will re-login")
# # #     except Exception as e:
# # #         print("[SESSION] Could not delete browser_profile/: {}".format(e))


# # # def is_redirected_to_sso(url: str) -> bool:
# # #     """Returns True when browser Microsoft SSO pe redirect ho gaya."""
# # #     return SSO_DOMAIN in url.lower()


# # # # ============================================================
# # # # CREATE SESSION — Pehli baar login, profile disk pe save
# # # # ============================================================

# # # async def create_session(
# # #     base_url: str,
# # #     viewport: dict,
# # #     headless: bool = True,
# # #     timeout_ms: int = 60_000,
# # # ) -> None:
# # #     """
# # #     Sirf pehli baar chalega.
# # #     SSO login karke browser_profile/ mein save karega.
# # #     Agli baar se yeh function call hi nahi hoga.
# # #     """
# # #     from playwright.async_api import async_playwright

# # #     email, password, _ = _get_credentials()

# # #     print("\n[SESSION] ═══════════════════════════════════════")
# # #     print("[SESSION]  First-time login — saving browser profile")
# # #     print("[SESSION]  Email   : {}".format(email))
# # #     print("[SESSION]  URL     : {}".format(base_url))
# # #     print("[SESSION]  Profile : {}".format(PROFILE_DIR.resolve()))
# # #     print("[SESSION] ═══════════════════════════════════════\n")

# # #     # Purana stale profile delete karo
# # #     if PROFILE_DIR.exists():
# # #         shutil.rmtree(PROFILE_DIR)
# # #     PROFILE_DIR.mkdir(parents=True, exist_ok=True)

# # #     async with async_playwright() as p:

# # #         # ── KEY LINE ─────────────────────────────────────────
# # #         # Normal launch() nahi — launch_persistent_context() use hota hai.
# # #         # Ye ek real Chrome user profile folder banata hai.
# # #         # Jab context.close() hota hai, browser khud sab disk pe likh deta hai.
# # #         # Koi manual save call nahi chahiye.
# # #         context = await p.chromium.launch_persistent_context(
# # #             str(PROFILE_DIR),
# # #             headless=headless,
# # #             viewport=viewport,
# # #             ignore_https_errors=True,
# # #             args=["--disable-blink-features=AutomationControlled"],
# # #         )

# # #         page = context.pages[0] if context.pages else await context.new_page()

# # #         # ── App pe jaao ───────────────────────────────────────
# # #         print("[SESSION] Navigating to app...")
# # #         await page.goto(base_url, wait_until="domcontentloaded", timeout=30_000)
# # #         await page.wait_for_timeout(2000)

# # #         current_url = page.url
# # #         print("[SESSION] URL: {}".format(current_url[:80]))

# # #         # SSO nahi aaya — directly app khul gaya
# # #         if SSO_DOMAIN not in current_url:
# # #             print("[SESSION] App opened without SSO — profile saved ✓")
# # #             await context.close()
# # #             return

# # #         # ── Step 1: Email ─────────────────────────────────────
# # #         print("[SESSION] Step 1 — Email...")
# # #         try:
# # #             await page.wait_for_selector(
# # #                 "input[type='email'], #i0116", timeout=timeout_ms)
# # #             await page.locator(
# # #                 "input[type='email'], #i0116").first.fill(email)
# # #             await page.wait_for_timeout(500)
# # #             await page.locator(
# # #                 "input[type='submit'], button:has-text('Next')").first.click(timeout=5000)
# # #             print("[SESSION] Email submitted ✓")
# # #             await page.wait_for_timeout(2000)
# # #         except Exception as e:
# # #             print("[SESSION] Email error: {}".format(e))

# # #         # ── Step 2: Password ──────────────────────────────────
# # #         print("[SESSION] Step 2 — Password...")
# # #         try:
# # #             await page.wait_for_selector(
# # #                 "input[type='password'], #i0118", timeout=timeout_ms)
# # #             await page.locator(
# # #                 "input[type='password'], #i0118").first.fill(password)
# # #             await page.wait_for_timeout(500)
# # #             await page.locator(
# # #                 "input[type='submit'][value*='Sign' i], "
# # #                 "button:has-text('Sign in')"
# # #             ).first.click(timeout=5000)
# # #             print("[SESSION] Password submitted ✓")
# # #             await page.wait_for_timeout(3000)
# # #         except Exception as e:
# # #             print("[SESSION] Password error: {}".format(e))

# # #         # ── Step 3: "Stay signed in?" — SABSE IMPORTANT ───────
# # #         # "Yes" click → Microsoft ek ESTSAUTHPERSISTENT cookie set karta hai
# # #         # Ye cookie browser profile mein save hoti hai
# # #         # Isi se agli baar bina login ke app khulta hai
# # #         print("[SESSION] Step 3 — Stay signed in...")
# # #         try:
# # #             yes_sel = (
# # #                 "input[type='submit'][value='Yes' i], "
# # #                 "button:has-text('Yes'), "
# # #                 "button:has-text('Stay signed in')"
# # #             )
# # #             await page.wait_for_selector(yes_sel, timeout=6000)
# # #             await page.locator(yes_sel).first.click(timeout=5000)
# # #             print("[SESSION] 'Stay signed in' clicked ✓  ← long-lived cookie saved")
# # #             await page.wait_for_timeout(3000)
# # #         except Exception:
# # #             print("[SESSION] No 'Stay signed in' prompt — continuing")

# # #         # ── App load hone ka wait ─────────────────────────────
# # #         print("[SESSION] Waiting for app redirect...")
# # #         try:
# # #             await page.wait_for_function(
# # #                 "() => !window.location.href.includes('microsoftonline.com')",
# # #                 timeout=30_000,
# # #             )
# # #         except Exception:
# # #             pass

# # #         final_url = page.url
# # #         print("[SESSION] Final URL: {}".format(final_url[:80]))

# # #         if SSO_DOMAIN in final_url:
# # #             await context.close()
# # #             shutil.rmtree(PROFILE_DIR, ignore_errors=True)
# # #             raise RuntimeError(
# # #                 "SSO login failed.\n"
# # #                 "Check LOGIN_EMAIL / LOGIN_PASSWORD in config/settings.py"
# # #             )

# # #         # ── context.close() = automatic profile save ─────────
# # #         # Ye line browser profile ko disk pe flush kar deti hai.
# # #         # Koi extra call nahi chahiye.
# # #         await context.close()
# # #         print("[SESSION] ✓ Profile saved to browser_profile/")
# # #         print("[SESSION] ✓ Next run will skip login entirely\n")


# # # # ============================================================
# # # # LOAD SESSION — Saved profile se browser launch karo
# # # # ============================================================

# # # async def load_session(
# # #     playwright,
# # #     headless: bool,
# # #     viewport: dict,
# # #     args: list = None,
# # # ):
# # #     """
# # #     Saved browser_profile/ se persistent context restore karo.
# # #     Cookies already browser mein hain — no injection needed.

# # #     Returns:
# # #         (None, context, page)
# # #         NOTE: browser=None — persistent context mein alag browser object nahi hota.
# # #               main.py mein browser.close() ki jagah context.close() hoga.
# # #     """
# # #     if not PROFILE_DIR.exists():
# # #         raise FileNotFoundError(
# # #             "browser_profile/ not found. Call create_session() first."
# # #         )

# # #     print("[SESSION] Loading browser profile from disk...")

# # #     context = await playwright.chromium.launch_persistent_context(
# # #         str(PROFILE_DIR),
# # #         headless=headless,
# # #         viewport=viewport,
# # #         ignore_https_errors=True,
# # #         args=args or ["--disable-blink-features=AutomationControlled"],
# # #     )

# # #     page = context.pages[0] if context.pages else await context.new_page()
# # #     print("[SESSION] Profile loaded ✓ — already logged in")

# # #     # browser=None — main.py mein context.close() use karna hoga
# # #     return None, context, page

# # """
# # utils/session_manager.py
# # ========================
# # Persistent Browser Context — credentials browser profile mein save hoti hain.
# # session.json ki zaroorat NAHI.

# # HOW IT WORKS:
# # ─────────────
# #   Run 1 → browser_profile/ folder create hota hai (real Chrome profile)
# #            SSO login hota hai → credentials profile mein save
# #            Browser band hone par bhi profile disk pe rehta hai

# #   Run 2 → same profile load → already logged in ✓
# #            No session.json, no cookie injection

# #   Run 3 → Microsoft silently refresh karta hai via profile cookies ✓

# # PUBLIC API (same as before — main.py mein koi change nahi):
# # ─────────────────────────────────────────────────────────────
# #   session_exists()          → bool
# #   create_session(...)       → None
# #   load_session(...)         → (browser, context, page)
# #   is_redirected_to_sso(url) → bool
# #   delete_session()          → None
# # """

# # import shutil
# # from pathlib import Path

# # # ── Browser profile folder (project root ke andar) ───────────
# # PROFILE_DIR = Path("browser_profile")   # real browser profile yahan save hota hai
# # SSO_DOMAIN  = "microsoftonline.com"


# # def _get_credentials():
# #     from config.settings import LOGIN_EMAIL, LOGIN_PASSWORD, BASE_URL
# #     return LOGIN_EMAIL, LOGIN_PASSWORD, BASE_URL


# # # ============================================================
# # # PUBLIC HELPERS
# # # ============================================================

# # def session_exists() -> bool:
# #     """
# #     Returns True if browser_profile/ folder exist karta hai aur usme data hai.
# #     session.json check NAHI — real browser profile folder check hota hai.
# #     """
# #     if not PROFILE_DIR.exists():
# #         print("[SESSION] No browser profile found — first run, login required")
# #         return False

# #     contents = list(PROFILE_DIR.iterdir())
# #     if not contents:
# #         print("[SESSION] Browser profile empty — will re-login")
# #         return False

# #     print("[SESSION] Browser profile found ✓ — login will be skipped")
# #     return True


# # def delete_session() -> None:
# #     """
# #     Poora browser_profile/ folder delete karo.
# #     Next run mein fresh login hoga.
# #     """
# #     try:
# #         if PROFILE_DIR.exists():
# #             shutil.rmtree(PROFILE_DIR)
# #             print("[SESSION] browser_profile/ deleted — next run will re-login")
# #     except Exception as e:
# #         print("[SESSION] Could not delete browser_profile/: {}".format(e))


# # def is_redirected_to_sso(url: str) -> bool:
# #     """Returns True when browser Microsoft SSO pe redirect ho gaya."""
# #     return SSO_DOMAIN in url.lower()


# # # ============================================================
# # # CREATE SESSION — Pehli baar login, profile disk pe save
# # # ============================================================

# # async def create_session(
# #     base_url: str,
# #     viewport: dict,
# #     headless: bool = True,
# #     timeout_ms: int = 60_000,
# # ) -> None:
# #     """
# #     Sirf pehli baar chalega.
# #     SSO login karke browser_profile/ mein save karega.
# #     Agli baar se yeh function call hi nahi hoga.
# #     """
# #     from playwright.async_api import async_playwright

# #     email, password, _ = _get_credentials()

# #     print("\n[SESSION] ═══════════════════════════════════════")
# #     print("[SESSION]  First-time login — saving browser profile")
# #     print("[SESSION]  Email   : {}".format(email))
# #     print("[SESSION]  URL     : {}".format(base_url))
# #     print("[SESSION]  Profile : {}".format(PROFILE_DIR.resolve()))
# #     print("[SESSION] ═══════════════════════════════════════\n")

# #     # Purana stale profile delete karo
# #     if PROFILE_DIR.exists():
# #         shutil.rmtree(PROFILE_DIR)
# #     PROFILE_DIR.mkdir(parents=True, exist_ok=True)

# #     async with async_playwright() as p:

# #         # ── KEY LINE ─────────────────────────────────────────
# #         # Normal launch() nahi — launch_persistent_context() use hota hai.
# #         # Ye ek real Chrome user profile folder banata hai.
# #         # Jab context.close() hota hai, browser khud sab disk pe likh deta hai.
# #         # Koi manual save call nahi chahiye.
# #         context = await p.chromium.launch_persistent_context(
# #             str(PROFILE_DIR),
# #             headless=headless,
# #             viewport=viewport,
# #             ignore_https_errors=True,
# #             args=["--disable-blink-features=AutomationControlled"],
# #         )

# #         page = context.pages[0] if context.pages else await context.new_page()

# #         # ── App pe jaao ───────────────────────────────────────
# #         print("[SESSION] Navigating to app...")
# #         await page.goto(base_url, wait_until="domcontentloaded", timeout=30_000)
# #         await page.wait_for_timeout(2000)

# #         current_url = page.url
# #         print("[SESSION] URL: {}".format(current_url[:80]))

# #         # SSO nahi aaya — directly app khul gaya
# #         if SSO_DOMAIN not in current_url:
# #             print("[SESSION] App opened without SSO — profile saved ✓")
# #             await context.close()
# #             return

# #         # ── Step 1: Email ─────────────────────────────────────
# #         print("[SESSION] Step 1 — Email...")
# #         try:
# #             await page.wait_for_selector(
# #                 "input[type='email'], #i0116", timeout=timeout_ms)
# #             await page.locator(
# #                 "input[type='email'], #i0116").first.fill(email)
# #             await page.wait_for_timeout(500)
# #             await page.locator(
# #                 "input[type='submit'], button:has-text('Next')").first.click(timeout=5000)
# #             print("[SESSION] Email submitted ✓")
# #             await page.wait_for_timeout(2000)
# #         except Exception as e:
# #             print("[SESSION] Email error: {}".format(e))

# #         # ── Step 2: Password ──────────────────────────────────
# #         print("[SESSION] Step 2 — Password...")
# #         try:
# #             await page.wait_for_selector(
# #                 "input[type='password'], #i0118", timeout=timeout_ms)
# #             await page.locator(
# #                 "input[type='password'], #i0118").first.fill(password)
# #             await page.wait_for_timeout(500)
# #             await page.locator(
# #                 "input[type='submit'][value*='Sign' i], "
# #                 "button:has-text('Sign in')"
# #             ).first.click(timeout=5000)
# #             print("[SESSION] Password submitted ✓")
# #             await page.wait_for_timeout(3000)
# #         except Exception as e:
# #             print("[SESSION] Password error: {}".format(e))

# #         # ── Step 3: "Stay signed in?" — SABSE IMPORTANT ───────
# #         # "Yes" click → Microsoft ek ESTSAUTHPERSISTENT cookie set karta hai
# #         # Ye cookie browser profile mein save hoti hai
# #         # Isi se agli baar bina login ke app khulta hai
# #         print("[SESSION] Step 3 — Stay signed in...")
# #         try:
# #             yes_sel = (
# #                 "input[type='submit'][value='Yes' i], "
# #                 "button:has-text('Yes'), "
# #                 "button:has-text('Stay signed in')"
# #             )
# #             await page.wait_for_selector(yes_sel, timeout=6000)
# #             await page.locator(yes_sel).first.click(timeout=5000)
# #             print("[SESSION] 'Stay signed in' clicked ✓  ← long-lived cookie saved")
# #             await page.wait_for_timeout(3000)
# #         except Exception:
# #             print("[SESSION] No 'Stay signed in' prompt — continuing")

# #         # ── App load hone ka wait ─────────────────────────────
# #         print("[SESSION] Waiting for app redirect...")
# #         try:
# #             await page.wait_for_function(
# #                 "() => !window.location.href.includes('microsoftonline.com')",
# #                 timeout=30_000,
# #             )
# #         except Exception:
# #             pass

# #         final_url = page.url
# #         print("[SESSION] Final URL: {}".format(final_url[:80]))

# #         if SSO_DOMAIN in final_url:
# #             await context.close()
# #             shutil.rmtree(PROFILE_DIR, ignore_errors=True)
# #             raise RuntimeError(
# #                 "SSO login failed.\n"
# #                 "Check LOGIN_EMAIL / LOGIN_PASSWORD in config/settings.py"
# #             )

# #         # ── context.close() = automatic profile save ─────────
# #         # Ye line browser profile ko disk pe flush kar deti hai.
# #         # Koi extra call nahi chahiye.
# #         await context.close()
# #         print("[SESSION] ✓ Profile saved to browser_profile/")
# #         print("[SESSION] ✓ Next run will skip login entirely\n")


# # # ============================================================
# # # LOAD SESSION — Saved profile se browser launch karo
# # # ============================================================

# # async def load_session(
# #     playwright,
# #     headless: bool,
# #     viewport: dict,
# #     args: list = None,
# # ):
# #     """
# #     Saved browser_profile/ se persistent context restore karo.
# #     Cookies already browser mein hain — no injection needed.

# #     Returns:
# #         (None, context, page)
# #         NOTE: browser=None — persistent context mein alag browser object nahi hota.
# #               main.py mein browser.close() ki jagah context.close() hoga.
# #     """
# #     if not PROFILE_DIR.exists():
# #         raise FileNotFoundError(
# #             "browser_profile/ not found. Call create_session() first."
# #         )

# #     print("[SESSION] Loading browser profile from disk...")

# #     context = await playwright.chromium.launch_persistent_context(
# #         str(PROFILE_DIR),
# #         headless=headless,
# #         viewport=viewport,
# #         ignore_https_errors=True,
# #         args=args or ["--disable-blink-features=AutomationControlled"],
# #     )

# #     page = context.pages[0] if context.pages else await context.new_page()
# #     print("[SESSION] Profile loaded ✓ — already logged in")

# #     # browser=None — main.py mein context.close() use karna hoga
# #     return None, context, page
# import shutil
# import time
# from pathlib import Path

# PROFILE_DIR = Path("browser_profile")
# SSO_DOMAIN = "microsoftonline.com"


# def _get_credentials():
#     from config.settings import LOGIN_EMAIL, LOGIN_PASSWORD, BASE_URL
#     return LOGIN_EMAIL, LOGIN_PASSWORD, BASE_URL


# # ============================================================
# # HELPERS
# # ============================================================

# def session_exists() -> bool:
#     if not PROFILE_DIR.exists():
#         print("[SESSION] No browser profile found — login required")
#         return False

#     if not any(PROFILE_DIR.iterdir()):
#         print("[SESSION] Browser profile empty — login required")
#         return False

#     print("[SESSION] Browser profile found ✓ — login will be skipped")
#     return True


# def delete_session():
#     try:
#         if PROFILE_DIR.exists():
#             time.sleep(1)
#             shutil.rmtree(PROFILE_DIR, ignore_errors=True)
#             print("[SESSION] browser_profile deleted ✓")
#     except Exception as e:
#         print("[SESSION] Delete error:", e)


# def is_redirected_to_sso(url: str) -> bool:
#     return SSO_DOMAIN in url.lower()


# # ============================================================
# # CREATE SESSION
# # ============================================================

# async def create_session(base_url, viewport, headless=True):
#     from playwright.async_api import async_playwright

#     email, password, _ = _get_credentials()

#     print("\n[SESSION] Creating new session...\n")

#     if PROFILE_DIR.exists():
#         shutil.rmtree(PROFILE_DIR, ignore_errors=True)

#     PROFILE_DIR.mkdir(parents=True, exist_ok=True)

#     async with async_playwright() as p:
#         context = await p.chromium.launch_persistent_context(
#             str(PROFILE_DIR),
#             headless=headless,
#             viewport=viewport,
#             ignore_https_errors=True,
#         )

#         page = context.pages[0] if context.pages else await context.new_page()

#         await page.goto(base_url)
#         await page.wait_for_timeout(3000)

#         # Force SSO if needed
#         if not is_redirected_to_sso(page.url):
#             await page.goto(base_url + "/projects")
#             await page.wait_for_timeout(3000)

#         if is_redirected_to_sso(page.url):

#             # EMAIL
#             await page.wait_for_selector("input[type='email'], #i0116", timeout=10000)
#             await page.fill("input[type='email'], #i0116", email)
#             await page.click("input[type='submit'], button:has-text('Next')")
#             await page.wait_for_timeout(2000)

#             # PASSWORD
#             await page.wait_for_selector("input[type='password'], #i0118", timeout=10000)
#             await page.fill("input[type='password'], #i0118", password)
#             await page.click("input[type='submit'], button:has-text('Sign in')")
#             await page.wait_for_timeout(3000)

#             try:
#                 await page.click("button:has-text('Yes')")
#             except:
#                 pass

#             await page.wait_for_timeout(5000)

#         if is_redirected_to_sso(page.url):
#             await context.close()
#             raise Exception("SSO login failed")

#         await context.close()
#         print("[SESSION] Session created ✓\n")


# # ============================================================
# # LOAD SESSION  ✅ (THIS WAS MISSING / BROKEN)
# # ============================================================

# async def load_session(playwright, headless, viewport):
#     if not PROFILE_DIR.exists():
#         raise Exception("No session found. Run create_session first.")

#     context = await playwright.chromium.launch_persistent_context(
#         str(PROFILE_DIR),
#         headless=headless,
#         viewport=viewport,
#         ignore_https_errors=True,
#     )

#     page = context.pages[0] if context.pages else await context.new_page()

#     print("[SESSION] Session loaded ✓")
#     return None, context, page

import shutil
import time
from pathlib import Path

PROFILE_DIR = Path("browser_profile")
SSO_DOMAIN = "microsoftonline.com"


def _get_credentials():
    from config.settings import LOGIN_EMAIL, LOGIN_PASSWORD, BASE_URL
    return LOGIN_EMAIL, LOGIN_PASSWORD, BASE_URL


# ============================================================
# HELPERS
# ============================================================

def session_exists() -> bool:
    if not PROFILE_DIR.exists():
        print("[SESSION] No browser profile found — login required")
        return False

    if not any(PROFILE_DIR.iterdir()):
        print("[SESSION] Browser profile empty — login required")
        return False

    print("[SESSION] Browser profile found ✓ — login will be skipped")
    return True


def delete_session():
    try:
        if PROFILE_DIR.exists():
            time.sleep(1)
            shutil.rmtree(PROFILE_DIR, ignore_errors=True)
            print("[SESSION] browser_profile deleted ✓")
    except Exception as e:
        print("[SESSION] Delete error:", e)


def is_redirected_to_sso(url: str) -> bool:
    return SSO_DOMAIN in url.lower()


# ============================================================
# CREATE SESSION (FINAL FIXED)
# ============================================================

async def create_session(base_url, viewport, headless=True):
    from playwright.async_api import async_playwright

    email, password, _ = _get_credentials()

    print("\n[SESSION] Creating new session...\n")

    # 🔥 Always clean
    if PROFILE_DIR.exists():
        shutil.rmtree(PROFILE_DIR, ignore_errors=True)

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=headless,
            viewport=viewport,
            ignore_https_errors=True,
        )

        page = context.pages[0] if context.pages else await context.new_page()

        # Step 1: Open app
        await page.goto(base_url)
        await page.wait_for_timeout(3000)

        # Step 2: Force SSO if not triggered
        if not is_redirected_to_sso(page.url):
            print("[SESSION] No SSO → forcing protected route")
            try:
                await page.goto(base_url + "/projects")
                await page.wait_for_timeout(3000)
            except:
                pass

        # Step 3: Perform login
        if is_redirected_to_sso(page.url):
            print("[SESSION] SSO detected → logging in")

            # EMAIL
            await page.wait_for_selector("input[type='email']", timeout=10000)
            await page.locator("input[type='email']").first.fill(email)
            await page.locator("input[type='submit'], button:has-text('Next')").first.click()
            await page.wait_for_timeout(2000)

            # PASSWORD
            await page.wait_for_selector("input[type='password']", timeout=10000)
            await page.locator("input[type='password']").first.fill(password)
            await page.locator("input[type='submit'], button:has-text('Sign in')").first.click()
            await page.wait_for_timeout(3000)

            # ============================
            # 🔥 STAY SIGNED IN FIX
            # ============================
            print("[SESSION] Handling 'Stay signed in'...")

            try:
                await page.wait_for_timeout(2000)

                yes_selectors = [
                    "#idSIButton9",  # ⭐ MOST RELIABLE
                    "input[value='Yes']",
                    "button:has-text('Yes')",
                ]

                clicked = False

                for sel in yes_selectors:
                    try:
                        locator = page.locator(sel)
                        if await locator.count() > 0:
                            await locator.first.click(timeout=3000)
                            print(f"[SESSION] Clicked Stay signed in using: {sel}")
                            clicked = True
                            break
                    except:
                        continue

                if not clicked:
                    print("[SESSION] 'Stay signed in' not found — continuing")

            except Exception as e:
                print("[SESSION] Stay signed in error:", e)

            await page.wait_for_timeout(4000)

        # Step 4: Wait for final redirect
        print("[SESSION] Waiting for final redirect...")

        try:
            await page.wait_for_function(
                "() => !window.location.href.includes('microsoftonline.com')",
                timeout=30000
            )
        except:
            pass

        await page.wait_for_timeout(3000)

        final_url = page.url
        print("[SESSION] Final URL:", final_url)

        if is_redirected_to_sso(final_url):
            await context.close()
            raise Exception("SSO login failed — still on Microsoft page")

        await context.close()
        print("[SESSION] Session created successfully ✓\n")


# ============================================================
# LOAD SESSION
# ============================================================

async def load_session(playwright, headless, viewport):
    if not PROFILE_DIR.exists():
        raise Exception("No session found. Run create_session first.")

    context = await playwright.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        headless=headless,
        viewport=viewport,
        ignore_https_errors=True,
    )

    page = context.pages[0] if context.pages else await context.new_page()

    print("[SESSION] Session loaded ✓")
    return None, context, page