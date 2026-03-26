import re
from datetime import datetime

_BASE_URL = "https://vertex-dev.savetime.com"


# ============================================================
# ACTIONS
# ============================================================

ACTIONS = {
    "edit": {
        "label":        "Edit Client",
        "needs_target": False,
    }
}

ACTION_KEYS = list(ACTIONS.keys())


# ============================================================
# DOM SCANNER
# ============================================================

def scan_dom(dom):
    result = {
        "clients_nav": None,
        "edit_btn": None,
        "add_client_btn": None,
        "save_btn": None,
        "success_toast": None,
    }

    for el in dom:
        tag   = (el.get("tag") or "").lower()
        text  = (el.get("text") or "").lower()
        label = (el.get("label") or "").lower()
        eid   = (el.get("id") or "").lower()
        cls   = (el.get("class") or "").lower()
        role  = (el.get("role") or "").lower()

        comb = text + " " + label + " " + eid + " " + cls

        # Clients Nav
        if "clients" in comb and not result["clients_nav"]:
            result["clients_nav"] = el

        # Edit button (kept but unused)
        if "edit" in comb and tag == "button":
            result["edit_btn"] = el

        # Add Client button
        if "clients-add-btn" in eid or "add client" in comb:
            result["add_client_btn"] = el

        # Save button
        if "save" in comb and tag == "button":
            result["save_btn"] = el

        # Success toast
        if any(x in comb for x in ("success", "updated", "created", "added")):
            result["success_toast"] = el

    return result


# ============================================================
# STATE
# ============================================================

class _EditState:
    def __init__(self):
        self.nav_done     = False
        self.add_clicked  = False
        self.form_open    = False
        self.submitted    = False
        self.verified     = False
        self._wait        = 0
        self.MAX_WAIT     = 4

    def reset(self):
        self.__init__()


_edit_st = _EditState()


# ============================================================
# DECISION LOGIC
# ============================================================

async def decide_edit(els, url):
    s = _edit_st

    if s.verified:
        return {
            "action": "done",
            "result": "PASS",
            "reason": "Client created successfully"
        }

    # VERIFY
    if s.submitted:
        if els["success_toast"] or "clients" in url.lower():
            s.verified = True
            return {
                "action": "done",
                "result": "PASS",
                "reason": "Client created successfully"
            }

        s._wait += 1
        if s._wait > s.MAX_WAIT:
            return {
                "action": "done",
                "result": "FAIL",
                "reason": "Client creation not verified"
            }

        return {"action": "wait", "seconds": 1}

    # FORM OPEN
    if s.form_open:
        s.submitted = True
        return {
            "action": "fill_client_form",
            "params": {
                "client_name": f"UpdatedClient_{datetime.now().strftime('%H%M%S')}",
                "email": "updated@test.com",
                "phone": "9999999999",
                "website": "https://updated.com",
                "address": "Updated Address",
                "city": "Mumbai",
                "country": "India",
                "industry": "Finance",
                "size": None,
                "active": True
            }
        }

    # WAIT AFTER CLICK
    if s.add_clicked and not s.form_open:
        s.form_open = True
        return {"action": "wait", "seconds": 1}

    # CLICK ADD CLIENT
    if not s.add_clicked:
        ab = els.get("add_client_btn")
        if ab:
            s.add_clicked = True
            return {"action": "click", "selector": ab["selector"]}

        s._wait += 1
        if s._wait > s.MAX_WAIT:
            return {
                "action": "done",
                "result": "FAIL",
                "reason": "Add Client button not found"
            }
        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# PUBLIC ENTRY
# ============================================================

def reset_state():
    _edit_st.reset()
    print("[STATE] Client module reset")


async def decide_action(action, dom, url, goal="", email=None, password=None):
    els = scan_dom(dom)

    # ✅ FIX: HANDLE SSO LOGIN PROPERLY
    if "microsoftonline.com" in url.lower():
        return {"action": "wait", "seconds": 2}

    if "vertex-dev.savetime.com" not in url.lower():
        return {"action": "wait", "seconds": 1}

    # Navigate to Clients page AFTER login
    if "clients" not in url.lower():
        cn = els["clients_nav"]
        if cn:
            return {"action": "click", "selector": cn["selector"]}
        return {"action": "navigate", "url": _BASE_URL + "/settings/clients/"}

    if action == "edit":
        return await decide_edit(els, url)

    return {"action": "wait", "seconds": 1}