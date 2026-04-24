
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
    """
    Dynamically import modules/<module_key>.py.
    No changes needed here when adding a new module — just:
      1. Create modules/<name>.py
      2. Register it in modules/__init__.py MODULES dict
    """
    import importlib
    if module_key not in MODULES:
        raise ValueError(
            "Unknown module: '{}'. Available: {}. "
            "Register it in modules/__init__.py.".format(
                module_key, list(MODULES.keys())))
    try:
        mod = importlib.import_module("modules.{}".format(module_key))
    except ModuleNotFoundError as exc:
        raise ValueError(
            "Module file not found for '{}': {}".format(module_key, exc))
    return mod.decide_action, mod.reset_state, mod.ACTIONS, mod.ACTION_KEYS


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

async def run(url, module_key, action_key, goal, test_mode=False, keep_session=False):
    """
    Main automation loop — fully automatic, no user interaction needed.

    Credentials are read from config/settings.py (LOGIN_EMAIL, LOGIN_PASSWORD).
    Session is created automatically on first run, reused on subsequent runs.

    Args:
        keep_session — if True, skip state reset for login/nav (reuse active session)

    Returns:
        dict with keys 'result' (PASS/FAIL) and 'reason' (str).
    """
    _run_outcome = {"result": "FAIL", "reason": "Run did not complete"}

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
    reset_state(keep_session=keep_session)

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
            return {"result": "FAIL", "reason": "Navigation failed"}

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
                return {"result": "FAIL", "reason": "Session expired — re-run to re-login"}
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
                _run_outcome = {"result": "FAIL", "reason": "Browser closed"}
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
                    _run_outcome = {"result": "FAIL", "reason": "Session expired mid-run"}
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
                _run_outcome = {"result": result, "reason": reason}
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
            _run_outcome = {"result": "FAIL", "reason": "Max steps reached"}

        await asyncio.sleep(POST_RUN_S)
        try:
            await browser.close()
        except Exception as e:
            logger.warning("Browser close raised an error (safe to ignore): %s", e)
        return _run_outcome


# ============================================================
# NEGATIVE SUITE RUNNER
# ============================================================

async def run_negative_suite(url, module_key, action_key, selected_scenarios=None):
    """
    Run negative scenarios for the given module + action.

    Args:
        selected_scenarios — list of scenario dicts to run, or None to run all.
            Each dict must have keys: id, action_key, name, description.
            Pass the return value of _select_negative_scenarios() here, or
            leave as None to run every entry in NEGATIVE_CREATE_SCENARIOS.

    Loops through the chosen scenarios, calls run() for each, collects results,
    and generates an individual report per scenario plus one combined suite report.

    Returns:
        list of result dicts with keys: id, name, status, reason
    """
    from modules.project import NEGATIVE_CREATE_SCENARIOS
    from report.test_report import generate_suite_report

    suite_name = "{} {}".format(module_key.upper(), action_key.upper())
    scenarios  = selected_scenarios if selected_scenarios is not None else NEGATIVE_CREATE_SCENARIOS
    results    = []

    print("\n" + "=" * 50)
    print("  NEGATIVE TEST SUITE — {}".format(suite_name))
    print("  Scenarios: {}".format(len(scenarios)))
    print("=" * 50)

    for i, sc in enumerate(scenarios):
        print("\n[SUITE] Running {} / {}  —  {} ({})".format(
            i + 1, len(scenarios), sc["id"], sc["name"]))

        goal      = "{} — {}".format(sc["id"], sc["name"])
        # Each run() opens a brand-new browser via async_playwright().
        # keep_session=True would skip reset_nav(), leaving nav_done()=True
        # as stale state from the previous run — causing all scenarios after
        # the first to skip navigation to /projects and fill a broken form.
        keep_sess = False

        outcome = await run(
            url        = url,
            module_key = module_key,
            action_key = sc["action_key"],
            goal       = goal,
            test_mode  = True,
            keep_session = keep_sess,
        )

        results.append({
            "id":     sc["id"],
            "name":   sc["name"],
            "status": outcome.get("result", "FAIL"),
            "reason": outcome.get("reason", ""),
        })

        result_str = outcome.get("result", "FAIL")
        if result_str == "PASS":
            icon = "[PASS]"
        elif result_str == "WARN":
            icon = "[WARN]"
        else:
            icon = "[FAIL]"
        print("[SUITE] {} {} — {}".format(icon, sc["id"], outcome.get("reason", "")))

    # Combined suite report
    generate_suite_report(results, suite_name)

    # Print suite summary
    total  = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    warned = sum(1 for r in results if r["status"] == "WARN")
    print("\n" + "=" * 50)
    print("  SUITE SUMMARY — {}".format(suite_name))
    print("  Total: {}  |  Passed: {}  |  Failed: {}  |  Warned: {}".format(
        total, passed, failed, warned))
    print("=" * 50 + "\n")

    return results


