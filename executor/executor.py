from __future__ import annotations
import random
from datetime import datetime, timedelta
from typing import Optional


# =========================================================
# TIMING CONSTANTS (ms)
# =========================================================

_T_SHORT       =  80
_T_MEDIUM      = 200
_T_OPTION_LOAD = 600
_T_SAVE        = 1500
_T_NAV         =  800
_T_KEY         =  150


async def _wait(page, ms: int):
    await page.wait_for_timeout(ms)


# =========================================================
# STEP DISPATCHER
# =========================================================

async def execute_step(page, dom, step: dict) -> bool:
    action   = step.get("action")
    selector = step.get("selector")
    value    = step.get("text") or step.get("value")

    try:
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
            await _wait(page, _T_KEY)
            return True

        if action == "navigate":
            url = step.get("url", "")
            if url:
                print(f"[NAV] Navigate -> {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await _wait(page, _T_NAV)
            return True

        if action == "done":
            r    = step.get("result", "UNKNOWN")
            icon = "[PASS]" if r == "PASS" else ("[FAIL]" if r == "FAIL" else "[?]")
            print(f"{icon} DONE: {r} -- {step.get('reason', '')}")
            return True

        if action == "autocomplete_pick_first":
            try:
                opt = page.locator('[role="option"]').first
                await opt.wait_for(state="visible", timeout=2000)
                txt = await opt.inner_text()
                await opt.click(timeout=2000)
                print(f"   [OK] picked: '{txt}'")
            except Exception:
                await page.keyboard.press("Escape")
            return True

        if action == "fill_form":
            return await _fill_form(page, step.get("params", {}))
        
        elif action == "fill_client_form":
            return await _fill_client_form(page, step.get("params", {}))

        # ── Selector-required actions ──────────────────────
        if not selector:
            print("[ERR] No selector")
            return False

        print(f"\n[?] {action} -> {selector}")
        loc   = page.locator(selector)
        count = await loc.count()
        print(f"   Found {count} element(s)")
        if count == 0:
            print("[ERR] Not found -- skip")
            return False

        el = loc.first
        try:
            await el.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass

        if action == "click":
            soft = step.get("soft_fail", False) or step.get("sso_yes", False)
            return await _click(page, el, soft_fail=soft)
        elif action == "type":
            return await _type_into(page, el, value or "")
        elif action == "select":
            return await _select(page, el, value or "")
        else:
            print(f"[ERR] Unknown action: {action}")
            return False

    except Exception as e:
        print(f"[ERR] Executor error: {e}")
        import traceback
        traceback.print_exc()
        return False
# ===============================
# SELECT FIRST OPTION (Dropdown)
# ===============================
    if action["action"] == "select_first_option":
        print("[?] Selecting first dropdown option")

        options = page.locator('[role="option"]')

        count = await options.count()
        print(f"   Found {count} option(s)")

        if count > 0:
            await options.first.click()
            print("   [OK] First option selected")
        else:
            print("   [WARN] No options found")

        return

# =========================================================
# FILL FORM
# =========================================================

async def _fill_form(page, p: dict) -> bool:
    name        = p.get("project_name", f"AutoProject_{datetime.now().strftime('%H%M%S')}")
    description = p.get("description",  "Auto-generated.")
    start_date  = p.get("start_date")  or datetime.now().strftime("%m/%d/%Y")
    end_date    = p.get("end_date")    or (datetime.now() + timedelta(days=30)).strftime("%m/%d/%Y")
    budget      = p.get("budget",       "10000")

    print(f"\n{'='*55}")
    print(f"[FORM] FILL_FORM: {name}")
    print(f"   {start_date} -> {end_date}  budget={budget}")
    print(f"{'='*55}")

    # ── 1. Project Name ────────────────────────────────────
    # NOTE: sequential -- both locators hit .first on the same page,
    #       running them with asyncio.gather causes a race condition.
    await _set_text_input(page, name)

    # ── 2. Description ────────────────────────────────────
    await _set_textarea(page, description)

    # ── 3. MUI Select dropdowns ───────────────────────────
    # Sequential because Billing Type gates Client visibility.
    await _mui_select(page, "Project Type",   p.get("project_type"))
    await _mui_select(page, "Delivery Model", p.get("delivery_model"))
    await _mui_select(page, "Methodology",    p.get("methodology"))
    await _mui_select(page, "Risk Rating",    p.get("risk_rating"))

    chosen_billing = await _mui_select(page, "Billing Type", p.get("billing_type"))
    await _wait(page, _T_SHORT)

    await _mui_select(page, "Currency", p.get("currency"))

    # ── 4. Client autocomplete ────────────────────────────
    is_billable = (chosen_billing or "").lower().strip() == "billable"
    if is_billable or chosen_billing is None:
        await _mui_autocomplete(
            page,
            label    = "Client",
            search_q = p.get("client_search", "a"),
            selector = p.get("client_selector"),
        )
    else:
        print(f"   [INFO] Client skipped (billing='{chosen_billing}')")

    # ── 5. Link to Estimation ─────────────────────────────
    est_search = p.get("estimation_search") or "a"
    est_sel    = p.get("estimation_selector")
    print(f"   [LINK] Estimation: search='{est_search}' selector={est_sel}")
    await _mui_autocomplete(
        page,
        label    = "Link to Estimation",
        search_q = est_search,
        selector = est_sel,
    )

    # ── 6. Start Date ─────────────────────────────────────
    # FIX: date pickers are run SEQUENTIALLY.
    # asyncio.gather on _set_date() caused both pickers to share
    # the same page keyboard simultaneously, corrupting both dates.
    await _set_date(page, 0, start_date, "Start Date")

    # ── 7. End Date ───────────────────────────────────────
    await _set_date(page, 1, end_date, "End Date")

    # ── 8. Budget ─────────────────────────────────────────
    await _set_budget(page, budget)

    # ── 9. Save ───────────────────────────────────────────
    return await _save(page)


# =========================================================
# MUI SELECT  (div[role=combobox] → listbox)
# =========================================================

async def _mui_select(page, label_text: str, target_value: Optional[str]) -> Optional[str]:
    mode = "RANDOM" if target_value is None else f"'{target_value}'"
    print(f"   [SEL] {label_text} -> {mode}")

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
                        const allDivs = Array.from(document.querySelectorAll('.MuiSelect-select'));
                        return {
                            found:   true,
                            idx:     allDivs.indexOf(div),
                            current: div.textContent.trim()
                        };
                    }
                }
            }
            return { found: false };
        }""", [label_text])

        if not info.get("found"):
            print(f"   [ERR] {label_text}: MuiSelect div not found")
            return None

        idx = info["idx"]
        print(f"     div_idx={idx}  current='{info.get('current')}'")

        div = page.locator(".MuiSelect-select").nth(idx)
        await div.scroll_into_view_if_needed(timeout=2000)
        await div.click(timeout=3000)

        listbox = page.locator('[role="listbox"]')
        try:
            await listbox.wait_for(state="visible", timeout=3000)
        except Exception:
            print(f"   [WARN] {label_text}: listbox not visible -- Escape")
            await page.keyboard.press("Escape")
            return None

        # Batch-read all option texts in ONE JS call (O(1) round-trips)
        all_opts_raw = await page.evaluate("""() => {
            const items = document.querySelectorAll(
                '[role="listbox"] [role="option"], [role="listbox"] li'
            );
            return Array.from(items).map(el => el.textContent.trim());
        }""")

        all_opts = [(i, t) for i, t in enumerate(all_opts_raw) if t]
        if not all_opts:
            await page.keyboard.press("Escape")
            return None

        print(f"     options: {[t for _, t in all_opts]}")

        chosen_i    = -1
        chosen_text = ""

        if target_value is None:
            chosen_i, chosen_text = random.choice(all_opts)
            print(f"     [RAND] -> '{chosen_text}'")
        else:
            tgt = target_value.lower().strip()
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
                print(f"   [WARN] '{target_value}' not found -- random: '{chosen_text}'")

        opts = page.locator('[role="listbox"] [role="option"], [role="listbox"] li')
        await opts.nth(chosen_i).click(timeout=2000)
        print(f"   [OK] {label_text}: '{chosen_text}'")
        await _wait(page, _T_SHORT)
        return chosen_text

    except Exception as e:
        print(f"   [ERR] {label_text}: {e}")
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        return None


# =========================================================
# MUI AUTOCOMPLETE  (input[role=combobox] → dropdown)
# =========================================================

async def _mui_autocomplete(
    page,
    label:    str,
    search_q: str,
    selector: Optional[str] = None,
):
    print(f"   [AC] {label}: finding input field...")
    inp = None

    # Strategy 1: passed selector
    if selector:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0:
                inp = loc
                print(f"   [OK] {label}: selector -> {selector}")
        except Exception:
            pass

    # Strategy 2: JS label walk
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
                    const inp = el.querySelector(
                        'input[role="combobox"], input.MuiAutocomplete-input'
                    );
                    if (inp) {
                        if (inp.id) return '#' + CSS.escape(inp.id);
                        const all = Array.from(
                            document.querySelectorAll('input[role="combobox"]:not([disabled])')
                        );
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
                    print(f"   [OK] {label}: JS label -> {sel_js}")
            except Exception:
                pass

    # Strategy 3: last combobox fallback
    if not inp:
        try:
            all_inputs = page.locator("input[role='combobox']:not([disabled])")
            cnt = await all_inputs.count()
            if cnt > 0:
                inp = all_inputs.nth(cnt - 1)
                print(f"   [OK] {label}: last combobox fallback (nth={cnt-1})")
        except Exception:
            pass

    if not inp:
        print(f"   [ERR] {label}: input not found -- skipping")
        return

    try:
        await inp.scroll_into_view_if_needed(timeout=2000)

        # MODE A: Search-based (type -> wait -> pick first)
        if search_q:
            await inp.click(timeout=2000)
            await _wait(page, _T_SHORT)
            await inp.fill("")
            await inp.type(search_q, delay=30)

            opt = page.locator('[role="option"]').first
            try:
                await opt.wait_for(state="visible", timeout=_T_OPTION_LOAD)
                txt = await opt.inner_text()
                await opt.click(timeout=2000)
                print(f"   [OK] {label} (search): '{txt}'")
                await _wait(page, _T_SHORT)
                return
            except Exception:
                print(f"   [WARN] {label}: no results for '{search_q}' -- trying open-on-focus")
                await inp.fill("")
                await _wait(page, _T_SHORT)

        # MODE B: Open-on-focus (click -> all options appear -> pick random)
        print(f"   [CLICK] {label}: clicking to open all options...")
        await inp.click(timeout=2000)

        opt = page.locator('[role="option"]').first
        try:
            await opt.wait_for(state="visible", timeout=2000)
        except Exception:
            await inp.press("ArrowDown")
            try:
                await opt.wait_for(state="visible", timeout=2000)
            except Exception:
                print(f"   [ERR] {label}: no options appeared -- skipping")
                await page.keyboard.press("Escape")
                return

        all_opts_loc = page.locator('[role="option"]')
        cnt = await all_opts_loc.count()
        if cnt > 0:
            idx = random.randint(0, cnt - 1)
            txt = await all_opts_loc.nth(idx).inner_text()
            await all_opts_loc.nth(idx).click(timeout=2000)
            print(f"   [OK] {label} (open-on-focus [{idx}/{cnt}]): '{txt}'")
        else:
            print(f"   [ERR] {label}: 0 options -- skip")
            await page.keyboard.press("Escape")

        await _wait(page, _T_SHORT)

    except Exception as e:
        print(f"   [ERR] {label}: {e}")
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass


# =========================================================
# DATE  --  MuiPickersSectionList spinbuttons
# =========================================================
# FIX: This function is called SEQUENTIALLY from _fill_form
# (once for Start Date, then once for End Date).
#
# Previously asyncio.gather() was used to run both pickers
# at the same time. Because both rely on page.keyboard.type()
# (a single shared resource), the keystrokes from picker-0
# and picker-1 interleaved, corrupting both date values.
#
# The fix: just call _set_date twice in sequence -- the
# overhead is trivial compared to the MUI animation time.
# =========================================================

async def _set_date(page, picker_idx: int, date_val: str, desc: str):
    # ── Parse date string ─────────────────────────────────
    try:
        parts = date_val.strip().split("/")
        if len(parts) != 3:
            raise ValueError("need MM/DD/YYYY")
        mm, dd, yyyy = parts[0].zfill(2), parts[1].zfill(2), parts[2].zfill(4)
    except Exception as exc:
        print(f"   [ERR] {desc}: bad format '{date_val}' -- {exc}")
        return

    print(f"   [DATE] {desc}: {mm}/{dd}/{yyyy}")

    pickers = page.locator(".MuiPickersSectionList-root")
    cnt = await pickers.count()
    if picker_idx >= cnt:
        print(f"   [ERR] {desc}: only {cnt} picker(s) found, needed index {picker_idx}")
        return

    picker = pickers.nth(picker_idx)

    async def _fill_segment(aria_lbl: str, digits: str) -> bool:
        """Click the segment span, type the digits, verify the value was accepted."""
        span = picker.locator(f'[aria-label="{aria_lbl}"]')
        if await span.count() == 0:
            print(f"     [WARN] [{aria_lbl}] span not found in picker {picker_idx}")
            return False

        await span.click(timeout=2000)
        await _wait(page, _T_SHORT)

        # Type digit by digit with small delay so MUI spinbutton registers each
        await page.keyboard.type(digits, delay=_T_SHORT)
        await _wait(page, _T_SHORT)

        v  = await span.get_attribute("aria-valuetext")
        ok = v not in (None, "Empty", "")
        print(f"     [{desc}] [{aria_lbl}] typed={digits!r} -> aria-valuetext={v!r} {'[OK]' if ok else '[WARN]'}")
        return ok

    # Fill month, day, year -- retry once each if the segment was not accepted
    ok_m = await _fill_segment("Month", mm)
    ok_d = await _fill_segment("Day",   dd)
    ok_y = await _fill_segment("Year",  yyyy)

    if not ok_m:
        print(f"   [RETRY] {desc}: Month")
        await _fill_segment("Month", mm)
    if not ok_d:
        print(f"   [RETRY] {desc}: Day")
        await _fill_segment("Day", dd)
    if not ok_y:
        print(f"   [RETRY] {desc}: Year")
        await _fill_segment("Year", yyyy)

    # Tab out of the picker to confirm selection
    await page.keyboard.press("Tab")
    await _wait(page, _T_SHORT)


# =========================================================
# TEXT / TEXTAREA / BUDGET
# =========================================================

async def _set_text_input(page, value: str):
    """Fill the Project Name field (first visible MUI text input)."""
    try:
        inp = page.locator("input.MuiInputBase-input[type='text']").first
        await inp.scroll_into_view_if_needed(timeout=2000)
        await inp.click(click_count=3, timeout=2000)  # triple-click selects existing text
        await inp.fill(value)
        print(f"   [OK] Project Name: {value!r}")
    except Exception as e:
        print(f"   [ERR] Project Name: {e}")


async def _set_textarea(page, value: str):
    """Fill the Description textarea (first visible MUI textarea)."""
    try:
        ta = page.locator("textarea.MuiInputBase-input").first
        await ta.scroll_into_view_if_needed(timeout=2000)
        await ta.click(timeout=2000)
        await ta.fill(value)
        print("   [OK] Description: filled")
    except Exception as e:
        print(f"   [ERR] Description: {e}")


async def _set_budget(page, budget: str):
    """Fill the Budget number input."""
    try:
        inp = page.locator("input[type='number'].MuiInputBase-input").first
        await inp.scroll_into_view_if_needed(timeout=2000)
        await inp.click(click_count=3, timeout=2000)
        await inp.fill(budget)
        print(f"   [OK] Budget: {budget!r}")
    except Exception as e:
        print(f"   [ERR] Budget: {e}")
    await _wait(page, _T_SHORT)


# =========================================================
# SAVE
# =========================================================

async def _save(page) -> bool:
    try:
        btn = page.locator("#project-form-save").first
        await btn.scroll_into_view_if_needed(timeout=2000)
        await _wait(page, _T_SHORT)
        await btn.click(timeout=5000)
        print("   [OK] Save Project clicked")
        await _wait(page, _T_SAVE)
        return True
    except Exception as e:
        print(f"   [ERR] Save (by id): {e}")

    try:
        await page.get_by_role("button", name="Save Project").first.click(timeout=3000)
        print("   [OK] Save Project clicked (by role)")
        await _wait(page, _T_SAVE)
        return True
    except Exception as e:
        print(f"   [ERR] Save (by role): {e}")
        return False


# =========================================================
# CLICK
# =========================================================

async def _click(page, element, soft_fail: bool = False) -> bool:
    for kwargs in [{"timeout": 5000}, {"force": True, "timeout": 3000}]:
        try:
            await element.click(**kwargs)
            print("   [OK] Click OK")
            await _wait(page, _T_MEDIUM)
            return True
        except Exception as e:
            print(f"   [WARN] click({list(kwargs.keys())}): {e}")

    try:
        await element.evaluate("el => el.click()")
        print("   [OK] JS click")
        await _wait(page, _T_MEDIUM)
        return True
    except Exception as e:
        print(f"   [ERR] JS click: {e}")

    if soft_fail:
        print("   [WARN] All clicks failed -- soft_fail OK")
        return True
    return False


# =========================================================
# TYPE
# =========================================================

async def _type_into(page, element, value: str) -> bool:
    try:
        tag  = await element.evaluate("el => el.tagName.toLowerCase()")
        role = await element.evaluate("el => (el.getAttribute('role') || '').toLowerCase()")

        if tag == "textarea":
            await element.click()
            await element.fill(value)
            print("   [OK] Textarea filled")
            return True

        if role == "combobox":
            await element.click()
            await _wait(page, _T_SHORT)
            await element.fill("")
            await element.type(value, delay=30)
            print(f"   [OK] Combobox: {value!r}")
            try:
                opt = page.locator('[role="option"]').first
                await opt.wait_for(state="visible", timeout=_T_OPTION_LOAD)
                await opt.click()
                print("   [OK] Option selected")
            except Exception:
                pass
            return True

        await element.click()
        await element.fill(value)
        print(f"   [OK] Filled: {value!r}")
        return True

    except Exception as e:
        print(f"   [ERR] Type: {e}")
        return False


# =========================================================
# SELECT
# =========================================================

async def _select(page, element, value: str) -> bool:
    for kwargs in [{"value": value}, {"label": value}]:
        try:
            await element.select_option(**kwargs)
            print(f"   [OK] Select: {value!r}")
            return True
        except Exception:
            pass
    print(f"   [ERR] Select failed: {value!r}")
    return False
#----------------------------------------------------------------------------------


# =========================================================
# FILL CLIENT FORM
# =========================================================

async def _fill_client_form(page, p: dict) -> bool:
    print(f"\n{'='*55}")
    print("[FORM] EDIT CLIENT")
    print(f"{'='*55}")

    name     = p.get("client_name", f"AutoClient_{datetime.now().strftime('%H%M%S')}")
    email    = p.get("email", "auto@test.com")
    phone    = p.get("phone", "9876543210")
    website  = p.get("website", "https://example.com")
    address  = p.get("address", "Auto Address")
    city     = p.get("city", "Pune")
    country  = p.get("country", "India")
    industry = p.get("industry", "IT")

    # ── Text Inputs (generic MUI handling) ─────────────────

    async def fill_by_label(label, value):
        try:
            sel = await page.evaluate("""([lbl]) => {
                const norm = s => s.toLowerCase().trim();
                for (const label of document.querySelectorAll('label')) {
                    if (norm(label.textContent).includes(norm(lbl))) {
                        if (label.htmlFor) return '#' + label.htmlFor;
                    }
                }
                return null;
            }""", [label])

            if sel:
                inp = page.locator(sel).first
                await inp.click(click_count=3)
                await inp.fill(value)
                print(f"   [OK] {label}: {value}")
            else:
                print(f"   [WARN] {label}: not found")

        except Exception as e:
            print(f"   [ERR] {label}: {e}")

    await fill_by_label("Client Name", name)
    await fill_by_label("Email", email)
    await fill_by_label("Phone", phone)
    await fill_by_label("Website", website)
    await fill_by_label("Address", address)
    await fill_by_label("City", city)
    await fill_by_label("Country", country)
    await fill_by_label("Industry", industry)

    # ── Size Dropdown (MUI Select) ─────────────────────────
    await _mui_select(page, "Size", p.get("size"))

    # ── Active Toggle ──────────────────────────────────────
    try:
        toggle = page.locator("input[role='switch']").first
        desired = p.get("active", True)
        is_checked = await toggle.is_checked()

        if desired != is_checked:
            await toggle.click()
            print(f"   [OK] Active toggled -> {desired}")
        else:
            print(f"   [OK] Active already {desired}")

    except Exception as e:
        print(f"   [WARN] Active toggle: {e}")

    # ── Save ───────────────────────────────────────────────
    try:
        btn = page.get_by_role("button", name="Save").last
        await btn.click()
        print("   [OK] Save Client clicked")
        await page.wait_for_timeout(_T_SAVE)
        return True
    except Exception as e:
        print(f"   [ERR] Save Client: {e}")
        return False