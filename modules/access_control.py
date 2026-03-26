from datetime import datetime

_BASE_URL = "https://vertex-dev.savetime.com"

# ============================================================
# ACTIONS
# ============================================================

ACTIONS = {
    "assign": {
        "label": "Assign Role",
        "needs_target": False,
    }
}

ACTION_KEYS = list(ACTIONS.keys())

# ============================================================
# DOM SCANNER
# ============================================================

def scan_dom(dom):
    result = {
        # Login
        "email_input": None,
        "password_input": None,
        "next_btn": None,
        "signin_btn": None,
        "yes_btn": None,

        # Navigation
        "profile_icon": None,
        "settings_btn": None,
        "access_control_nav": None,

        # Assign Role Flow
        "assign_btn": None,
        "dialog_open": False,
        "user_dropdown": None,
        "role_dropdown": None,
        "dropdown_option": None,
        "effective_from": None,
        "primary_toggle": None,
        "save_btn": None,
    }

    for el in dom:
        tag = (el.get("tag") or "").lower()
        text = (el.get("text") or "").lower()
        label = (el.get("label") or "").lower()
        eid = (el.get("id") or "").lower()
        cls = (el.get("class") or "").lower()
        role = (el.get("role") or "").lower()

        comb = text + " " + label + " " + eid + " " + cls

        # LOGIN
        if eid == "i0116":
            result["email_input"] = el

        if eid == "i0118":
            result["password_input"] = el

        if "next" in comb or "idsibutton9" in eid:
            result["next_btn"] = el

        if "sign in" in comb:
            result["signin_btn"] = el

        if "yes" in comb:
            result["yes_btn"] = el

        # NAVIGATION
        if eid == "nav-user-profile":
            result["profile_icon"] = el

        if eid == "settings-icon":
            result["settings_btn"] = el

        if "access control" in comb:
            result["access_control_nav"] = el

        # ASSIGN ROLE BUTTON
        if tag == "button" and "assign role" in comb:
            result["assign_btn"] = el

        # DIALOG
        if tag == "h2" and "assign role" in comb:
            result["dialog_open"] = True

        # USER DROPDOWN
        if role == "combobox" and "user" in comb:
            result["user_dropdown"] = el

        # ROLE DROPDOWN
        if el.get("role") == "combobox" and "user" in comb:
            result["user_dropdown"] = el

        if el.get("role") == "combobox" and "role" in comb:
            result["role_dropdown"] = el

        # DROPDOWN OPTION (generic)
        if role == "option":
            result["dropdown_option"] = el

        # DATE
        if "effective from" in comb:
            result["effective_from"] = el

        # TOGGLE
        if "switch" in str(el):
            result["primary_toggle"] = el

        # SAVE
        if tag == "button" and "save" in comb:
            result["save_btn"] = el

    return result


# ============================================================
# LOGIN STATE (UNCHANGED)
# ============================================================

class _LoginState:
    def __init__(self):
        self.done = False
        self.yes_clicked = False

    def reset(self):
        self.__init__()


_login = _LoginState()


def login_done():
    return _login.done


def handle_login(els, email, password, url):
    if _login.done:
        return None

    is_sso = "microsoftonline.com" in url.lower()

    e = els["email_input"]
    p = els["password_input"]
    nb = els["next_btn"]
    sb = els["signin_btn"]
    yb = els["yes_btn"]

    if yb and not _login.yes_clicked:
        _login.yes_clicked = True
        return {"action": "click", "selector": yb["selector"]}

    if p:
        if not (p.get("value") or "").strip():
            return {"action": "type", "selector": p["selector"], "text": password}
        if sb:
            return {"action": "click", "selector": sb["selector"]}

    if e:
        if not (e.get("value") or "").strip():
            return {"action": "type", "selector": e["selector"], "text": email}
        if nb:
            return {"action": "click", "selector": nb["selector"]}

    if not is_sso:
        _login.done = True
        return None

    return {"action": "wait", "seconds": 1}


# ============================================================
# NAVIGATION STATE
# ============================================================

class _NavState:
    def __init__(self):
        self.profile_clicked = False
        self.settings_clicked = False
        self.access_clicked = False
        self.done = False

    def reset(self):
        self.__init__()


_nav = _NavState()


def nav_done():
    return _nav.done