# ============================================================
# RUN ALL MODULES
# ============================================================

async def run_all_modules(url, items):
    """
    Run every (module_key, action_key, goal) item in sequence.
    Errors are caught per-item and logged — execution always continues.
    Generates a single consolidated suite report at the end.

    Args:
        items — list of dicts from _collect_run_all_inputs():
                {"module_key", "action_key", "goal", "label"}

    Returns:
        list of result dicts: {"id", "name", "status", "reason", "steps"}
    """
    from report.test_report import generate_suite_report

    total   = len(items)
    results = []

    print("\n" + "=" * 60)
    print("  RUN ALL — {} action(s) across {} module(s)".format(
        total, len(set(i["module_key"] for i in items))))
    print("=" * 60)

    for idx, item in enumerate(items):
        module_key = item["module_key"]
        action_key = item["action_key"]
        goal       = item["goal"]
        label      = item["label"]
        run_id     = "{}.{}".format(module_key, action_key)

        print("\n[RUN-ALL] ({}/{}) {}".format(idx + 1, total, label))
        print("[RUN-ALL] goal: {}".format(goal))

        try:
            outcome = await run(
                url          = url,
                module_key   = module_key,
                action_key   = action_key,
                goal         = goal,
                test_mode    = True,
                keep_session = False,
            )
            results.append({
                "id":     run_id,
                "name":   label,
                "status": outcome.get("result", "FAIL"),
                "reason": outcome.get("reason", ""),
            })
            icon = "[PASS]" if outcome.get("result") == "PASS" else "[FAIL]"
            print("[RUN-ALL] {} {} — {}".format(icon, run_id, outcome.get("reason", "")))

        except Exception as exc:
            err_msg = str(exc)
            print("[RUN-ALL] [ERR] {} — {}".format(run_id, err_msg))
            results.append({
                "id":     run_id,
                "name":   label,
                "status": "FAIL",
                "reason": "Unexpected error: {}".format(err_msg),
            })

    # ── Consolidated suite report ─────────────────────────────
    generate_suite_report(results, "ALL MODULES RUN")

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    warned = sum(1 for r in results if r["status"] == "WARN")

    print("\n" + "=" * 60)
    print("  RUN-ALL COMPLETE")
    print("  Total: {}  |  Passed: {}  |  Failed: {}  |  Warned: {}".format(
        total, passed, failed, warned))
    print("=" * 60 + "\n")

    return results


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
        goal += " | hours {}".format(hours)

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
    print("  0  ->  Run All Modules")
    for i, key in enumerate(MODULE_KEYS, start=1):
        print("  {}  ->  {}".format(i, MODULES[key]["name"]))
    print("-" * 45)

    while True:
        choice = input("  Select module (number or name, 0 = Run All): ").strip()
        if choice == "0":
            return "__all__", None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(MODULE_KEYS):
                key = MODULE_KEYS[idx]
                return key, MODULES[key]
        elif choice.lower() in MODULES:
            return choice.lower(), MODULES[choice.lower()]
        print("  [WARN] Invalid choice, please try again")


# Action keys that belong exclusively to the negative suite.
# They are run automatically by run_negative_suite() and must NOT
# appear in the interactive action menu.
_NEG_ACTION_KEYS = {
    "create_empty_name", "create_duplicate",
    "neg_c_03", "neg_c_04", "neg_c_05",
    "neg_c_06", "neg_c_07", "neg_c_08",
}


