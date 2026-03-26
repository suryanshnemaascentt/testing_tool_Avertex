import random
from datetime import datetime, timedelta

_BASE_URL = "https://vertex-dev.savetime.com"

ACTIONS = {
    "estimate_ai": {
        "label": "Create AI Estimate",
        "needs_target": False,
    }
}

ACTION_KEYS = list(ACTIONS.keys())


# ============================================================
# DOM SCANNER (UNCHANGED)
# ============================================================

def scan_dom(dom):
    result = {
        "email_input": None,
        "password_input": None,
        "next_btn": None,
        "signin_btn": None,
        "yes_btn": None,

        "new_estimate_btn": None,
        "start_ai_btn": None,
        "description_input": None,
        "generate_btn": None,

        "tech_input": None,
        "timeline_dropdown": None,
        "start_date": None,
        "end_date": None,
    }

    for el in dom:
        tag = (el.get("tag") or "").lower()
        etype = (el.get("type") or "").lower()
        text = (el.get("text") or "").lower()
        eid = (el.get("id") or "").lower()
        name = (el.get("name") or "").lower()
        label = (el.get("label") or "").lower()

        comb = text + " " + label + " " + eid

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

        if "new estimate" in text:
            result["new_estimate_btn"] = el

        if "start with ai" in text:
            result["start_ai_btn"] = el

        if tag == "textarea":
            result["description_input"] = el

        if "generate estimate" in text:
            result["generate_btn"] = el

        if "search and select technologies" in (el.get("placeholder") or "").lower():
            result["tech_input"] = el

        if "gantt_interval" in eid or "timeline interval" in comb:
            result["timeline_dropdown"] = el

        if name == "project_start_date":
            result["start_date"] = el

        if name == "project_end_date":
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

class _EstimateState:
    def __init__(self):
        self.clicked_estimates = False
        self.clicked_new = False
        self.clicked_ai = False
        self.description_done = False

        self.tech_scrolled = False
        self.tech_clicked = False
        self.tech_waited = False
        self.tech_selected = False

        self.timeline_scrolled = False
        self.timeline_clicked = False
        self.timeline_waited = False
        self.timeline_selected = False

        self.start_date_done = False
        self.end_date_done = False

        self.fixed_size_clicked = False
        self.team_size_entered = False
        self.currency_clicked = False
        self.currency_waited = False
        self.currency_selected = False
        self.onsite_clicked = False
        self.offshore_clicked = False
        self.hybrid_clicked = False

                # ================= PORTFOLIO (NEW) =================
        self.portfolio_scrolled = False
        self.portfolio_clicked = False
        self.portfolio_waited = False
        self.portfolio_selected = False

                # ================= CATEGORY (NEW) =================
        self.category_scrolled = False
        self.category_clicked = False
        self.category_waited = False
        self.category_selected = False
        self.category_clicked = False
        self.category_selected = False
        self.customize_clicked = False

        self.generated = False

    def reset(self):
        self.__init__()


_state = _EstimateState()


# ============================================================
# HELPERS
# ============================================================

def generate_description():
    return f"AI Project generated at {datetime.now().strftime('%Y%m%d%H%M%S')}"


def get_dates():
    today = datetime.today()
    start = today + timedelta(days=1)
    end = start + timedelta(days=30)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def get_team_size():
    return str(random.randint(5, 50))


# ============================================================
# MAIN FLOW (FINAL FIXED)
# ============================================================

