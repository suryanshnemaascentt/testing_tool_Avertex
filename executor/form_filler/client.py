from datetime import datetime
from config.settings import T_SHORT, T_SAVE
from report.test_report import get_reporter
from ._shared import _wait

# ============================================================
# executor/form_filler/client.py — Client form fill logic.
# ============================================================

# ── Report integration metadata ──────────────────────────────
FORM_ACTION_NAME        = "fill_client_form"
FORM_MODULE             = None
FORM_ACTION_VERB        = "Filled Client Form"
FORM_DESCRIPTION_PARAMS = [("client_name", "name")]
FORM_SUB_STEPS = [
    ("client_name", "Client Name", None),
    ("email",       "Email",       None),
    ("phone",       "Phone",       None),
    ("website",     "Website",     None),
    ("address",     "Address",     None),
    ("city",        "City",        None),
    ("country",     "Country",     None),
    ("industry",    "Industry",    None),
    (None,          "Save Button", None),
]


async def fill_client_form(page, p):
    """
    Fill and submit the Add New Client dialog.

    Params expected in p:
        client_name, email, phone, website, address,
        city, country, industry, size (optional), active (bool)
    """
    client_name = p.get("client_name", "Client_{}".format(datetime.now().strftime("%H%M%S")))
    email       = p.get("email",    "test@test.com")
    phone       = p.get("phone",    "9999999999")
    website     = p.get("website",  "https://test.com")
    address     = p.get("address",  "Test Address")
    city        = p.get("city",     "Mumbai")
    country     = p.get("country",  "India")
    industry    = p.get("industry", "Finance")

    print("\n[CLIENT FORM] name='{}' email={} phone={}".format(
        client_name, email, phone))

    r = get_reporter()

    # ── Client Name ───────────────────────────────────────────
    try:
        inp = page.locator(
            "input[placeholder*='client name' i], "
            "input[placeholder*='name' i], "
            "input[id*='client-name' i]"
        ).first
        if await inp.count() == 0:
            inp = page.locator("input[type='text']").first
        await inp.fill(client_name)
        await _wait(page, T_SHORT)
        if r:
            r.log_sub_step(1, "Client Name", client_name, True)
        print("[CLIENT FORM] 1. Client name: '{}'".format(client_name))
    except Exception as e:
        if r:
            r.log_sub_step(1, "Client Name", client_name, False, str(e))
        print("[CLIENT FORM] ! Client name failed: {}".format(e))

    # ── Email ─────────────────────────────────────────────────
    try:
        inp = page.locator(
            "input[type='email'], "
            "input[placeholder*='email' i], "
            "input[id*='email' i]"
        ).first
        if await inp.count() > 0:
            await inp.fill(email)
            await _wait(page, T_SHORT)
            if r:
                r.log_sub_step(2, "Email", email, True)
            print("[CLIENT FORM] 2. Email: '{}'".format(email))
    except Exception as e:
        if r:
            r.log_sub_step(2, "Email", email, False, str(e))
        print("[CLIENT FORM] ! Email failed: {}".format(e))

    # ── Phone ─────────────────────────────────────────────────
    try:
        inp = page.locator(
            "input[type='tel'], "
            "input[placeholder*='phone' i], "
            "input[id*='phone' i]"
        ).first
        if await inp.count() > 0:
            await inp.fill(phone)
            await _wait(page, T_SHORT)
            if r:
                r.log_sub_step(3, "Phone", phone, True)
            print("[CLIENT FORM] 3. Phone: '{}'".format(phone))
    except Exception as e:
        if r:
            r.log_sub_step(3, "Phone", phone, False, str(e))
        print("[CLIENT FORM] ! Phone failed: {}".format(e))

    # ── Website ───────────────────────────────────────────────
    try:
        inp = page.locator(
            "input[type='url'], "
            "input[placeholder*='website' i], "
            "input[id*='website' i]"
        ).first
        if await inp.count() > 0:
            await inp.fill(website)
            await _wait(page, T_SHORT)
            if r:
                r.log_sub_step(4, "Website", website, True)
            print("[CLIENT FORM] 4. Website: '{}'".format(website))
    except Exception as e:
        if r:
            r.log_sub_step(4, "Website", website, False, str(e))
        print("[CLIENT FORM] ! Website failed: {}".format(e))

    # ── Address ───────────────────────────────────────────────
    try:
        inp = page.locator(
            "textarea[placeholder*='address' i], "
            "input[placeholder*='address' i], "
            "input[id*='address' i]"
        ).first
        if await inp.count() > 0:
            await inp.fill(address)
            await _wait(page, T_SHORT)
            if r:
                r.log_sub_step(5, "Address", address, True)
            print("[CLIENT FORM] 5. Address: '{}'".format(address))
    except Exception as e:
        if r:
            r.log_sub_step(5, "Address", address, False, str(e))
        print("[CLIENT FORM] ! Address failed: {}".format(e))

    # ── City ──────────────────────────────────────────────────
    try:
        inp = page.locator(
            "input[placeholder*='city' i], "
            "input[id*='city' i]"
        ).first
        if await inp.count() > 0:
            await inp.fill(city)
            await _wait(page, T_SHORT)
            if r:
                r.log_sub_step(6, "City", city, True)
            print("[CLIENT FORM] 6. City: '{}'".format(city))
    except Exception as e:
        if r:
            r.log_sub_step(6, "City", city, False, str(e))
        print("[CLIENT FORM] ! City failed: {}".format(e))

    # ── Country ───────────────────────────────────────────────
    try:
        inp = page.locator(
            "input[placeholder*='country' i], "
            "input[id*='country' i]"
        ).first
        if await inp.count() > 0:
            await inp.fill(country)
            await _wait(page, T_SHORT)
            if r:
                r.log_sub_step(7, "Country", country, True)
            print("[CLIENT FORM] 7. Country: '{}'".format(country))
    except Exception as e:
        if r:
            r.log_sub_step(7, "Country", country, False, str(e))
        print("[CLIENT FORM] ! Country failed: {}".format(e))

    # ── Industry ──────────────────────────────────────────────
    try:
        inp = page.locator(
            "input[placeholder*='industry' i], "
            "input[id*='industry' i]"
        ).first
        if await inp.count() > 0:
            await inp.fill(industry)
            await _wait(page, T_SHORT)
            if r:
                r.log_sub_step(8, "Industry", industry, True)
            print("[CLIENT FORM] 8. Industry: '{}'".format(industry))
    except Exception as e:
        if r:
            r.log_sub_step(8, "Industry", industry, False, str(e))
        print("[CLIENT FORM] ! Industry failed: {}".format(e))

    # ── Save ──────────────────────────────────────────────────
    try:
        save_btn = page.locator(
            "button[id*='save' i], "
            "button:has-text('Save'), "
            "button[type='submit']"
        ).first
        await save_btn.click()
        await _wait(page, T_SAVE)
        if r:
            r.log_sub_step(9, "Save Button", "", True)
        print("[CLIENT FORM] 9. Save clicked")
    except Exception as e:
        if r:
            r.log_sub_step(9, "Save Button", "", False, str(e))
        print("[CLIENT FORM] ! Save failed: {}".format(e))
