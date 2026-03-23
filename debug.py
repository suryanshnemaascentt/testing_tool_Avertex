"""
Run after Jobs tab is open — prints exact DOM of job form row.
Usage: python debug_job_form.py
"""
import asyncio
from playwright.async_api import async_playwright

URL   = "https://vertex-dev.savetime.com"
EMAIL = "suryansh.nema@ascentt.com"
PASS  = "Sn94948988@"

async def main():
    project = input("Project name: ").strip()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page    = await browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

        # Login
        await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        try:
            await page.fill("#i0116", EMAIL)
            await page.click("#idSIButton9")
            await page.wait_for_timeout(2000)
        except Exception: pass
        try:
            await page.fill("#i0118", PASS)
            await page.click("#idSIButton9")
            await page.wait_for_timeout(2000)
        except Exception: pass
        try:
            await page.click("#idSIButton9")
            await page.wait_for_timeout(3000)
        except Exception: pass

        # Navigate → search → view → jobs tab → add job
        await page.goto(URL + "/projects", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.locator("input[placeholder*='earch' i]").first.fill(project)
        await page.wait_for_timeout(1500)
        await page.locator("button:has-text('View')").first.click()
        await page.wait_for_timeout(2000)
        await page.locator("#project-jobs-tab").click()
        await page.wait_for_timeout(1500)
        await page.locator("button:has-text('Add Job')").first.click()
        await page.wait_for_timeout(1500)
        print("[OK] Add Job clicked — form row should be visible")

        # ── Print ALL inputs ───────────────────────────────────
        print("\n" + "="*60)
        print("ALL INPUTS IN FORM ROW")
        print("="*60)
        inputs = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input'))
                .filter(el => {
                    const s = window.getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden';
                })
                .map(el => ({
                    id:          el.id || '',
                    type:        el.getAttribute('type') || 'text',
                    placeholder: el.getAttribute('placeholder') || '',
                    value:       el.value || '',
                    cls:         (el.className || '').slice(0, 80),
                    name:        el.getAttribute('name') || '',
                    min:         el.getAttribute('min') || '',
                    disabled:    el.disabled,
                }));
        }""")
        for i in inputs:
            print("  id={id:15} type={type:8} placeholder={placeholder:35} disabled={disabled}".format(**i))

        # ── Print ALL buttons ──────────────────────────────────
        print("\n" + "="*60)
        print("ALL BUTTONS")
        print("="*60)
        buttons = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button'))
                .filter(b => {
                    const s = window.getComputedStyle(b);
                    return s.display !== 'none' && s.visibility !== 'hidden';
                })
                .map((b, i) => ({
                    idx:      i,
                    text:     (b.innerText || '').trim().replace(/\\n/g,' ').slice(0,40),
                    id:       b.id || '',
                    cls:      (b.className || '').slice(0, 100),
                    disabled: b.disabled,
                    tabindex: b.getAttribute('tabindex') || '',
                    ariaLabel: b.getAttribute('aria-label') || '',
                }));
        }""")
        for b in buttons:
            tick = " *** SAVE/TICK?" if (
                not b["disabled"] and
                b["tabindex"] != "-1" and
                not b["text"] and
                "icon" in b["cls"].lower()
            ) else ""
            print("  [{idx}] text={text!r:25} disabled={disabled} tabindex={tabindex} cls={cls:.60}{t}".format(**b, t=tick))

        # ── Try filling job name ───────────────────────────────
        print("\n" + "="*60)
        print("TRYING TO FILL JOB NAME")
        print("="*60)
        strategies = [
            "input[placeholder*='Discovery' i]",
            "input[placeholder*='e.g.' i]",
            "input[placeholder*='Development' i]",
            "input.MuiInputBase-inputSizeSmall[type='text']",
            "tr input[type='text']",
            "input[type='text']",
        ]
        for sel in strategies:
            try:
                loc = page.locator(sel).first
                cnt = await loc.count()
                if cnt > 0:
                    await loc.click(click_count=3)
                    await loc.fill("TEST_JOB_NAME")
                    val = await loc.input_value()
                    print("  [OK] selector={!r} -> filled: {!r}".format(sel, val))
                    await loc.fill("")
                    break
                else:
                    print("  [MISS] selector={!r} -> 0 elements".format(sel))
            except Exception as e:
                print("  [ERR] selector={!r} -> {}".format(sel, e))

        print("\n[INFO] Browser open 30s")
        await page.wait_for_timeout(30000)
        await browser.close()

asyncio.run(main())