def handle_estimate_ai(els):
    s = _state

    # STEP 1
    if not s.clicked_estimates:
        s.clicked_estimates = True
        return {"action": "click", "selector": "//div[@id='nav-item-estimates']"}

    # STEP 2
    if not s.clicked_new:
        if els["new_estimate_btn"]:
            s.clicked_new = True
            return {"action": "click", "selector": els["new_estimate_btn"]["selector"]}
        return {"action": "wait", "seconds": 1}

    # STEP 3
    if not s.clicked_ai:
        if els["start_ai_btn"]:
            s.clicked_ai = True
            return {"action": "click", "selector": els["start_ai_btn"]["selector"]}
        return {"action": "wait", "seconds": 1}

    # STEP 4: DESCRIPTION
    if not s.description_done:
        if els["description_input"]:
            s.description_done = True
            return {
                "action": "type",
                "selector": els["description_input"]["selector"],
                "text": generate_description()
            }
        return {"action": "wait", "seconds": 1}

    # ================= TECHNOLOGY =================

    if not s.tech_scrolled:
        if els["tech_input"]:
            s.tech_scrolled = True
            return {"action": "scroll", "selector": els["tech_input"]["selector"]}

    if not s.tech_clicked:
        s.tech_clicked = True
        return {"action": "click", "selector": els["tech_input"]["selector"]}

    if not s.tech_waited:
        s.tech_waited = True
        return {"action": "wait", "seconds": 2}

    if not s.tech_selected:
        s.tech_selected = True
        return {
            "action": "click",
            "selector": "//ul[contains(@class,'MuiAutocomplete-listbox')]//li[1]"
        }

    # ================= TIMELINE =================

    if not s.timeline_scrolled:
        if els["timeline_dropdown"]:
            s.timeline_scrolled = True
            return {"action": "scroll", "selector": "#mui-component-select-gantt_interval"}

    if not s.timeline_clicked:
        s.timeline_clicked = True
        return {"action": "click", "selector": "#mui-component-select-gantt_interval"}

    if not s.timeline_waited:
        s.timeline_waited = True
        return {"action": "wait", "seconds": 2}

    if not s.timeline_selected:
        s.timeline_selected = True
        return {
            "action": "click",
            "selector": "//ul[@role='listbox']//li[1]"
        }

    # ================= DATES =================

    if not s.start_date_done:
        if els["start_date"]:
            start, _ = get_dates()
            s.start_date_done = True
            return {
                "action": "type",
                "selector": els["start_date"]["selector"],
                "text": start
            }
        return {"action": "wait", "seconds": 1}

    if not s.end_date_done:
        if els["end_date"]:
            _, end = get_dates()
            s.end_date_done = True
            return {
                "action": "type",
                "selector": els["end_date"]["selector"],
                "text": end
            }
        return {"action": "wait", "seconds": 1}
    
    if not s.fixed_size_clicked:
        s.fixed_size_clicked = True
        return {"action": "click", "selector": "//button[contains(.,'Fixed Size')]"}

    if not s.team_size_entered:
        s.team_size_entered = True
        return {
            "action": "type",
            "selector": "//input[@name='team_size']",
            "text": get_team_size()
        }

    if not s.currency_clicked:
        s.currency_clicked = True
        return {"action": "click", "selector": "#mui-component-select-display_currency"}

    if not s.currency_waited:
        s.currency_waited = True
        return {"action": "wait", "seconds": 2}

    if not s.currency_selected:
        s.currency_selected = True
        index = random.randint(2, 6)
        return {
            "action": "click",
            "selector": f"(//ul[@role='listbox']//li)[{index}]"
        }

    if not s.onsite_clicked:
        s.onsite_clicked = True
        return {"action": "click", "selector": "//button[contains(.,'Onsite')]"}

    if not s.offshore_clicked:
        s.offshore_clicked = True
        return {"action": "click", "selector": "//button[contains(.,'Offshore')]"}

    if not s.hybrid_clicked:
        s.hybrid_clicked = True
        return {"action": "click", "selector": "//button[contains(.,'Hybrid')]"}
    
    if not s.portfolio_clicked:
        s.portfolio_clicked = True
        return {"action": "click", "selector": "#mui-component-select-portfolio"}

    if not s.portfolio_waited:
        s.portfolio_waited = True
        return {"action": "wait", "seconds": 2}

    if not s.portfolio_selected:
        s.portfolio_selected = True
        return {
            "action": "click",
            "selector": f"(//ul[@role='listbox']//li)[{random.randint(2,6)}]"
        }

        # ================= CATEGORY =================
    # CATEGORY CLICK
    if not s.category_clicked:
        el = find_by_id(els, "mui-component-select-category")
        if el:
            s.category_clicked = True
            return {
                "action": "click",
                "selector": el["selector"]
            }

# CATEGORY SELECT (AFTER CLICK)
    if s.category_clicked and not s.category_selected:
        s.category_selected = True
        return {
            "action": "click",
            "selector": "li[role='option']:nth-child(2)"   # ✅ safe generic option
        }
    if not s.category_scrolled:
        s.category_scrolled = True
        return {"action": "scroll", "selector": "#mui-component-select-category"}

    if not s.category_clicked:
        s.category_clicked = True
        return {"action": "click", "selector": "#mui-component-select-category"}

    if not s.category_waited:
        s.category_waited = True
        return {"action": "wait", "seconds": 2}

    if not s.category_selected:
        s.category_selected = True
        return {
            "action": "click",
            "selector": "(//ul[@role='listbox']//li)[1]"
        }

    if not s.customize_clicked:
        s.customize_clicked = True
        return {"action": "click", "selector": "//button[contains(.,'Customize Rates')]"}

    if not s.hide_clicked:
        s.hide_clicked = True
        return {"action": "click", "selector": "//button[contains(.,'Hide Rates')]"}

    # ================= FINAL STEP (UNCHANGED) =================

    if not s.generated:
        if els["generate_btn"]:
            s.generated = True
            return {"action": "click", "selector": els["generate_btn"]["selector"]}
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

    return handle_estimate_ai(els)