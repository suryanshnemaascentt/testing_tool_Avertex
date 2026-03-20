import random
from typing import Optional
from config.settings import (
    T_SHORT, T_MEDIUM, T_OPTION_LOAD, T_KEY, T_DATE_SEG
)

# ============================================================
# executor/actions.py — Generic browser actions.
#
# Contains reusable functions for clicking, typing, selecting,
# and interacting with MUI components.
# No module-specific logic lives here.
# This file should rarely need to change when adding new modules.
# ============================================================


async def _wait(page, ms):
    """Wait for the given number of milliseconds."""
    await page.wait_for_timeout(ms)


# ── Click ────────────────────────────────────────────────────

async def do_click(page, element, soft_fail=False, force_first=False):
    """
    Click an element with fallback strategies.

    Args:
        force_first — skip the normal click and go straight to force click.
                      Use this for MUI buttons that need to trigger dialogs.
        soft_fail   — if True, return True even when all click strategies fail.
                      Useful for optional buttons like SSO "Yes".

    Strategy order (normal):  normal click  →  force click  →  JS click
    Strategy order (force_first):            force click  →  JS click
    """
    strategies = [{"force": True, "timeout": 3000}] if force_first else [
        {"timeout": 5000},
        {"force": True, "timeout": 3000},
    ]
    for kwargs in strategies:
        try:
            await element.click(**kwargs)
            print("   [OK] Click OK")
            await _wait(page, T_MEDIUM)
            return True
        except Exception as e:
            print("   [WARN] click({}): {}".format(list(kwargs.keys()), e))

    # Final fallback: native JS click
    try:
        await element.evaluate("el => el.click()")
        print("   [OK] JS click")
        await _wait(page, T_MEDIUM)
        return True
    except Exception as e:
        print("   [ERR] JS click: {}".format(e))
    # Fallback 2: dispatch real MouseEvents — works for MUI React buttons
    # that ignore force clicks and JS .click() because they listen for
    # synthetic React events, not native DOM events.
    try:
        await element.evaluate("""el => {
            el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true}));
            el.dispatchEvent(new MouseEvent('mouseup',   {bubbles:true, cancelable:true}));
            el.dispatchEvent(new MouseEvent('click',     {bubbles:true, cancelable:true}));
        }""")
        print("   [OK] MouseEvent dispatch")
        await _wait(page, T_MEDIUM)
        return True
    except Exception as e:
        print("   [ERR] MouseEvent dispatch: {}".format(e))

    if soft_fail:
        print("   [WARN] All clicks failed — soft_fail OK")
        return True
    return False


# ── Type ─────────────────────────────────────────────────────

async def do_type(page, element, value):
    """
    Type a value into an input element.
    Handles textarea, MUI combobox, and plain text inputs differently.
    For combobox elements, types the value and picks the first matching option.
    """
    try:
        tag  = await element.evaluate("el => el.tagName.toLowerCase()")
        role = await element.evaluate("el => (el.getAttribute('role') || '').toLowerCase()")

        if tag == "textarea":      # if that is textarea thats means input will be fill
            await element.click()
            await element.fill(value)
            print("   [OK] Textarea filled")
            return True

        if role == "combobox":
            await element.click()
            await _wait(page, T_SHORT)
            await element.fill("")
            await element.type(value, delay=30)
            print("   [OK] Combobox typed: {!r}".format(value))
            try:
                opt = page.locator('[role="option"]').first
                await opt.wait_for(state="visible", timeout=T_OPTION_LOAD)
                await opt.click()
                print("   [OK] First option selected")
            except Exception:
                pass
            return True

        await element.click()
        await element.fill(value)
        print("   [OK] Filled: {!r}".format(value))
        return True

    except Exception as e:
        print("   [ERR] Type: {}".format(e))
        return False


# ── Select ───────────────────────────────────────────────────

async def do_select(page, element, value):
    """Select an option in a native <select> element by value or label."""
    for kwargs in [{"value": value}, {"label": value}]:
        try:
            await element.select_option(**kwargs)
            print("   [OK] Select: {!r}".format(value))
            return True
        except Exception:
            pass
    print("   [ERR] Select failed: {!r}".format(value))
    return False