def handle_nav(els, url):
    s = _nav

    if "/settings/access-control" in url.lower():
        s.done = True
        return {"action": "wait", "seconds": 1}

    if not s.profile_clicked:
        if els["profile_icon"]:
            s.profile_clicked = True
            return {"action": "click", "selector": els["profile_icon"]["selector"]}

    if not s.settings_clicked:
        if els["settings_btn"]:
            s.settings_clicked = True
            return {"action": "click", "selector": els["settings_btn"]["selector"]}

    if not s.access_clicked:
        if els["access_control_nav"]:
            s.access_clicked = True
            return {"action": "click", "selector": els["access_control_nav"]["selector"]}

    return {"action": "wait", "seconds": 1}


# ============================================================
# ASSIGN ROLE STATE
# ============================================================

class _AssignState:
    def __init__(self):
        self.clicked_assign = False
        self.user_opened = False
        self.user_selected = False
        self.role_opened = False
        self.role_selected = False
        self.date_done = False
        self.toggle_done = False
        self.saved = False

    def reset(self):
        self.__init__()


_assign = _AssignState()


# ============================================================
# ASSIGN ROLE HANDLER
# ============================================================

def handle_assign(els):
    s = _assign

    # CLICK ASSIGN BUTTON
    if not s.clicked_assign:
        if els["assign_btn"]:
            s.clicked_assign = True
            return {"action": "click", "selector": els["assign_btn"]["selector"]}
        return {"action": "wait", "seconds": 1}

    # WAIT DIALOG
    if not els["dialog_open"]:
        return {"action": "wait", "seconds": 1}

    # USER DROPDOWN OPEN
    # Step 2: Open User dropdown
    if not s.user_selected:
        if els["user_dropdown"]:
            s.user_selected = True
            return {"action": "click", "selector": els["user_dropdown"]["selector"]}

    # Step 3: Select option from User dropdown
    if s.user_selected and not s.role_selected:
        return {"action": "select_first_option"}
    
    # Step 4: Open Role dropdown
    if not s.role_selected:
        if els["role_dropdown"]:
            s.role_selected = True
            return {"action": "click", "selector": els["role_dropdown"]["selector"]}

    # Step 5: Select option from Role dropdown
    if s.role_selected and not s.date_selected:
        return {"action": "select_first_option"}

    # USER SELECT
    if not s.user_selected:
        if els["dropdown_option"]:
            s.user_selected = True
            return {"action": "click", "selector": els["dropdown_option"]["selector"]}
        return {"action": "wait", "seconds": 1}

    # ROLE DROPDOWN OPEN
    if not s.role_opened:
        if els["role_dropdown"]:
            s.role_opened = True
            return {"action": "click", "selector": els["role_dropdown"]["selector"]}
        return {"action": "wait", "seconds": 1}

    # ROLE SELECT
    if not s.role_selected:
        if els["dropdown_option"]:
            s.role_selected = True
            return {"action": "click", "selector": els["dropdown_option"]["selector"]}
        return {"action": "wait", "seconds": 1}

    # DATE CLICK
    if not s.date_done:
        if els["effective_from"]:
            s.date_done = True
            return {"action": "click", "selector": els["effective_from"]["selector"]}
        return {"action": "wait", "seconds": 1}

    # TOGGLE
    if not s.toggle_done:
        if els["primary_toggle"]:
            s.toggle_done = True
            return {"action": "click", "selector": els["primary_toggle"]["selector"]}
        return {"action": "wait", "seconds": 1}

    # SAVE
    if not s.saved:
        if els["save_btn"]:
            s.saved = True
            return {"action": "click", "selector": els["save_btn"]["selector"]}
        return {"action": "wait", "seconds": 1}

    return {
        "action": "done",
        "result": "PASS",
        "reason": "Assign Role completed"
    }


# ============================================================
# PUBLIC ENTRY
# ============================================================

def reset_state():
    _login.reset()
    _nav.reset()
    _assign.reset()
    print("[STATE] Access Control reset")


async def decide_action(action, dom, url, goal="", email=None, password=None):
    els = scan_dom(dom)

    if not login_done():
        step = handle_login(els, email, password, url)
        if step:
            return step

    if not nav_done():
        return handle_nav(els, url)

    return handle_assign(els)