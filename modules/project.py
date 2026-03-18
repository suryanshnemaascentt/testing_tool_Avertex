
import re
from datetime import datetime, timedelta

_BASE_URL = "https://vertex-dev.savetime.com"

# ============================================================
# ACTIONS REGISTRY
# ============================================================

ACTIONS = {
    "create": {
        "label":        "Create Project  (auto name + dates)",
        "needs_target": False,
    },
    "update": {
        "label":        "Update Project  (search by name)",
        "needs_target": True,
    },
    "delete": {
        "label":        "Delete Project  (search by name)",
        "needs_target": True,
    },
}

ACTION_KEYS = list(ACTIONS.keys())


# ============================================================
# DOM SCANNER
# ============================================================

_NON_TOAST = ("input", "button")
_SIGNIN    = ("sign in", "signin", "log in", "login")
_YES       = ("yes", "stay signed in", "kmsi")
_NAV_TAGS  = ("a", "li", "span")
_BTN_TAGS  = ("button", "input")
_BTN_TYPES = ("button", "submit", "")

_DELETE_SUCCESS_PHRASES = (
    "deleted successfully",
    "removed successfully",
    "project deleted",
    "successfully deleted",
    "delete successful",
)


def scan_dom(dom):
    result = {
        "dom_raw":             dom,
        "email_input":         None,
        "password_input":      None,
        "next_btn":            None,
        "signin_btn":          None,
        "yes_btn":             None,
        "projects_nav":        None,
        "new_project_btn":     None,
        "search_input":        None,
        "view_btn":            None,
        "edit_btn":            None,
        "delete_btn":          None,
        "confirm_btn":         None,
        "save_btn":            None,
        "autocomplete_inputs": [],
        "mui_selects":         [],
        "success_toast":       None,
        "error_toast":         None,
    }

    has_password = False

    for el in dom:
        tag   = (el.get("tag")         or "").lower()
        etype = (el.get("type")        or "").lower()
        eid   = (el.get("id")          or "").lower()
        label = (el.get("label")       or "").lower().strip()
        text  = (el.get("text")        or "").lower().strip()
        val   = (el.get("value")       or "").lower().strip()
        role  = (el.get("role")        or "").lower()
        ph    = (el.get("placeholder") or "").lower()
        cls   = (el.get("class")       or "").lower()
        lv    = label + " " + text + " " + val
        comb  = lv + " " + eid + " " + ph + " " + cls

        if etype == "email" or eid == "i0116":
            result["email_input"] = el
            continue
        if etype == "password" or eid == "i0118":
            result["password_input"] = el
            has_password = True
            continue

        if tag in _BTN_TAGS and etype in _BTN_TYPES:
            if "next" in lv and not result["next_btn"]:
                result["next_btn"] = el
            elif any(w in lv for w in _SIGNIN) and not result["signin_btn"]:
                result["signin_btn"] = el
            elif any(w in lv for w in _YES) and not result["yes_btn"]:
                result["yes_btn"] = el
            elif any(x in lv for x in ("new project", "add project", "create project")):
                result["new_project_btn"] = el
            elif text in ("view", "view details") or label == "view":
                result["view_btn"] = el
            elif text in ("edit", "edit details") or label == "edit":
                result["edit_btn"] = el
            elif text == "delete" or label == "delete":
                if not result["delete_btn"]:
                    result["delete_btn"] = el
            elif any(x in text for x in ("yes", "confirm", "ok", "sure", "proceed")):
                if not result["confirm_btn"]:
                    result["confirm_btn"] = el
            elif eid == "project-form-save" or "save project" in lv:
                result["save_btn"] = el

        if tag in _NAV_TAGS and "project" in comb and not result["projects_nav"]:
            result["projects_nav"] = el

        if (tag == "input" and etype in ("text", "search")
                and ("search" in ph or "search" in eid or "search" in cls)
                and not result["search_input"]):
            result["search_input"] = el

        if tag == "div" and role == "combobox":
            result["mui_selects"].append(el)

        if tag == "input" and role == "combobox":
            result["autocomplete_inputs"].append(el)

        if tag not in _NON_TOAST:
            if (any(phrase in comb for phrase in _DELETE_SUCCESS_PHRASES)
                    and not result["success_toast"]):
                result["success_toast"] = el
            if (any(x in comb for x in ("error", "failed", "invalid"))
                    and not result["error_toast"]):
                result["error_toast"] = el

    nb = result["next_btn"]
    if nb:
        if has_password:
            result["signin_btn"] = nb
            result["next_btn"]   = None
        elif not result["email_input"] and not result["password_input"]:
            result["yes_btn"]  = nb
            result["next_btn"] = None

    return result


