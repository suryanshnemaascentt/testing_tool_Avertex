

from config.settings import T_KEY, T_NAV
from executor.actions import do_click, do_type, do_select, _wait
import executor.form_filler as _form_filler

# ============================================================
# executor/executor.py — Step dispatcher.
#
# Routes each action dict returned by a module's decide_action()
# to the correct handler function.
#
# To add a new module form:
#   1. Create fill_<module>_form() in executor/form_filler.py
#   2. Add one if-line inside the "fill_form" block below
#   Nothing else needs to change.
# ============================================================


async def execute_step(page, dom, step):
    """
    Execute a single automation step.

    Args:
        page  — Playwright page object
        dom   — raw DOM list from the last extract_live_dom() call
        step  — action dict from decide_action(), e.g.
                {"action": "click", "selector": "button:has-text('Save')"}

    Returns:
        True on success, False on failure.
    """
    action   = step.get("action")
    selector = step.get("selector")
    value    = step.get("text") or step.get("value")

    try:
        # ── Actions that need no selector ────────────────────
        if action == "wait":
            await _wait(page, step.get("seconds", 1) * 1000)
            return True

        if action == "key":
            sel = step.get("selector")
            key = step.get("key", "Escape")
            try:
                if sel:
                    await page.locator(sel).first.press(key)
                else:
                    await page.keyboard.press(key)
            except Exception:
                await page.keyboard.press(key)
            await _wait(page, T_KEY)
            return True

        if action == "navigate":
            url = step.get("url", "")
            if url:
                print("[NAV] Navigate -> {}".format(url))
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await _wait(page, T_NAV)
            return True

        if action == "done":
            r    = step.get("result", "UNKNOWN")
            icon = "[PASS]" if r == "PASS" else ("[FAIL]" if r == "FAIL" else "[?]")
            print("{} DONE: {} -- {}".format(icon, r, step.get("reason", "")))
            return True

        if action == "autocomplete_pick_first":
            # Pick the first visible autocomplete option without searching
            try:
                opt = page.locator('[role="option"]').first
                await opt.wait_for(state="visible", timeout=2000)
                txt = await opt.inner_text()
                await opt.click(timeout=2000)
                print("   [OK] Picked: '{}'".format(txt))
            except Exception:
                await page.keyboard.press("Escape")
            return True

        # ── fill_form and fill_*_form — dynamic dispatch ────────
        # No changes needed here when adding new modules.
        # Just add fill_<module>_form() in executor/form_filler.py.
        # This block finds and calls it automatically.
        if action in ("fill_form", "fill_job_form") or action.startswith("fill_") and action.endswith("_form"):
            params      = step.get("params", {})
            module_name = step.get("module", "")
            # Derive function name from action or module name
            if action == "fill_form":
                fn_name = "fill_{}_form".format(module_name or "project")
            else:
                fn_name = action   # e.g. "fill_job_form" -> direct match
            fn = getattr(_form_filler, fn_name, None)
            if fn is None:
                print("[ERR] No form filler found: '{}' — add it to executor/form_filler.py".format(fn_name))
                return False
            print("[FORM] Calling {}()".format(fn_name))
            return await fn(page, params)

        # ── Actions that require a selector ──────────────────
        if not selector:
            print("[ERR] No selector provided")
            return False

        print("\n[ACT] {} -> {}".format(action, selector))
        loc   = page.locator(selector)
        count = await loc.count()
        print("   Found {} element(s)".format(count))
        if count == 0:
            print("[ERR] Element not found — skipping")
            return False

        el = loc.first
        try:
            await el.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass

        if action == "click":
            soft       = step.get("soft_fail", False) or step.get("sso_yes", False)
            force      = step.get("force", False)
            extra_wait = step.get("extra_wait_ms", 0)   # used for delete confirm dialog
            result     = await do_click(page, el, soft_fail=soft, force_first=force)
            if extra_wait > 0:
                await _wait(page, extra_wait)
            return result

        if action == "type":
            return await do_type(page, el, value or "")

        if action == "select":
            return await do_select(page, el, value or "")

        print("[ERR] Unknown action: {}".format(action))
        return False

    except Exception as e:
        print("[ERR] Executor error: {}".format(e))
        import traceback
        traceback.print_exc()
        return False