# ── MUI Select (div[role=combobox] → listbox) ────────────────

async def mui_select(page, label_text, target_value):
    """
    Interact with a Material UI <Select> dropdown (div[role=combobox]).

    Finds the dropdown by walking up from its <label>, opens the listbox,
    reads all options in one JS call, then clicks the target option.

    Args:
        label_text   — visible label text of the dropdown field
        target_value — exact option to select, or None to pick randomly

    Returns:
        The text of the selected option, or None on failure.
    """
    mode = "RANDOM" if target_value is None else "'{}'".format(target_value)
    print("   [SEL] {} -> {}".format(label_text, mode))

    try:
        info = await page.evaluate("""([lbl]) => {
            const norm = s => s.replace(/[\u00a0\u2009\u202f*]/g,'').trim().toLowerCase();
            const nlbl = norm(lbl);
            for (const label of document.querySelectorAll('label')) {
                if (!norm(label.textContent).includes(nlbl)) continue;
                let el = label;
                for (let i = 0; i < 8; i++) {
                    el = el.parentElement;
                    if (!el) break;
                    const div = el.querySelector('.MuiSelect-select');
                    if (div) {
                        const all = Array.from(document.querySelectorAll('.MuiSelect-select'));
                        return { found: true, idx: all.indexOf(div), current: div.textContent.trim() };
                    }
                }
            }
            return { found: false };
        }""", [label_text])

        if not info.get("found"):
            print("   [ERR] {}: MuiSelect div not found".format(label_text))
            return None

        idx = info["idx"]
        print("     div_idx={}  current='{}'".format(idx, info.get("current")))

        div = page.locator(".MuiSelect-select").nth(idx)
        await div.scroll_into_view_if_needed(timeout=2000)
        await div.click(timeout=3000)

        listbox = page.locator('[role="listbox"]')
        try:
            await listbox.wait_for(state="visible", timeout=3000)
        except Exception:
            print("   [WARN] {}: listbox did not appear".format(label_text))
            await page.keyboard.press("Escape")
            return None

        # Read all option texts in a single JS round-trip
        all_opts_raw = await page.evaluate("""() => {
            const items = document.querySelectorAll('[role="listbox"] [role="option"], [role="listbox"] li');
            return Array.from(items).map(el => el.textContent.trim());
        }""")

        all_opts = [(i, t) for i, t in enumerate(all_opts_raw) if t]
        if not all_opts:
            await page.keyboard.press("Escape")
            return None

        print("     options: {}".format([t for _, t in all_opts]))

        chosen_i, chosen_text = -1, ""

        if target_value is None:
            chosen_i, chosen_text = random.choice(all_opts)
            print("     [RAND] -> '{}'".format(chosen_text))
        else:
            tgt = target_value.lower().strip()
            # Exact match first, then partial match, then random fallback
            for i, t in all_opts:
                if t.lower() == tgt:
                    chosen_i, chosen_text = i, t
                    break
            if chosen_i == -1:
                for i, t in all_opts:
                    if tgt in t.lower():
                        chosen_i, chosen_text = i, t
                        break
            if chosen_i == -1:
                chosen_i, chosen_text = random.choice(all_opts)
                print("   [WARN] '{}' not found — using random: '{}'".format(
                    target_value, chosen_text))

        opts = page.locator('[role="listbox"] [role="option"], [role="listbox"] li')
        await opts.nth(chosen_i).click(timeout=2000)
        print("   [OK] {}: '{}'".format(label_text, chosen_text))
        await _wait(page, T_SHORT)
        return chosen_text

    except Exception as e:
        print("   [ERR] {}: {}".format(label_text, e))
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        return None


# ── MUI Autocomplete (input[role=combobox] → dropdown) ───────