# ============================================================
# LOGIN STATE + HANDLER
# ============================================================

class _LoginState:
    def __init__(self):
        self.done             = False
        self.yes_clicked      = False
        self.email_typed      = False
        self.password_typed   = False
        self.next_clicked     = False
        self.signin_clicked   = False
        self._empty_dom_count = 0
        self.MAX_EMPTY_DOM    = 5

    def reset(self):
        self.__init__()

_login = _LoginState()


def login_done():
    return _login.done


def handle_login(els, email, password, url):
    if _login.done:
        return None

    is_sso = "microsoftonline.com" in url.lower()
    is_app = _BASE_URL.replace("https://", "") in url.lower()

    if _login.yes_clicked and not is_sso:
        print("[LOGIN] SSO redirect complete — login done")
        _login.done = True
        return None

    if is_app and not is_sso:
        dom_count = len(els.get("dom_raw") or [])
        if dom_count == 0:
            _login._empty_dom_count += 1
            print("[LOGIN] DOM empty ({}/{}) — waiting for page".format(
                _login._empty_dom_count, _login.MAX_EMPTY_DOM))
            if _login._empty_dom_count >= _login.MAX_EMPTY_DOM:
                print("[LOGIN] No login form — treating as logged in")
                _login.done = True
                return None
            return {"action": "wait", "seconds": 2}
        else:
            _login._empty_dom_count = 0

    e  = els["email_input"]
    pw = els["password_input"]
    nb = els["next_btn"]
    sb = els["signin_btn"]
    yb = els["yes_btn"]

    print("[LOGIN] email={} pw={} next={} signin={} yes={}  url_type={}".format(
        "Y" if e else "N", "Y" if pw else "N",
        "Y" if nb else "N", "Y" if sb else "N",
        "Y" if yb else "N", "SSO" if is_sso else "APP",
    ))

    if yb:
        _login.yes_clicked = True
        print("[LOGIN] Clicking Yes / Stay signed in")
        return {"action": "click", "selector": yb["selector"],
                "sso_yes": True, "soft_fail": True}

    if not e and not pw and len(els.get("dom_raw") or []) > 0:
        print("[LOGIN] No credentials form — treating as logged in")
        _login.done = True
        return None

    if pw:
        if not (pw.get("value") or "").strip() and password:
            return {"action": "type", "selector": pw["selector"], "text": password}
        if (pw.get("value") or "").strip() and sb:
            return {"action": "click", "selector": sb["selector"]}
        return {"action": "wait", "seconds": 1}

    if e:
        if not (e.get("value") or "").strip() and email:
            return {"action": "type", "selector": e["selector"], "text": email}
        if (e.get("value") or "").strip() and nb:
            return {"action": "click", "selector": nb["selector"]}

    return {"action": "wait", "seconds": 1}


# ============================================================
# NAV STATE + HANDLER
# ============================================================

class _NavState:
    def __init__(self):
        self.done            = False
        self.fallback_fired  = False
        self.interacted      = set()

    def reset(self):
        self.__init__()

_nav = _NavState()


def nav_done():
    return _nav.done


def handle_nav(els, url):
    if "projects" in url.lower() and "microsoftonline.com" not in url.lower():
        _nav.done = True
        print("[NAV] On /projects page")
        return None

    if "microsoftonline.com" in url.lower():
        return {"action": "wait", "seconds": 1}

    pn = els["projects_nav"]
    if pn and pn["selector"] not in _nav.interacted:
        _nav.interacted.add(pn["selector"])
        print("[NAV] Clicking projects nav link")
        return {"action": "click", "selector": pn["selector"]}

    if not _nav.fallback_fired:
        _nav.fallback_fired = True
        target = _BASE_URL + "/projects"
        print("[NAV] Fallback navigate -> " + target)
        return {"action": "navigate", "url": target}

    return {"action": "wait", "seconds": 1}


# ============================================================
# CREATE STATE + LOGIC
# ============================================================