def _select_negative_scenarios():
    """
    Display the full list of negative scenarios and let the user choose which to run.

    Accepted inputs:
      - Enter / 'all'       → every scenario
      - '7'                 → only scenario 7
      - '1,3,7'             → scenarios 1, 3 and 7
      - '1-4'               → scenarios 1 through 4 (inclusive)
      - '1,3-5,7'           → combinations of the above

    Returns:
        list of scenario dicts (subset of NEGATIVE_CREATE_SCENARIOS).
    """
    from modules.project import NEGATIVE_CREATE_SCENARIOS
    scenarios = NEGATIVE_CREATE_SCENARIOS

    print("\n" + "-" * 55)
    print("  NEGATIVE TEST SCENARIOS")
    print("-" * 55)
    for i, sc in enumerate(scenarios, start=1):
        print("  {:>2}  ->  [{}]  {}".format(i, sc["id"], sc["name"]))
        print("          {}".format(sc["description"]))
    print("-" * 55)
    print("  Enter numbers to select (e.g. 7,  1,3,7,  1-4,  all)")
    print("  Press Enter or type 'all' to run all {} scenarios".format(len(scenarios)))
    print("-" * 55)

    while True:
        raw = input("  Selection [all]: ").strip().lower()
        if not raw or raw == "all":
            print("  Will run all {} scenarios.".format(len(scenarios)))
            return list(scenarios)

        selected_indices = set()
        valid = True

        for part in (p.strip() for p in raw.split(",")):
            if not part:
                continue
            if part.isdigit():
                idx = int(part)
                if 1 <= idx <= len(scenarios):
                    selected_indices.add(idx)
                else:
                    print("  [WARN] {} is out of range (1-{})".format(part, len(scenarios)))
                    valid = False
                    break
            elif "-" in part:
                bounds = part.split("-", 1)
                if len(bounds) == 2 and bounds[0].isdigit() and bounds[1].isdigit():
                    lo, hi = int(bounds[0]), int(bounds[1])
                    if 1 <= lo <= hi <= len(scenarios):
                        selected_indices.update(range(lo, hi + 1))
                    else:
                        print("  [WARN] Range {}-{} is invalid (valid: 1-{})".format(
                            lo, hi, len(scenarios)))
                        valid = False
                        break
                else:
                    print("  [WARN] '{}' is not a valid range — use N-M (e.g. 2-5)".format(part))
                    valid = False
                    break
            else:
                print("  [WARN] '{}' is not a valid entry".format(part))
                valid = False
                break

        if not valid:
            continue

        if not selected_indices:
            print("  [WARN] No scenarios selected — please try again")
            continue

        selected = [scenarios[i - 1] for i in sorted(selected_indices)]
        print("\n  Will run {} scenario(s): {}".format(
            len(selected), ", ".join(s["id"] for s in selected)))
        return selected


def _select_test_type(action_key="create"):
    """
    Prompt for test type.
    Negative / Both are only available when action_key == 'create'
    (negative scenarios are implemented for Create only so far).
    """
    neg_available = (action_key == "create")

    print("\n" + "-" * 45)
    print("  TEST TYPE")
    print("-" * 45)
    print("  1  ->  Positive  (existing flow)")
    if neg_available:
        print("  2  ->  Negative  (all negative scenarios)")
        print("  3  ->  Both      (positive then negative)")
    else:
        print("  [NOTE] Negative testing is only available for the Create action")
    print("-" * 45)
    while True:
        tt = input("  Select test type [1]: ").strip()
        if tt in ("", "1"):
            return "positive"
        if tt == "2" and neg_available:
            return "negative"
        if tt == "3" and neg_available:
            return "both"
        if tt in ("2", "3") and not neg_available:
            print("  [WARN] Negative testing not available for this action — running Positive")
            return "positive"
        print("  [WARN] Invalid choice, please enter 1{}".format(", 2 or 3" if neg_available else ""))


def _select_action(module_key, module_info):
    _, _, ACTIONS, ACTION_KEYS = _load_module_handler(module_key)

    # Hide internal negative-suite action keys from the interactive menu
    visible_keys = [k for k in ACTION_KEYS if k not in _NEG_ACTION_KEYS]

    print("\n" + "-" * 45)
    print("  {} — ACTION SELECT".format(module_info["name"].upper()))
    print("-" * 45)
    for i, key in enumerate(visible_keys, start=1):
        print("  {}  ->  {}".format(i, ACTIONS[key]["label"]))
    print("-" * 45)

    while True:
        choice = input("  Select action (number or name): ").strip()
        action_key = None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(visible_keys):
                action_key = visible_keys[idx]
        elif choice.lower() in ACTIONS and choice.lower() not in _NEG_ACTION_KEYS:
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