async def mui_autocomplete(page, label, search_q, selector=None):
    """
    Interact with a Material UI Autocomplete field (input[role=combobox]).

    Strategy:
      1. If a selector is provided, use it directly.
      2. Otherwise, walk up from the <label> element via JS to find the input.
      3. Fall back to the last visible combobox input on the page.

    Then:
      Mode A — if search_q is given: type it and pick the first result.
      Mode B — if no search_q: click to open all options, then pick randomly.
    """
    print("   [AC] {}: locating input field...".format(label))
    inp = None

    # Strategy 1: use the provided selector
    if selector:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0:
                inp = loc
        except Exception:
            pass

    # Strategy 2: walk up from the label via JS
    if not inp:
        sel_js = await page.evaluate("""([lbl]) => {
            const norm = s => s.replace(/[\u00a0\u2009\u202f*]/g,'').trim().toLowerCase();
            const nlbl = norm(lbl);
            for (const label of document.querySelectorAll('label')) {
                if (!norm(label.textContent).includes(nlbl)) continue;
                if (label.htmlFor) {
                    const el = document.getElementById(label.htmlFor);
                    if (el && (el.getAttribute('role') === 'combobox' ||
                               el.classList.contains('MuiAutocomplete-input'))) {
                        return '#' + CSS.escape(el.id);
                    }
                }
                let el = label;
                for (let i = 0; i < 8; i++) {
                    el = el.parentElement;
                    if (!el) break;
                    const inp = el.querySelector('input[role="combobox"], input.MuiAutocomplete-input');
                    if (inp) {
                        if (inp.id) return '#' + CSS.escape(inp.id);
                        const all = Array.from(document.querySelectorAll('input[role="combobox"]:not([disabled])'));
                        return '__nth__' + all.indexOf(inp);
                    }
                }
            }
            return null;
        }""", [label])

        if sel_js:
            if sel_js.startswith("__nth__"):
                nth = int(sel_js.replace("__nth__", ""))
                loc = page.locator("input[role='combobox']:not([disabled])").nth(nth)
            else:
                loc = page.locator(sel_js).first
            try:
                if await loc.count() > 0:
                    inp = loc
            except Exception:
                pass

    # Strategy 3: fall back to the last visible combobox on the page
    if not inp:
        try:
            all_inputs = page.locator("input[role='combobox']:not([disabled])")
            cnt = await all_inputs.count()
            if cnt > 0:
                inp = all_inputs.nth(cnt - 1)
        except Exception:
            pass

    if not inp:
        print("   [ERR] {}: input field not found — skipping".format(label))
        return

    try:
        await inp.scroll_into_view_if_needed(timeout=2000)

        # Mode A: type a search query and pick the first result
        if search_q:
            await inp.click(timeout=2000)
            await _wait(page, T_SHORT)
            await inp.fill("")
            await inp.type(search_q, delay=30)
            opt = page.locator('[role="option"]').first
            try:
                await opt.wait_for(state="visible", timeout=T_OPTION_LOAD)
                txt = await opt.inner_text()
                await opt.click(timeout=2000)
                print("   [OK] {} (search): '{}'".format(label, txt))
                await _wait(page, T_SHORT)
                return
            except Exception:
                print("   [WARN] {}: no results for '{}' — trying open-on-focus".format(
                    label, search_q))
                await inp.fill("")
                await _wait(page, T_SHORT)

        # Mode B: click to open all options, then pick one randomly
        await inp.click(timeout=2000)
        opt = page.locator('[role="option"]').first
        try:
            await opt.wait_for(state="visible", timeout=2000)
        except Exception:
            await inp.press("ArrowDown")
            try:
                await opt.wait_for(state="visible", timeout=2000)
            except Exception:
                print("   [ERR] {}: no options appeared — skipping".format(label))
                await page.keyboard.press("Escape")
                return

        all_opts_loc = page.locator('[role="option"]')
        cnt = await all_opts_loc.count()
        if cnt > 0:
            idx = random.randint(0, cnt - 1)
            txt = await all_opts_loc.nth(idx).inner_text()
            await all_opts_loc.nth(idx).click(timeout=2000)
            print("   [OK] {} (open-on-focus [{}/{}]): '{}'".format(label, idx, cnt, txt))
        else:
            await page.keyboard.press("Escape")

        await _wait(page, T_SHORT)

    except Exception as e:
        print("   [ERR] {}: {}".format(label, e))
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass