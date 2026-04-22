from datetime import datetime

from utils.login       import login_done, handle_login, reset_login
from utils.nav         import nav_done,   handle_nav,   reset_nav
from utils.dom_scanner import scan_common_dom
from config.settings   import BASE_URL
from report.test_report import get_reporter

# ============================================================
# modules/client.py
#
# Workflow:
#   Login -> /settings/clients -> Add Client -> fill form -> Save
# ============================================================

NAV_FRAGMENT = "settings/clients"

MODULE_META = {
    "name":     "Clients",
    "fragment": NAV_FRAGMENT,
    "order":    5,
}

ACTIONS = {
    "add": {
        "label":        "Add Client",
        "needs_target": False,
    },
}

ACTION_KEYS = list(ACTIONS.keys())


# ============================================================
# DOM SCANNER
# ============================================================

def scan_dom(dom):
    result = scan_common_dom(dom)
    result.update({
        "add_client_btn": None,
        "save_btn":       None,
        "dialog_open":    False,
    })

    for el in dom:
        tag   = (el.get("tag")   or "").lower()
        eid   = (el.get("id")    or "").lower()
        text  = (el.get("text")  or "").lower()
        label = (el.get("label") or "").lower()
        cls   = (el.get("class") or "").lower()
        comb  = text + " " + label + " " + eid + " " + cls

        if eid == "clients-add-btn":
            result["add_client_btn"] = el

        if tag == "button" and "save" in comb and not result["save_btn"]:
            result["save_btn"] = el

        if "add new client" in comb:
            result["dialog_open"] = True

    return result


# ============================================================
# ADD CLIENT STATE
# ============================================================

class _AddClientState:
    def __init__(self):
        self.add_clicked = False
        self.form_open   = False
        self.submitted   = False
        self.verified    = False
        self._wait       = 0
        self.MAX_WAIT    = 4

    def reset(self):
        self.__init__()


_add = _AddClientState()


# ============================================================
# ADD CLIENT LOGIC
# ============================================================

async def _decide_add(els, url):
    s = _add
    r = get_reporter()

    if s.verified:
        if r:
            r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Client added successfully"}

    if s.submitted:
        if not els["dialog_open"]:
            s.verified = True
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "Client added successfully"}

        s._wait += 1
        if s._wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False,
                    error="Dialog still open after save — client may not have been created")
            return {"action": "done", "result": "FAIL",
                    "reason": "Client save was not confirmed — dialog did not close"}
        return {"action": "wait", "seconds": 1}

    if s.form_open:
        s.submitted = True
        step = {
            "action": "fill_client_form",
            "params": {
                "client_name": "Client_{}".format(datetime.now().strftime("%H%M%S")),
                "email":    "test@test.com",
                "phone":    "9999999999",
                "website":  "https://test.com",
                "address":  "Test Address",
                "city":     "Mumbai",
                "country":  "India",
                "industry": "Finance",
                "size":     None,
                "active":   True,
            },
        }
        if r:
            r.log_step(len(r.steps) + 1, step, url)
        return step

    if not s.add_clicked:
        btn = els["add_client_btn"]
        if btn:
            s.add_clicked = True
            step = {"action": "click", "selector": btn["selector"]}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step
        return {"action": "wait", "seconds": 1}

    if s.add_clicked and not s.form_open:
        if els["dialog_open"]:
            s.form_open = True
            return {"action": "wait", "seconds": 1}
        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

def reset_state(keep_session=False):
    reset_login()
    reset_nav()
    _add.reset()
    print("[STATE] Client module reset")


async def decide_action(action, dom, url, goal="", email=None, password=None, page=None):
    els = scan_dom(dom)

    if not login_done():
        step = handle_login(els, email, password, url)
        if step is None and not login_done():
            return {"action": "wait", "seconds": 1}
        if step:
            r = get_reporter()
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step

    if not nav_done():
        step = handle_nav(els, url, NAV_FRAGMENT)
        if step:
            r = get_reporter()
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step

    if action == "add":
        return await _decide_add(els, url)

    return {"action": "wait", "seconds": 1}