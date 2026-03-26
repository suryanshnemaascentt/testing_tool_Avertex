from datetime import datetime

_BASE_URL = "https://vertex-dev.savetime.com"

# ============================================================
# ACTIONS
# ============================================================

ACTIONS = {
    "add": {
        "label": "Add Client",
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
        "clients_nav": None,

        # Add client flow
        "add_client_btn": None,
        "save_btn": None,
        "dialog_open": False,
    }

    for el in dom:
        tag = (el.get("tag") or "").lower()
        etype = (el.get("type") or "").lower()
        text = (el.get("text") or "").lower()
        label = (el.get("label") or "").lower()
        eid = (el.get("id") or "").lower()
        cls = (el.get("class") or "").lower()

        comb = text + " " + label + " " + eid + " " + cls

        # LOGIN
        if etype == "email" or eid == "i0116":
            result["email_input"] = el

        if etype == "password" or eid == "i0118":
            result["password_input"] = el

        if "next" in comb:
            result["next_btn"] = el

        if "sign in" in comb or "login" in comb:
            result["signin_btn"] = el

        if "yes" in comb or "stay signed in" in comb:
            result["yes_btn"] = el

        # NAVIGATION
        if eid == "nav-user-profile":
            result["profile_icon"] = el

        if eid == "settings-icon":
            result["settings_btn"] = el

        if "settings-nav-clients" in eid:
            result["clients_nav"] = el

        # ADD CLIENT
        if eid == "clients-add-btn":
            result["add_client_btn"] = el

        # SAVE BUTTON
        if "save" in comb and tag == "button":
            result["save_btn"] = el

        # DIALOG OPEN
        if "add new client" in comb:
            result["dialog_open"] = True

    return result


# ============================================================
# LOGIN STATE
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

    # YES
    if yb and not _login.yes_clicked:
        _login.yes_clicked = True
        return {"action": "click", "selector": yb["selector"]}

    # PASSWORD
    if p:
        if not (p.get("value") or "").strip():
            return {"action": "type", "selector": p["selector"], "text": password}
        if sb:
            return {"action": "click", "selector": sb["selector"]}

    # EMAIL
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
        self.clients_clicked = False
        self.done = False

    def reset(self):
        self.__init__()


_nav = _NavState()


def nav_done():
    return _nav.done


def handle_nav(els, url):
    s = _nav

    if "/settings/clients" in url.lower():
        s.done = True
        return None

    if not s.profile_clicked:
        if els["profile_icon"]:
            s.profile_clicked = True
            return {"action": "click", "selector": els["profile_icon"]["selector"]}
        return {"action": "wait", "seconds": 1}

    if not s.settings_clicked:
        if els["settings_btn"]:
            s.settings_clicked = True
            return {"action": "click", "selector": els["settings_btn"]["selector"]}
        return {"action": "wait", "seconds": 1}

    if not s.clients_clicked:
        if els["clients_nav"]:
            s.clients_clicked = True
            return {"action": "click", "selector": els["clients_nav"]["selector"]}
        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# ADD CLIENT STATE
# ============================================================

class _AddClientState:
    def __init__(self):
        self.add_clicked = False
        self.form_open = False
        self.submitted = False
        self.verified = False
        self.wait = 0
        self.MAX_WAIT = 4

    def reset(self):
        self.__init__()


_add = _AddClientState()


async def decide_add(els, url):
    s = _add

    # SUCCESS
    if s.verified:
        return {
            "action": "done",
            "result": "PASS",
            "reason": "Client added successfully"
        }

    # AFTER SUBMIT
    if s.submitted:
        if not els["dialog_open"]:
            s.verified = True
            return {
                "action": "done",
                "result": "PASS",
                "reason": "Client added successfully"
            }
        return {"action": "wait", "seconds": 1}

    # FILL FORM
    if s.form_open:
        s.submitted = True
        return {
            "action": "fill_client_form",
            "params": {
                "client_name": f"Client_{datetime.now().strftime('%H%M%S')}",
                "email": "test@test.com",
                "phone": "9999999999",
                "website": "https://test.com",
                "address": "Test Address",
                "city": "Mumbai",
                "country": "India",
                "industry": "Finance",
                "size": None,
                "active": True
            }
        }

    # CLICK ADD CLIENT
    if not s.add_clicked:
        if els["add_client_btn"]:
            s.add_clicked = True
            return {"action": "click", "selector": els["add_client_btn"]["selector"]}
        return {"action": "wait", "seconds": 1}

    # WAIT FOR FORM
    if s.add_clicked and not s.form_open:
        if els["dialog_open"]:
            s.form_open = True
            return {"action": "wait", "seconds": 1}
        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# PUBLIC ENTRY
# ============================================================

def reset_state():
    _login.reset()
    _nav.reset()
    _add.reset()
    print("[STATE] Add Client module reset")


async def decide_action(action, dom, url, goal="", email=None, password=None):
    els = scan_dom(dom)

    # LOGIN
    if not login_done():
        step = handle_login(els, email, password, url)
        if step:
            return step

    # NAV
    if not nav_done():
        step = handle_nav(els, url)
        if step:
            return step

    # ADD CLIENT FLOW
    if action == "add":
        return await decide_add(els, url)

    return {"action": "wait", "seconds": 1}