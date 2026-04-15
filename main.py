
import asyncio
import logging
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

from config.settings import (
    BASE_URL, LOGIN_EMAIL, LOGIN_PASSWORD,
    MAX_STEPS, DOM_SETTLE_MS, SSO_SETTLE_MS, POST_RUN_S,
    VIEWPORT, HEADLESS,
)
from dom.dom_builder    import extract_live_dom
from executor.executor  import execute_step
from report.test_report import TestReporter
from modules            import MODULES, MODULE_KEYS

from utils.session_manager import (
    session_exists,
    create_session,
    load_session,
    is_redirected_to_sso,
    delete_session,
    get_session_file,
)

# ============================================================
# main.py — Entry point.
#
# LOGIN FLOW:
#   1. Email/password are read from config/settings.py — no prompts.
#   2. If no session file → auto-login via create_session().
#   3. If session file exists → browser loads with session, access/refresh token checked.
#   4. Session expires mid-run → refresh token tried first; deleted only if both expired.
# ============================================================


def _load_module_handler(module_key):
    if module_key == "project":
        from modules.project import decide_action, reset_state, ACTIONS, ACTION_KEYS
        return decide_action, reset_state, ACTIONS, ACTION_KEYS
    if module_key == "job":
        from modules.job import decide_action, reset_state, ACTIONS, ACTION_KEYS
        return decide_action, reset_state, ACTIONS, ACTION_KEYS
    if module_key == "activities":
        from modules.activities import decide_action, reset_state, ACTIONS, ACTION_KEYS
        return decide_action, reset_state, ACTIONS, ACTION_KEYS
    if module_key == "timesheet":
        from modules.timesheet import decide_action, reset_state, ACTIONS, ACTION_KEYS
        return decide_action, reset_state, ACTIONS, ACTION_KEYS

    raise ValueError("Unknown module: '{}'. Add it to _load_module_handler.".format(module_key))


async def is_page_alive(page):
    try:
        await page.evaluate("1")
        return True
    except Exception:
        # Browser tab closed or crashed — not an error we need to log noisily
        return False


# ============================================================
# CORE RUN LOOP
# ============================================================