def _collect_run_all_inputs():
    """
    Iterate every module and every non-NEG action_key.
    - needs_target=False  → goal built automatically, no prompt.
    - needs_target=True/list → prompt user once per required field.
      Pressing Enter (blank) skips that action entirely.

    Returns:
        list of {"module_key", "action_key", "goal", "label"}
    """
    items = []

    for module_key in MODULE_KEYS:
        _, _, ACTIONS, ACTION_KEYS = _load_module_handler(module_key)
        module_info  = MODULES[module_key]
        visible_keys = [k for k in ACTION_KEYS if k not in _NEG_ACTION_KEYS]

        for action_key in visible_keys:
            info  = ACTIONS[action_key]
            nt    = info["needs_target"]
            label = "{} → {}".format(module_info["name"], info["label"])

            extra_parts = []

            if nt is False:
                # Auto-runnable — build goal the same way _select_action does
                goal = "{} {}".format(action_key, module_key)

            elif nt is True:
                print("\n  [{}.{}] {}".format(module_key, action_key, info["label"]))
                val = input(
                    "    Enter {} name (blank = skip): ".format(module_info["name"])
                ).strip()
                if not val:
                    print("    → Skipped")
                    continue
                extra_parts.append(val)
                goal = "{} {}".format(action_key, module_key)
                goal += " " + " | ".join(extra_parts)

            elif isinstance(nt, list):
                print("\n  [{}.{}] {}".format(module_key, action_key, info["label"]))
                skip = False
                for prompt_label in nt:
                    val = input(
                        "    Enter {} (blank = skip action): ".format(prompt_label)
                    ).strip()
                    if not val:
                        print("    → Skipped")
                        skip = True
                        break
                    extra_parts.append(val)
                if skip:
                    continue

                # Reuse same goal-building logic as _select_action
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
            else:
                # Unknown needs_target type — skip safely
                continue

            items.append({
                "module_key": module_key,
                "action_key": action_key,
                "goal":       goal,
                "label":      label,
            })

    return items


def get_inputs():
    """
    Collect module / action / test-type inputs from CLI.

    Order:
      1. Module select
      2. Action select   (create / update / delete  — NEG internal keys hidden)
      3. Test type       (Negative / Both only offered when action == create)

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

    # ── Run All Modules mode ──────────────────────────────────
    if module_key == "__all__":
        print("\n" + "-" * 55)
        print("  RUN ALL MODULES")
        print("  Actions needing input will be prompted now.")
        print("  Leave any prompt blank to skip that action.")
        print("-" * 55)
        items = _collect_run_all_inputs()

        print("\n" + "=" * 55)
        print("  RUN-ALL QUEUE ({} action(s))".format(len(items)))
        for item in items:
            print("    • {}".format(item["label"]))
        print("=" * 55 + "\n")

        return "__all__", None, None, "run_all", items

    action_key, goal = _select_action(module_key, module_info)
    test_type               = _select_test_type(action_key)

    # When running negative scenarios, let the user pick which ones to execute.
    neg_selection = None
    if test_type in ("negative", "both"):
        neg_selection = _select_negative_scenarios()

    print("\n" + "=" * 45)
    print("  URL       : {}".format(BASE_URL))
    print("  Email     : {}".format(LOGIN_EMAIL))
    print("  Module    : {}".format(module_info["name"]))
    print("  Action    : {}".format(action_key))
    print("  Test Type : {}".format(test_type.upper()))
    if test_type in ("positive", "both"):
        print("  Goal      : {}".format(goal))
    if neg_selection is not None:
        print("  Neg. Scenarios : {}".format(
            ", ".join(s["id"] for s in neg_selection)))
    print("=" * 45 + "\n")

    return module_key, action_key, goal, test_type, neg_selection


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    import sys

    if "--auto" in sys.argv or "-a" in sys.argv:
        # ── Fully automated, zero-prompt run ─────────────────
        # Runs every module + positive + negative tests in order.
        # No user input required.
        # Usage:  python main.py --auto
        from tests.suite_runner import run_full_suite
        asyncio.run(run_full_suite(url=BASE_URL))

    else:
        # ── Existing interactive CLI (unchanged) ──────────────
        module_key, action_key, goal, test_type, neg_selection = get_inputs()

        if test_type == "run_all":
            asyncio.run(
                run_all_modules(
                    url   = BASE_URL,
                    items = neg_selection,   # holds the items list from _collect_run_all_inputs
                )
            )

        elif test_type == "positive":
            asyncio.run(
                run(
                    url        = BASE_URL,
                    module_key = module_key,
                    action_key = action_key,
                    goal       = goal,
                    test_mode  = True,
                )
            )

        elif test_type == "negative":
            asyncio.run(
                run_negative_suite(
                    url                = BASE_URL,
                    module_key         = module_key,
                    action_key         = action_key,
                    selected_scenarios = neg_selection,
                )
            )

        elif test_type == "both":
            # Run positive first, then the selected negative scenarios
            asyncio.run(
                run(
                    url        = BASE_URL,
                    module_key = module_key,
                    action_key = action_key,
                    goal       = goal,
                    test_mode  = True,
                )
            )
            asyncio.run(
                run_negative_suite(
                    url                = BASE_URL,
                    module_key         = module_key,
                    action_key         = action_key,
                    selected_scenarios = neg_selection,
                )
            )