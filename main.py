import asyncio
from playwright.async_api import async_playwright

from config.settings    import (
    DEFAULT_URL, DEFAULT_EMAIL,
    MAX_STEPS, DOM_SETTLE_MS, SSO_SETTLE_MS, POST_RUN_S,
    VIEWPORT, HEADLESS,
)
from dom.dom_builder    import extract_live_dom
from executor.executor  import execute_step
from report.test_report import TestReporter
from modules            import MODULES, MODULE_KEYS

# ============================================================
# main.py — Entry point only.
# Login, nav, DOM, timing — all defined in separate files.
# This file only:
#   1. Shows the CLI menu
#   2. Launches the browser
#   3. Runs the per-step loop
# ============================================================


def _load_module_handler(module_key):
    """
    Load decide_action and reset_state for the given module key.

    To add a new module:
      1. Create modules/<name>.py
      2. Register it in modules/__init__.py
      3. Add one if-line here
    """
    if module_key == "project":
        from modules.project import decide_action, reset_state, ACTIONS, ACTION_KEYS
        return decide_action, reset_state, ACTIONS, ACTION_KEYS

    # ── Add new modules here ───────────────────────────────────
    if module_key == "job":
        from modules.job import decide_action, reset_state, ACTIONS, ACTION_KEYS
        return decide_action, reset_state, ACTIONS, ACTION_KEYS
    if module_key == "activities":
            from modules.activities import decide_action, reset_state, ACTIONS, ACTION_KEYS
            return decide_action, reset_state, ACTIONS, ACTION_KEYS
    
    # if module_key == "timesheet":
    #     from modules.timesheet import decide_action, reset_state, ACTIONS, ACTION_KEYS
    #     return decide_action, reset_state, ACTIONS, ACTION_KEYS

    raise ValueError("Unknown module: '{}'. Add it to _load_module_handler.".format(module_key))


# ============================================================
# PAGE ALIVE CHECK
# ============================================================

async def is_page_alive(page):
    """Returns True if the browser page is still open and responsive."""
    try:
        await page.evaluate("1")
        return True
    except Exception:
        return False


# ============================================================
# CORE RUN LOOP
# ============================================================

async def run(url, module_key, action_key, goal,
              email=None, password=None, test_mode=False):
    """
    Main automation loop.
    Launches the browser, loads the page, then repeatedly:
      1. Extracts the live DOM
      2. Asks the module what to do next (decide_action)
      3. Executes that action via execute_step
    Stops when action == 'done' or MAX_STEPS is reached.
    """
    reporter = TestReporter(goal=goal, url=url) if test_mode else None
    decide_action, reset_state, _, _ = _load_module_handler(module_key)
    reset_state()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport=VIEWPORT,
            ignore_https_errors=True,
        )
        page = await context.new_page()
        
        # Auto-accept browser native dialogs (window.confirm, window.alert).
        # The delete confirmation on this app uses window.confirm() —
        # without this handler Playwright would dismiss it automatically
        # and the delete would never go through.
        async def handle_dialog(dialog):
            print("[DIALOG] '{}' -> accepting".format(dialog.message))
            await dialog.accept()
 
        page.on("dialog", handle_dialog)

        # Navigate with exponential back-off (up to 3 attempts)
        loaded = False
        for attempt in range(3):
            try:
                print("[NAV] Loading {}  (attempt {})".format(url, attempt + 1))
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                print("[OK] Page loaded")
                loaded = True
                break
            except Exception as e:
                print("[WARN] Navigation failed: {}".format(e))
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2 ** attempt))

        if not loaded:
            print("[ERR] Could not load page after 3 attempts")
            if reporter:
                reporter.start()
                reporter.finish(result="FAIL", reason="Navigation failed")
                reporter.save_report()
                reporter.print_summary()
            await browser.close()
            return

        if reporter:
            reporter.start()

        last_was_wait = False

        for step_num in range(MAX_STEPS):
            print("\n{} STEP {} {}".format("=" * 12, step_num + 1, "=" * 12))

            if not await is_page_alive(page):
                print("[ERR] Browser closed — stopping")
                if reporter:
                    reporter.finish(result="FAIL", reason="Browser closed")
                    reporter.save_report()
                    reporter.print_summary()
                break

            current_url = page.url
            print("URL: {}".format(current_url))

            # Wait for DOM to settle
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=DOM_SETTLE_MS)
            except Exception:
                pass

            # Extra wait on SSO pages so login inputs fully render
            if "microsoftonline.com" in current_url:
                try:
                    await page.wait_for_selector("input", timeout=5000)
                except Exception:
                    pass
                await page.wait_for_timeout(SSO_SETTLE_MS)

            raw_dom = await extract_live_dom(page)
            if not last_was_wait:
                print("[DOM] {} elements".format(len(raw_dom)))

            action = await decide_action(
                action   = action_key,
                dom      = raw_dom,
                url      = current_url,
                goal     = goal,
                email    = email,
                password = password,
            )
            print("[ACTION] {}".format(action))

            if reporter:
                reporter.log_step(step_num + 1, action, current_url)

            # Stop when the module signals completion
            if action.get("action") == "done":
                result = action.get("result", "UNKNOWN")
                reason = action.get("reason", "")
                icon   = "[PASS]" if result == "PASS" else ("[FAIL]" if result == "FAIL" else "[?]")
                print("\n{}  {}  —  {}".format(icon, result, reason))
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
            if reporter:
                reporter.finish(result="FAIL", reason="Max steps reached")
                reporter.save_report()
                reporter.print_summary()

        await asyncio.sleep(POST_RUN_S)
        try:
            await browser.close()
        except Exception:
            pass


# ============================================================
# CLI — Step 1: Module  →  Step 2: Action
# ============================================================

def _select_module():
    """Prompt the user to select a module from the registry."""
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
    """Prompt the user to select an action for the chosen module."""
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
 
    # If the action needs one or more target inputs, prompt for each.
    # needs_target can be:
    #   True        — single prompt: "Enter <Module> name:"
    #   ["a","b"]   — multiple prompts, one per label in the list
    # The collected values are joined with " | " and appended to the goal.
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
    else:
        goal = "{} {}".format(action_key, module_key)
        if extra_parts:
            goal += " " + " | ".join(extra_parts)
    
    return action_key, goal

def get_inputs():
    """Collect all inputs from the user via CLI and return them."""
    print("\n" + "=" * 45)
    print("  A-Vertex Automation Tool")
    print("=" * 45)

    print("\n  Login Details  (press Enter to use defaults)")
    url = input("  App URL  [{}]: ".format(DEFAULT_URL)).strip()
    if not url:
        url = DEFAULT_URL

    email = input("  Email    [{}]: ".format(DEFAULT_EMAIL)).strip()
    if not email:
        email = DEFAULT_EMAIL

    password = input("  Password: ").strip()

    module_key, module_info = _select_module()
    action_key, goal        = _select_action(module_key, module_info)

    print("\n" + "=" * 45)
    print("  URL      : {}".format(url))
    print("  Email    : {}".format(email))
    print("  Module   : {}".format(module_info["name"]))
    print("  Goal     : {}".format(goal))
    print("=" * 45 + "\n")

    return url, email, password, module_key, action_key, goal


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    url, email, password, module_key, action_key, goal = get_inputs()
    asyncio.run(
        run(
            url        = url,
            module_key = module_key,
            action_key = action_key,
            goal       = goal,
            email      = email,
            password   = password,
            test_mode  = True,
        )
    )