async def run(url, module_key, action_key, goal, test_mode=False):
    """
    Main automation loop — fully automatic, no user interaction needed.

    Credentials are read from config/settings.py (LOGIN_EMAIL, LOGIN_PASSWORD).
    Session is created automatically on first run, reused on subsequent runs.
    """

    # ── STEP 0: Ensure valid session ──────────────────────────
    if not session_exists():
        print("[MAIN] No valid session — starting auto-login...")
        logger.info("No valid session found — starting auto-login")
        await create_session(base_url=url, viewport=VIEWPORT)
        print("[MAIN] Session created. Starting automation...\n")
        logger.info("Session created. Starting automation.")

    # ── STEP 1: Launch browser with session ───────────────────
    reporter = TestReporter(
        goal=goal, url=url,
        email=LOGIN_EMAIL, password=LOGIN_PASSWORD
    ) if test_mode else None

    decide_action, reset_state, _, _ = _load_module_handler(module_key)
    reset_state()

    _BROWSER_ARGS = ["--disable-blink-features=AutomationControlled"]

    async with async_playwright() as p:
        browser, context, page = await load_session(
            playwright=p,
            headless=HEADLESS,
            viewport=VIEWPORT,
            args=_BROWSER_ARGS,
        )

        async def handle_dialog(dialog):
            print("[DIALOG] '{}' -> accepting".format(dialog.message))
            await dialog.accept()

        page.on("dialog", handle_dialog)

        # Navigate to app
        loaded = False
        for attempt in range(3):
            try:
                print("[NAV] Loading {}  (attempt {})".format(url, attempt + 1))
                logger.info("Navigating to %s (attempt %d)", url, attempt + 1)
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                print("[OK] Page loaded")
                logger.info("Page loaded: %s", url)
                loaded = True
                break
            except PlaywrightTimeout as e:
                print("[WARN] Navigation timed out (attempt {}): {}".format(attempt + 1, e))
                logger.warning("Navigation timed out (attempt %d): %s", attempt + 1, e)
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2 ** attempt))
            except Exception as e:
                print("[WARN] Navigation failed (attempt {}): {}".format(attempt + 1, e))
                logger.warning("Navigation failed (attempt %d): %s", attempt + 1, e)
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2 ** attempt))

        if not loaded:
            print("[ERR] Could not load page after 3 attempts")
            logger.error("Could not load page after 3 attempts: %s", url)
            if reporter:
                reporter.start()
                reporter.finish(result="FAIL", reason="Navigation failed")
                reporter.save_report()
                reporter.print_summary()
            await browser.close()
            return

        # ── STEP 0b: Verify session via actual navigation ──────────
        if is_redirected_to_sso(page.url):
            print("[SESSION] Redirected to SSO — trying refresh token (waiting 5s)...")
            logger.info("SSO redirect after navigation — attempting refresh token")
            await page.wait_for_timeout(5000)
            if is_redirected_to_sso(page.url):
                print("[SESSION] Both tokens expired — fresh login needed")
                logger.error("Both tokens expired — fresh login needed")
                delete_session()
                await browser.close()
                if reporter:
                    reporter.start()
                    reporter.finish(result="FAIL", reason="Session expired — re-run to re-login")
                    reporter.save_report()
                    reporter.print_summary()
                return
            else:
                print("[SESSION] Refresh token worked")
                logger.info("Refresh token worked — session restored")
                await context.storage_state(path=str(get_session_file()))
        else:
            print("[SESSION] Access token valid")
            logger.info("Access token valid — session active")
            await context.storage_state(path=str(get_session_file()))

        print("[MAIN] Logged in via session ✓\n")

        if reporter:
            reporter.start()

        last_was_wait = False

        # ── STEP 2: Automation loop ───────────────────────────
        for step_num in range(MAX_STEPS):
            print("\n{} STEP {} {}".format("=" * 12, step_num + 1, "=" * 12))

            if not await is_page_alive(page):
                print("[ERR] Browser closed — stopping")
                logger.error("Browser tab closed or crashed at step %d", step_num + 1)
                if reporter:
                    reporter.finish(result="FAIL", reason="Browser closed")
                    reporter.save_report()
                    reporter.print_summary()
                break

            current_url = page.url
            print("URL: {}".format(current_url))

            if is_redirected_to_sso(current_url):
                print("[SESSION] Mid-run SSO redirect — trying refresh token (waiting 5s)...")
                logger.warning("Mid-run SSO redirect at step %d — attempting refresh token", step_num + 1)
                await page.wait_for_timeout(5000)
                if is_redirected_to_sso(page.url):
                    print("[SESSION] Both tokens expired — fresh login needed")
                    logger.error("Both tokens expired mid-run at step %d — stopping", step_num + 1)
                    delete_session()
                    if reporter:
                        reporter.finish(result="FAIL", reason="Session expired mid-run")
                        reporter.save_report()
                        reporter.print_summary()
                    break
                else:
                    print("[SESSION] Refresh token worked")
                    logger.info("Refresh token worked mid-run at step %d", step_num + 1)
                    await context.storage_state(path=str(get_session_file()))
                    continue

            try:
                await page.wait_for_load_state("domcontentloaded", timeout=DOM_SETTLE_MS)
            except PlaywrightTimeout:
                # DOM did not settle within the timeout — proceed anyway
                logger.debug("DOM settle timeout at step %d — continuing", step_num + 1)

            if "microsoftonline.com" in current_url:
                try:
                    await page.wait_for_selector("input", timeout=5000)
                except PlaywrightTimeout:
                    # Input field not found on SSO page — log and continue
                    logger.debug("SSO input not found at step %d — continuing", step_num + 1)
                await page.wait_for_timeout(SSO_SETTLE_MS)

            raw_dom = await extract_live_dom(page)
            if not last_was_wait:
                print("[DOM] {} elements".format(len(raw_dom)))

            action = await decide_action(
                action   = action_key,
                dom      = raw_dom,
                url      = current_url,
                goal     = goal,
                email    = LOGIN_EMAIL,
                password = LOGIN_PASSWORD,
                page     = page,
            )
            print("[ACTION] {}".format(action))

            if reporter:
                reporter.log_step(step_num + 1, action, current_url)

            if action.get("action") == "done":
                result = action.get("result", "UNKNOWN")
                reason = action.get("reason", "")
                icon   = "[PASS]" if result == "PASS" else ("[FAIL]" if result == "FAIL" else "[?]")
                print("\n{}  {}  —  {}".format(icon, result, reason))
                logger.info("Run finished: result=%s reason=%s", result, reason)
                if reporter:
                    reporter.finish(result=result, reason=reason)
                    reporter.save_report()
                    reporter.print_summary()
                break

            last_was_wait = action.get("action") == "wait"
            success = await execute_step(page, raw_dom, action)
            if reporter:
                reporter.update_last_step(success=success)

        else:
            print("\n[FAIL] Max steps reached")
            logger.error("Max steps (%d) reached without completion", MAX_STEPS)
            if reporter:
                reporter.finish(result="FAIL", reason="Max steps reached")
                reporter.save_report()
                reporter.print_summary()

        await asyncio.sleep(POST_RUN_S)
        try:
            await browser.close()
        except Exception as e:
            logger.warning("Browser close raised an error (safe to ignore): %s", e)


# ============================================================
# GOAL BUILDERS
# ============================================================

def _build_timesheet_goal(extra_parts):
    if len(extra_parts) < 3:
        return "add_timesheet start {}".format(" | ".join(extra_parts))

    goal = "add_timesheet start {} | project {} | job {}".format(
        extra_parts[0], extra_parts[1], extra_parts[2])

    hours = input("  Hours per day [8]: ").strip()
    if hours:
        goal += " | logging hours {}".format(hours)

    location = input("  Location [ascentt office] (wfh/client office/ascentt office/travel/remote): ").strip()
    if location:
        goal += " | location {}".format(location)

    remarks = input("  Remarks (optional, press Enter to skip): ").strip()
    if remarks:
        goal += " | remarks {}".format(remarks)

    return goal


