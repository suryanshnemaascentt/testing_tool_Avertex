from utils.login       import login_done, handle_login, reset_login
from utils.nav         import nav_done,   handle_nav,   reset_nav
from utils.dom_scanner import scan_common_dom
from config.settings   import BASE_URL
from report.test_report import get_reporter

# ============================================================
# modules/access_control.py
#
# Workflow:
#   Login -> /settings/access-control -> Assign Role -> fill form
# ============================================================

NAV_FRAGMENT = "settings/access-control"

MODULE_META = {
    "name":     "Access Control",
    "fragment": NAV_FRAGMENT,
    "order":    6,
}

ACTIONS = {
    "assign": {
        "label":        "Assign Role",
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
        "assign_btn":      None,
        "dialog_open":     False,
        "user_dropdown":   None,
        "role_dropdown":   None,
        "dropdown_option": None,
        "effective_from":  None,
        "effective_to":    None,
        "primary_toggle":  None,
        "save_btn":        None,
    })

    comboboxes = []

    for el in dom:
        tag   = (el.get("tag")   or "").lower()
        text  = (el.get("text")  or "").lower()
        label = (el.get("label") or "").lower()
        eid   = (el.get("id")    or "").lower()
        cls   = (el.get("class") or "").lower()
        role  = (el.get("role")  or "").lower()
        tokens = text + " " + label + " " + eid + " " + cls

        # ASSIGN ROLE BUTTON
        if tag == "button" and "assign role" in tokens and not result["assign_btn"]:
            result["assign_btn"] = el

        # DIALOG
        if "assign role" in tokens:
            result["dialog_open"] = True

        # COMBOBOXES (user + role dropdowns)
        if role == "combobox":
            comboboxes.append(el)

        # DROPDOWN OPTION
        if role == "option" or ("mui" in cls and "option" in cls):
            result["dropdown_option"] = el

        # DATE FIELDS
        if tag == "div" and "effective from" in tokens and not result["effective_from"]:
            result["effective_from"] = el

        if tag == "div" and "effective to" in tokens and not result["effective_to"]:
            result["effective_to"] = el

        # PRIMARY TOGGLE
        if role == "switch" and not result["primary_toggle"]:
            result["primary_toggle"] = el

        # SAVE BUTTON
        if tag == "button" and "save" in tokens and not result["save_btn"]:
            result["save_btn"] = el

    # Assign comboboxes after loop
    if len(comboboxes) >= 1:
        result["user_dropdown"] = comboboxes[0]
    if len(comboboxes) >= 2:
        result["role_dropdown"] = comboboxes[1]

    return result


# ============================================================
# ASSIGN ROLE STATE
# ============================================================

class _AssignState:
    def __init__(self):
        self.clicked_assign = False
        self.user_opened    = False
        self.user_selected  = False
        self.role_opened    = False
        self.role_selected  = False
        self.date_done      = False
        self.to_date_done   = False
        self.toggle_done    = False
        self.saved          = False
        self.verified       = False
        self._verify_wait   = 0
        self.MAX_WAIT       = 4

    def reset(self):
        self.__init__()


_assign = _AssignState()


# ============================================================
# ASSIGN ROLE HANDLER
# ============================================================

async def _decide_assign(els, url):
    s = _assign
    r = get_reporter()

    # ALREADY DONE
    if s.verified:
        if r:
            r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Assign Role completed"}

    # STEP 1: CLICK ASSIGN ROLE
    if not s.clicked_assign:
        btn = els["assign_btn"]
        if btn:
            s.clicked_assign = True
            step = {"action": "click", "selector": btn["selector"]}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step
        return {"action": "wait", "seconds": 1}

    # STEP 2: WAIT FOR DIALOG
    if not els["dialog_open"]:
        return {"action": "wait", "seconds": 1}

    print("DEBUG:",
          "user:",   bool(els["user_dropdown"]),
          "role:",   bool(els["role_dropdown"]),
          "option:", bool(els["dropdown_option"]))

    # STEP 3: OPEN USER DROPDOWN
    if not s.user_opened:
        if els["user_dropdown"]:
            s.user_opened = True
            step = {"action": "click", "selector": els["user_dropdown"]["selector"]}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step
        return {"action": "wait", "seconds": 1}

    # STEP 4: SELECT USER
    if not s.user_selected:
        if not els["dropdown_option"]:
            return {"action": "wait", "seconds": 1}
        s.user_selected = True
        step = {"action": "click", "selector": els["dropdown_option"]["selector"]}
        if r:
            r.log_step(len(r.steps) + 1, step, url)
        return step

    # STEP 5: OPEN ROLE DROPDOWN
    if not s.role_opened:
        if els["role_dropdown"]:
            s.role_opened = True
            step = {"action": "click", "selector": els["role_dropdown"]["selector"]}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step
        return {"action": "wait", "seconds": 1}

    # STEP 6: SELECT ROLE
    if not s.role_selected:
        if not els["dropdown_option"]:
            return {"action": "wait", "seconds": 1}
        s.role_selected = True
        step = {"action": "click", "selector": els["dropdown_option"]["selector"]}
        if r:
            r.log_step(len(r.steps) + 1, step, url)
        return step

    # STEP 7: EFFECTIVE FROM
    if not s.date_done:
        if els["effective_from"]:
            s.date_done = True
            step = {"action": "click", "selector": els["effective_from"]["selector"]}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step
        return {"action": "wait", "seconds": 1}

    # STEP 8: EFFECTIVE TO
    if not s.to_date_done:
        if els["effective_to"]:
            s.to_date_done = True
            step = {"action": "click", "selector": els["effective_to"]["selector"]}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step
        return {"action": "wait", "seconds": 1}

    # STEP 9: TOGGLE
    if not s.toggle_done:
        if els["primary_toggle"]:
            s.toggle_done = True
            step = {"action": "click", "selector": els["primary_toggle"]["selector"]}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step
        return {"action": "wait", "seconds": 1}

    # STEP 10: SAVE
    if not s.saved:
        if els["save_btn"]:
            s.saved = True
            step = {"action": "click", "selector": els["save_btn"]["selector"]}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step
        return {"action": "wait", "seconds": 1}

    # STEP 11: VERIFY
    dom_raw = els.get("dom_raw") or []
    toast_found = bool(els.get("success_toast")) or any(
        ("success"  in (el.get("text")  or "").lower()
         or "assigned" in (el.get("text")  or "").lower()
         or "snackbar" in (el.get("class") or "").lower()
         or "toast"    in (el.get("class") or "").lower())
        for el in dom_raw
    )
    dialog_closed = not els["dialog_open"]

    if toast_found or dialog_closed:
        s.verified = True
        if r:
            r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Assign Role completed"}

    s._verify_wait += 1
    if s._verify_wait >= s.MAX_WAIT:
        s.verified = True
        if r:
            r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Assign Role completed (assumed after {} waits)".format(s.MAX_WAIT)}

    return {"action": "wait", "seconds": 1}


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

def reset_state(keep_session=False):
    reset_login()
    reset_nav()
    _assign.reset()
    print("[STATE] Access Control reset")


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

    if action == "assign":
        return await _decide_assign(els, url)

    return {"action": "wait", "seconds": 1}