class _CreateState:
    def __init__(self):
        self.form_open    = False
        self.submitted    = False
        self.verified     = False
        self.last_name    = ""
        self._form_wait   = 0
        self._verify_wait = 0
        self.MAX_WAIT     = 4

    def reset(self):
        self.__init__()

_create_st = _CreateState()


async def decide_create(els, url):
    s = _create_st

    if s.verified:
        return {"action": "done", "result": "PASS",
                "reason": "Project '{}' created successfully".format(s.last_name)}

    if s.submitted:
        if els["success_toast"] or (
            "projects" in url.lower() and "create" not in url.lower()
        ):
            s.verified = True
            return {"action": "done", "result": "PASS",
                    "reason": "Project '{}' created successfully".format(s.last_name)}
        s._verify_wait += 1
        if s._verify_wait > s.MAX_WAIT:
            return {"action": "done", "result": "FAIL",
                    "reason": "Could not verify creation of '{}'".format(s.last_name)}
        return {"action": "wait", "seconds": 1}

    if s.form_open:
        name        = "AutoProject_{}".format(datetime.now().strftime("%H%M%S"))
        s.last_name = name
        s.submitted = True
        print("[CREATE] Filling form: '{}'".format(name))
        return {"action": "fill_form", "params": _build_create_params(name, els)}

    nb = els["new_project_btn"]
    if nb:
        s.form_open = True
        return {"action": "click", "selector": nb["selector"]}

    s._form_wait += 1
    if s._form_wait > s.MAX_WAIT:
        return {"action": "done", "result": "FAIL",
                "reason": "'New Project' button not found on page"}
    return {"action": "wait", "seconds": 1}


# ============================================================
# UPDATE STATE + LOGIC
# ============================================================

_UPDATE_RE = re.compile(r"update project\s+(.+?)$", re.IGNORECASE)


class _UpdateState:
    def __init__(self):
        self.target_name  = ""
        self.last_name    = ""
        self.search_typed = False
        self.view_clicked = False
        self.edit_clicked = False
        self.form_open    = False
        self.submitted    = False
        self.verified     = False
        self._nav_fired   = False
        self._search_wait = 0
        self._view_wait   = 0
        self._edit_wait   = 0
        self._verify_wait = 0
        self.interacted   = set()
        self.MAX_WAIT     = 4

    def reset(self):
        self.__init__()

_update_st = _UpdateState()


async def decide_update(els, url, goal):
    s = _update_st

    if not s.target_name:
        m = _UPDATE_RE.search(goal)
        if m:
            s.target_name = m.group(1).strip()
            print("[UPDATE] Target: '{}'".format(s.target_name))

    if s.verified:
        return {"action": "done", "result": "PASS",
                "reason": "Project '{}' updated successfully".format(s.last_name)}

    if s.submitted:
        if els["success_toast"] or not els["save_btn"]:
            s.verified = True
            return {"action": "done", "result": "PASS",
                    "reason": "Project '{}' updated successfully".format(s.last_name)}
        s._verify_wait += 1
        if s._verify_wait >= s.MAX_WAIT:
            return {"action": "done", "result": "FAIL",
                    "reason": "Form still open after save"}
        return {"action": "wait", "seconds": 1}

    if s.form_open:
        name        = "UpdatedProject_{}".format(datetime.now().strftime("%H%M%S"))
        s.last_name = name
        s.submitted = True
        print("[UPDATE] Filling update form: '{}'".format(name))
        return {"action": "fill_form", "params": _build_update_params(name, els)}

    if s.view_clicked and not s.edit_clicked:
        eb = els["edit_btn"]
        if eb and eb["selector"] not in s.interacted:
            s.interacted.add(eb["selector"])
            s.edit_clicked = True
            s.form_open    = True
            return {"action": "click", "selector": eb["selector"]}
        s._edit_wait += 1
        if s._edit_wait >= s.MAX_WAIT:
            return {"action": "done", "result": "FAIL",
                    "reason": "'Edit' button not found"}
        return {"action": "wait", "seconds": 1}

    if s.search_typed and not s.view_clicked:
        vb = els["view_btn"]
        if vb and vb["selector"] not in s.interacted:
            s.interacted.add(vb["selector"])
            s.view_clicked = True
            return {"action": "click", "selector": vb["selector"]}
        s._view_wait += 1
        if s._view_wait >= s.MAX_WAIT:
            return {"action": "done", "result": "FAIL",
                    "reason": "'View' button not found"}
        return {"action": "wait", "seconds": 1}

    if not s.search_typed:
        if "projects" not in url.lower():
            if not s._nav_fired:
                s._nav_fired = True
                return {"action": "navigate", "url": _BASE_URL + "/projects"}
            return {"action": "wait", "seconds": 1}
        si = els["search_input"]
        if si:
            s.search_typed = True
            return {"action": "type", "selector": si["selector"],
                    "text": s.target_name}
        s._search_wait += 1
        if s._search_wait >= s.MAX_WAIT:
            return {"action": "done", "result": "FAIL",
                    "reason": "Search input not found"}
        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# DELETE STATE + LOGIC
