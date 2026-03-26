import asyncio
import os
from playwright.async_api import async_playwright

from dom.dom_builder    import extract_live_dom
from executor.executor  import execute_step
from report.test_report import TestReporter
from modules            import MODULES, MODULE_KEYS


MAX_STEPS      = int(os.getenv("AVERTEX_MAX_STEPS", "60"))
_DOM_SETTLE_MS = 5000
_SSO_SETTLE_MS = 800
_POST_RUN_S    = 3


def _load_module_handler(module_key):
    if module_key == "project":
        from modules.project import decide_action, reset_state, ACTIONS, ACTION_KEYS
        return decide_action, reset_state, ACTIONS, ACTION_KEYS
    elif module_key == "client":
        from modules.client import decide_action, reset_state, ACTIONS, ACTION_KEYS
        return decide_action, reset_state, ACTIONS, ACTION_KEYS
    elif module_key == "add_client":   # ✅ ADD THIS BLOCK
        from modules.add_client import decide_action, reset_state, ACTIONS, ACTION_KEYS
        return decide_action, reset_state, ACTIONS, ACTION_KEYS
    elif module_key == "access_control":
        from modules.access_control import decide_action, reset_state, ACTIONS, ACTION_KEYS
        return decide_action, reset_state, ACTIONS, ACTION_KEYS
    elif module_key == "estimate_AI_based":
        from modules.estimate_AI_based import decide_action, reset_state, ACTIONS, ACTION_KEYS
        return decide_action, reset_state, ACTIONS, ACTION_KEYS
    raise ValueError("Unknown module: " + module_key)
    


async def is_page_alive(page):
    try:
        await page.evaluate("1")
        return True
    except Exception:
        return False


async def run(url, module_key, action_key, goal,
              email=None, password=None, test_mode=False):

    reporter = TestReporter(goal=goal, url=url) if test_mode else None

    decide_action, reset_state, _, _ = _load_module_handler(module_key)
    reset_state()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )
        page = await context.new_page()

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
            print("\n{} STEP {} {}".format("="*12, step_num + 1, "="*12))

            if not await is_page_alive(page):
                print("[ERR] Browser closed — stopping")
                if reporter:
                    reporter.finish(result="FAIL", reason="Browser closed")
                    reporter.save_report()
                    reporter.print_summary()
                break

            current_url = page.url
            print("URL: {}".format(current_url))

            try:
                await page.wait_for_load_state("domcontentloaded", timeout=_DOM_SETTLE_MS)
            except Exception:
                pass

            if "microsoftonline.com" in current_url:
                try:
                    await page.wait_for_selector("input", timeout=5000)
                except Exception:
                    pass
                await page.wait_for_timeout(_SSO_SETTLE_MS)

            raw_dom = await extract_live_dom(page)
            print("dom print",raw_dom)
            if not last_was_wait:
                print("[DOM] {} elements".format(len(raw_dom)))

            action = await decide_action(
                action=action_key,
                dom=raw_dom,
                url=current_url,
                goal=goal,
                email=email,
                password=password,
            )
            print("[ACTION] {}".format(action))

            if reporter:
                reporter.log_step(step_num + 1, action, current_url)

            if action.get("action") == "done":
                result = action.get("result", "UNKNOWN")
                reason = action.get("reason", "")
                icon = "[PASS]" if result == "PASS" else ("[FAIL]" if result == "FAIL" else "[?]")
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

        await asyncio.sleep(_POST_RUN_S)
        try:
            await browser.close()
        except Exception:
            pass


def _select_module():
    print("\n" + "-" * 45)
    print("  MODULE SELECT")
    print("-" * 45)
    for i, key in enumerate(MODULE_KEYS, start=1):
        print("  {}  ->  {}".format(i, MODULES[key]["name"]))
    print("-" * 45)

    while True:
        choice = input("  select module (number or name): ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(MODULE_KEYS):
                key = MODULE_KEYS[idx]
                return key, MODULES[key]
        elif choice.lower() in MODULES:
            key = choice.lower()
            return key, MODULES[key]
        print("  [WARN] Invalid choice, retry")


def _select_action(module_key, module_info):
    _, _, ACTIONS, ACTION_KEYS = _load_module_handler(module_key)

    print("\n" + "-" * 45)
    print("  {} - ACTION SELECT".format(module_info["name"].upper()))
    print("-" * 45)
    for i, key in enumerate(ACTION_KEYS, start=1):
        print("  {}  ->  {}".format(i, ACTIONS[key]["label"]))
    print("-" * 45)

    while True:
        choice = input("  Action choose action ").strip()
        action_key = None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(ACTION_KEYS):
                action_key = ACTION_KEYS[idx]
        elif choice.lower() in ACTIONS:
            action_key = choice.lower()

        if action_key:
            break
        print("  [WARN] Invalid choice, retry")

    extra = ""
    if ACTIONS[action_key]["needs_target"]:
        extra = input("  {} tell name: ".format(module_info["name"])).strip()

    goal = "{} {}".format(action_key, module_key)
    if extra:
        goal += " " + extra

    return action_key, goal


def get_inputs():
    print("\n" + "=" * 45)
    print("  A-Vertex Automation Tool")
    print("=" * 45)

    print("\n  Login Details  (Enter = default)")
    url = input("  App URL  [https://vertex-dev.savetime.com/]: ").strip()
    if not url:
        url = "https://vertex-dev.savetime.com/"

    email = input("  Email    [suraj.kadam@ascentt.com]: ").strip()
    if not email:
        email = "suraj.kadam@ascentt.com"

    password = input("  Password: ").strip()
    if not password:
        password='$Sara$1001'
    module_key, module_info = _select_module()
    action_key, goal        = _select_action(module_key, module_info)

    print("\n" + "=" * 45)
    print("  URL      : {}".format(url))
    print("  Email    : {}".format(email))
    print("  Module   : {}".format(module_info["name"]))
    print("  Goal     : {}".format(goal))
    print("=" * 45 + "\n")

    return url, email, password, module_key, action_key, goal


if __name__ == "__main__":
    url, email, password, module_key, action_key, goal = get_inputs()
    asyncio.run(
        run(
            url=url,
            module_key=module_key,
            action_key=action_key,
            goal=goal,
            email=email,
            password=password,
            test_mode=True,
        )
    )