def _build_clone_goal(extra_parts):
    start_date = extra_parts[0].strip() if extra_parts else ""
    return "clone_last_week start {}".format(start_date) if start_date else "clone_last_week"


def _build_approval_goal(extra_parts):
    from datetime import datetime
    start_date   = extra_parts[0].strip() if len(extra_parts) > 0 else datetime.now().strftime("%Y-%m-%d")
    project_name = extra_parts[1].strip() if len(extra_parts) > 1 else ""
    requested_by = extra_parts[2].strip() if len(extra_parts) > 2 else ""
    action       = extra_parts[3].strip().lower() if len(extra_parts) > 3 else "approve"

    if not start_date:
        start_date = datetime.now().strftime("%Y-%m-%d")

    parts = [
        "approve_timesheet",
        "start {}".format(start_date),
        "project {}".format(project_name),
    ]
    if requested_by:
        parts.append("requested_by {}".format(requested_by))
    parts.append("action {}".format(action if action in ("approve", "reject") else "approve"))
    return " | ".join(parts)


# ============================================================
# CLI
# ============================================================

def _select_module():
    print("\n" + "-" * 45)
    print("  MODULE SELECT")
    print("-" * 45)
    for i, key in enumerate(MODULE_KEYS, start=1):
        print("  {}  ->  {}".format(i, MODULES[key]["name"]))
    print("-" * 45)

    while True:
        choice = input("  Select module (number or name): ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(MODULE_KEYS):
                key = MODULE_KEYS[idx]
                return key, MODULES[key]
        elif choice.lower() in MODULES:
            return choice.lower(), MODULES[choice.lower()]
        print("  [WARN] Invalid choice, please try again")


def _select_action(module_key, module_info):
    _, _, ACTIONS, ACTION_KEYS = _load_module_handler(module_key)

    print("\n" + "-" * 45)
    print("  {} — ACTION SELECT".format(module_info["name"].upper()))
    print("-" * 45)
    for i, key in enumerate(ACTION_KEYS, start=1):
        print("  {}  ->  {}".format(i, ACTIONS[key]["label"]))
    print("-" * 45)

    while True:
        choice = input("  Select action (number or name): ").strip()
        action_key = None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(ACTION_KEYS):
                action_key = ACTION_KEYS[idx]
        elif choice.lower() in ACTIONS:
            action_key = choice.lower()

        if action_key:
            break
        print("  [WARN] Invalid choice, please try again")

    extra_parts = []
    nt = ACTIONS[action_key]["needs_target"]
    if nt is True:
        val = input("  Enter {} name: ".format(module_info["name"])).strip()
        if val:
            extra_parts.append(val)
    elif isinstance(nt, list):
        for prompt_label in nt:
            val = input("  Enter {}: ".format(prompt_label)).strip()
            extra_parts.append(val)

    if action_key == "add_job" and len(extra_parts) == 2:
        goal = "add_job job {} | {}".format(extra_parts[0], extra_parts[1])
    elif action_key == "add_activities" and len(extra_parts) == 3:
        goal = "add_activities project {} | job {} | activities {}".format(
            extra_parts[0], extra_parts[1], extra_parts[2])
    elif action_key == "add_timesheet":
        goal = _build_timesheet_goal(extra_parts)
    elif action_key == "clone_last_week":
        goal = _build_clone_goal(extra_parts)
    elif action_key == "approve_timesheet":
        goal = _build_approval_goal(extra_parts)
    else:
        goal = "{} {}".format(action_key, module_key)
        if extra_parts:
            goal += " " + " | ".join(extra_parts)

    return action_key, goal


def get_inputs():
    """
    Collect only module/action inputs from CLI.
    Email, password, and URL are read from config — no prompts for those.
    """
    print("\n" + "=" * 45)
    print("  A-Vertex Automation Tool")
    print("=" * 45)
    print("  Email : {}".format(LOGIN_EMAIL))
    print("  URL   : {}".format(BASE_URL))

    if session_exists():
        print("  [SESSION] Valid session — login will be skipped ✓")
    else:
        print("  [SESSION] No session — auto-login will run once")

    module_key, module_info = _select_module()
    action_key, goal        = _select_action(module_key, module_info)

    print("\n" + "=" * 45)
    print("  URL    : {}".format(BASE_URL))
    print("  Email  : {}".format(LOGIN_EMAIL))
    print("  Module : {}".format(module_info["name"]))
    print("  Goal   : {}".format(goal))
    print("=" * 45 + "\n")

    return module_key, action_key, goal


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    module_key, action_key, goal = get_inputs()
    asyncio.run(
        run(
            url        = BASE_URL,
            module_key = module_key,
            action_key = action_key,
            goal       = goal,
            test_mode  = True,
        )
    )