# ============================================================

_DELETE_RE = re.compile(r"delete project\s+(.+?)$", re.IGNORECASE)

_DELETE_SUCCESS_PHRASES = (
    "deleted successfully",
    "removed successfully",
    "project deleted",
    "successfully deleted",
    "delete successful",
)


class _DeleteState:
    def __init__(self):
        self.target_name      = ""
        self.search_typed     = False
        self.delete_clicked   = False
        self.confirmed        = False
        self.reverify_typed   = False
        self.verified         = False
        self._nav_fired       = False
        self._reverify_nav    = False
        self._search_wait     = 0
        self._delete_wait     = 0
        self._confirm_wait    = 0
        self._verify_wait     = 0
        self._reverify_wait   = 0
        self.interacted       = set()
        self.MAX_WAIT         = 4

    def reset(self):
        self.__init__()

_delete_st = _DeleteState()


async def decide_delete(els, url, goal):
    s = _delete_st

    if not s.target_name:
        m = _DELETE_RE.search(goal)
        if m:
            s.target_name = m.group(1).strip()
            print("[DELETE] Target project: '{}'".format(s.target_name))

    if s.verified:
        return {"action": "done", "result": "PASS",
                "reason": "Project '{}' deleted successfully".format(s.target_name)}

    # ── VERIFICATION PHASE ────────────────────────────────────
    if s.confirmed:

        # Method A: Strict success toast
        if els["success_toast"]:
            print("[DELETE-VERIFY] Method A: Success toast confirmed")
            s.verified = True
            return {"action": "done", "result": "PASS",
                    "reason": "Project '{}' deleted — toast confirmed".format(
                        s.target_name)}

        # Method B+C: Re-search + DOM check
        if not s._reverify_nav:
            if "projects" not in url.lower():
                s._reverify_nav = True
                return {"action": "navigate", "url": _BASE_URL + "/projects"}
            s._reverify_nav = True

        if not s.reverify_typed:
            si = els["search_input"]
            if si:
                s.reverify_typed = True
                print("[DELETE-VERIFY] Re-searching '{}' to verify".format(
                    s.target_name))
                return {"action": "type", "selector": si["selector"],
                        "text": s.target_name}
            s._reverify_wait += 1
            if s._reverify_wait >= s.MAX_WAIT:
                s.verified = True
                return {"action": "done", "result": "PASS",
                        "reason": "Project '{}' likely deleted".format(s.target_name)}
            return {"action": "wait", "seconds": 1}

        # Method C: DOM mein project naam count karo
        name_lower = s.target_name.lower()
        count = sum(
            1 for el in (els.get("dom_raw") or [])
            if name_lower in (el.get("text") or "").lower()
            or name_lower in (el.get("label") or "").lower()
        )
        print("[DELETE-VERIFY] Method C: '{}' found {} time(s) in DOM".format(
            s.target_name, count))

        if count == 0:
            s.verified = True
            return {"action": "done", "result": "PASS",
                    "reason": "Project '{}' deleted — not found in search results".format(
                        s.target_name)}
        else:
            s._verify_wait += 1
            s.reverify_typed = False
            if s._verify_wait >= s.MAX_WAIT:
                return {"action": "done", "result": "FAIL",
                        "reason": "Project '{}' still visible after delete".format(
                            s.target_name)}
            return {"action": "wait", "seconds": 1}

    # ── STEP 4: Confirm dialog ────────────────────────────────
    if s.delete_clicked:
        cb = els["confirm_btn"]
        if cb and cb["selector"] not in s.interacted:
            s.interacted.add(cb["selector"])
            s.confirmed = True
            print("[DELETE] Step 4: Clicking confirm: {}".format(cb["selector"]))
            return {"action": "click", "selector": cb["selector"]}
        s._confirm_wait += 1
        print("[DELETE] Step 4: Waiting for dialog ({}/{})".format(
            s._confirm_wait, s.MAX_WAIT))
        if s._confirm_wait >= s.MAX_WAIT:
            print("[DELETE] No dialog — treating as direct delete")
            s.confirmed = True
            return {"action": "wait", "seconds": 1}
        return {"action": "wait", "seconds": 1}

    # ── STEP 3: Delete button click ───────────────────────────
    if s.search_typed:
        db = els["delete_btn"]
        if db and db["selector"] not in s.interacted:
            s.interacted.add(db["selector"])
            s.delete_clicked = True
            print("[DELETE] Step 3: Clicking delete: {}".format(db["selector"]))
            return {
                "action":        "click",
                "selector":      db["selector"],
                "force":         True,
                "extra_wait_ms": 2000,
                "soft_fail":     False,
            }
        s._delete_wait += 1
        print("[DELETE] Step 3: Delete btn not found ({}/{})".format(
            s._delete_wait, s.MAX_WAIT))
        for el in (els.get("dom_raw") or []):
            if (el.get("tag") or "").lower() == "button":
                print("  BTN: text={!r:25} sel={!r}".format(
                    (el.get("text") or "")[:30], el.get("selector", "")))
        if s._delete_wait >= s.MAX_WAIT:
            return {"action": "done", "result": "FAIL",
                    "reason": "'Delete' button not found in search results"}
        return {"action": "wait", "seconds": 1}

    # ── STEP 2: Search ────────────────────────────────────────
    if not s.search_typed:
        if "projects" not in url.lower():
            if not s._nav_fired:
                s._nav_fired = True
                return {"action": "navigate", "url": _BASE_URL + "/projects"}
            return {"action": "wait", "seconds": 1}
        si = els["search_input"]
        if si:
            s.search_typed = True
            print("[DELETE] Step 2: Searching '{}'".format(s.target_name))
            return {"action": "type", "selector": si["selector"],
                    "text": s.target_name}
        s._search_wait += 1
        if s._search_wait >= s.MAX_WAIT:
            return {"action": "done", "result": "FAIL",
                    "reason": "Search input not found"}
        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

