import random
from datetime import datetime

_BASE_URL = "https://vertex-dev.savetime.com"

# ============================================================
# ACTIONS (REQUIRED BY FRAMEWORK)
# ============================================================

ACTIONS = {
    "edit_estimate": {
        "label": "Create Manual Estimate",
        "needs_target": False,
    }
}

ACTION_KEYS = list(ACTIONS.keys())

# ============================================================
# DOM SCANNER
# ============================================================

def scan_dom(dom):
    result = {
        "email_input": None,
        "password_input": None,
        "next_btn": None,
        "signin_btn": None,
        "yes_btn": None,

        "project_name": None,
        "description_input": None,
        "start_date": None,
        "end_date": None,
    }

    for el in dom:
        tag = (el.get("tag") or "").lower()
        etype = (el.get("type") or "").lower()
        text = (el.get("text") or "").lower()
        eid = (el.get("id") or "").lower()
        label = (el.get("label") or "").lower()
        placeholder = (el.get("placeholder") or "").lower()

        comb = text + " " + label + " " + eid

        # LOGIN
        if etype == "email" or eid == "i0116":
            result["email_input"] = el

        if etype == "password" or eid == "i0118":
            result["password_input"] = el

        if "next" in comb:
            result["next_btn"] = el

        if "sign in" in comb:
            result["signin_btn"] = el

        if "yes" in comb:
            result["yes_btn"] = el

        # FORM
        if "enter project name" in placeholder:
            result["project_name"] = el

        # Description field (NEW FIX)
        if "brief project description" in placeholder:
            result["description_input"] = el
        
        # DATE FIELDS
        if el.get("selector") == "(//input[@type=\"date\"])[1]":
            result["start_date"] = el

        if el.get("selector") == "(//input[@type=\"date\"])[2]":
            result["end_date"] = el

    return result


# ============================================================
# LOGIN (UNCHANGED)
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
# STATE
# ============================================================

class _State:
    def __init__(self):
        self.clicked_estimates = False
        self.clicked_new = False
        self.clicked_manual = False
        self.project_name_done = False
        self.description_done = False
        self.start_date_clicked = False
        self.start_date_done = False
        self.end_date_clicked = False
        self.end_date_done = False

    def reset(self):
        self.__init__()


_state = _State()


# ============================================================
# HELPERS
# ============================================================

PROJECT_NAMES = [
    "Apollo", "Neptune", "Orion", "Phoenix", "Atlas",
    "Quantum", "Nova", "Vertex", "Nimbus", "Zenith"
]


def generate_project_name():
    return f"{random.choice(PROJECT_NAMES)}_{datetime.now().strftime('%H%M%S')}"


def generate_description():
    return f"Automation_Project_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"

from datetime import timedelta

def generate_dates():
    # Start date between 2026 and 2031
    start_base = datetime(2026, 1, 1)
    end_base = datetime(2031, 1, 1)

    delta_days = (end_base - start_base).days
    start_date = start_base + timedelta(days=random.randint(0, delta_days))

    # End date = start + minimum 3 years
    end_date = start_date + timedelta(days=365 * 3 + random.randint(1, 365))

    return (
        start_date.strftime("%d-%m-%Y"),
        end_date.strftime("%d-%m-%Y")
    )


# ============================================================
# MAIN FLOW
# ============================================================

def handle_flow(els):
    s = _state

    # STEP 1 → Click Estimates
    if not s.clicked_estimates:
        s.clicked_estimates = True
        return {"action": "click", "selector": "//div[@id='nav-item-estimates']"}

    # STEP 2 → Click New Estimate
    if not s.clicked_new:
        s.clicked_new = True
        return {"action": "click", "selector": "//button[@id='new-estimate-button']"}

    # STEP 3 → Click Create Manually
    if not s.clicked_manual:
        s.clicked_manual = True
        return {"action": "click", "selector": "//button[text()='Create Manually']"}

    # STEP 4 → Enter Project Name
    if not s.project_name_done:
        if els["project_name"]:
            s.project_name_done = True
            return {
                "action": "type",
                "selector": els["project_name"]["selector"],
                "text": generate_project_name()
            }
        return {"action": "wait", "seconds": 1}

    # STEP 4 → Enter Description
    if not s.description_done:
        if els["description_input"]:
            s.description_done = True
            return {
                "action": "type",
                "selector": els["description_input"]["selector"],
                "text": generate_description()
            }
        return {"action": "wait", "seconds": 1}
    
    # STEP 5 → Start Date CLICK
    if not s.start_date_clicked:
        if els["start_date"]:
            s.start_date_clicked = True
            return {"action": "click", "selector": "(//input[@type='date'])[1]"}
        return {"action": "wait", "seconds": 1}


    # STEP 5 → Start Date TYPE
    if not s.start_date_done:
        if els["start_date"]:
            start, end = generate_dates()
            s.generated_start = start
            s.generated_end = end
            s.start_date_done = True
            return {
                "action": "type",
                "selector": "(//input[@type='date'])[1]",
                "text": start
            }
        return {"action": "wait", "seconds": 1}


    # STEP 5 → End Date CLICK
    if not s.end_date_clicked:
        if els["end_date"]:
            s.end_date_clicked = True
            return {"action": "click", "selector": "(//input[@type='date'])[2]"}
        return {"action": "wait", "seconds": 1}


    # STEP 5 → End Date TYPE
    if not s.end_date_done:
        if els["end_date"]:
            s.end_date_done = True
            return {
                "action": "type",
                "selector": "(//input[@type='date'])[2]",
                "text": s.generated_end
            }
        return {"action": "wait", "seconds": 1}

    return {"action": "done", "result": "PASS"}


# ============================================================
# ENTRY
# ============================================================

def reset_state():
    _login.reset()
    _state.reset()


async def decide_action(action, dom, url, goal="", email=None, password=None):
    els = scan_dom(dom)

    if not login_done():
        step = handle_login(els, email, password, url)
        if step:
            return step

    return handle_flow(els)