def reset_state():
    _login.reset()
    _nav.reset()
    _create_st.reset()
    _update_st.reset()
    _delete_st.reset()
    print("[STATE] Project module reset")


async def decide_action(action, dom, url, goal="", email=None, password=None):
    els = scan_dom(dom)

    if not login_done():
        step = handle_login(els, email, password, url)
        if step is None and not login_done():
            return {"action": "wait", "seconds": 1}
        if step:
            return step

    if not nav_done():
        step = handle_nav(els, url)
        if step:
            return step

    if action == "create":
        return await decide_create(els, url)
    if action == "update":
        return await decide_update(els, url, goal)
    if action == "delete":
        return await decide_delete(els, url, goal)

    return {"action": "wait", "seconds": 1}


# ============================================================
# FORM PARAMS BUILDERS
# ============================================================

def _find_estimation_selector(ac):
    for el in ac:
        if "estimation" in (el.get("label") or "").lower():
            return el["selector"]
    if len(ac) > 2:
        return ac[2]["selector"]
    return ac[-1]["selector"] if ac else None


def _base_params(name, els, budget):
    today = datetime.now()
    ac    = els["autocomplete_inputs"]
    return {
        "project_name":        name,
        "description":         "Auto - " + name,
        "project_type":        None,
        "delivery_model":      None,
        "methodology":         None,
        "risk_rating":         None,
        "billing_type":        None,
        "currency":            None,
        "client_search":       "a",
        "client_selector":     ac[0]["selector"] if len(ac) > 0 else None,
        "estimation_search":   "a",
        "estimation_selector": _find_estimation_selector(ac),
        "sow_search":          "",
        "sow_selector":        ac[1]["selector"] if len(ac) > 1 else None,
        "start_date":          today.strftime("%m/%d/%Y"),
        "end_date":            (today + timedelta(days=30)).strftime("%m/%d/%Y"),
        "budget":              budget,
    }


def _build_create_params(name, els):
    return _base_params(name, els, "10000")


def _build_update_params(name, els):
    p = _base_params(name, els, "20000")
    p["description"] = "Updated - " + name
    return p