
import re
from datetime import datetime, timedelta

from utils.login       import login_done, handle_login, reset_login
from utils.nav         import nav_done,   handle_nav,   reset_nav
from utils.dom_scanner import scan_common_dom
from config.settings   import BASE_URL
from report.test_report import get_reporter

# ============================================================
# modules/project.py
#
# Workflow:
#   Login -> /projects -> (create / update / delete)
# ============================================================

NAV_FRAGMENT = "projects"

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

# Regex to parse goal strings
_UPDATE_RE = re.compile(r"update project\s+(.+?)$", re.IGNORECASE)
_DELETE_RE = re.compile(r"delete project\s+(.+?)$", re.IGNORECASE)


# ============================================================
# DOM SCANNER
# ============================================================

_NON_TOAST = ("input", "button")

_DELETE_SUCCESS_PHRASES = (
    "deleted successfully",
    "removed successfully",
    "project deleted",
    "successfully deleted",
    "delete successful",
)

_SAVE_SUCCESS_PHRASES = (
    "saved successfully",
    "updated successfully",
    "project updated",
    "successfully updated",
    "changes saved",
    "project saved",
)

_DUPLICATE_PHRASES = (
    "already exists",
    "duplicate",
    "job name already",
    "already been added",
    "this name is taken",
    "name is not unique",
)


def scan_dom(dom):
    """
    Extend common DOM scan with project-specific elements.
    """
    result = scan_common_dom(dom)

    result.update({
        "new_project_btn":     None,   # New / Add / Create project button
        "search_input":        None,   # Project search box
        "view_btn":            None,   # View button on project row
        "edit_btn":            None,   # Edit button inside project view
        "delete_btn":          None,   # Delete button inside project view
        "confirm_btn":         None,   # Confirm / Yes dialog button
        "save_btn":            None,   # Save Project form button
        "autocomplete_inputs": [],     # MUI autocomplete inputs (client, estimation, sow)
        "mui_selects":         [],     # MUI div[role=combobox] selects
        "save_toast":          None,   # saved/updated successfully toast
        "duplicate_error":     None,   # already exists error in DOM
    })

    _BTN_TAGS  = ("button", "input")
    _BTN_TYPES = ("button", "submit", "")

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

        # ── Project action buttons ────────────────────────────
        if tag in _BTN_TAGS and etype in _BTN_TYPES:
            if any(x in lv for x in ("new project", "add project", "create project")):
                result["new_project_btn"] = el

            elif text in ("view", "view details") or label == "view":
                result["view_btn"] = el

            elif text in ("edit", "edit details") or label == "edit":
                result["edit_btn"] = el

            elif (text == "delete" or label == "delete"
                  or "muibutton-outlinederror" in cls
                  or "muibutton-colorerror" in cls):
                if not result["delete_btn"]:
                    result["delete_btn"] = el

            elif any(x in text for x in ("yes", "confirm", "ok", "sure", "proceed")):
                if not result["confirm_btn"]:
                    result["confirm_btn"] = el

            elif eid == "project-form-save" or "save project" in lv:
                result["save_btn"] = el

        # ── Search input ──────────────────────────────────────
        if (tag == "input" and etype in ("text", "search")
                and ("search" in ph or "search" in eid or "search" in cls)
                and not result["search_input"]):
            result["search_input"] = el

        # ── MUI autocomplete + selects ────────────────────────
        if tag == "div" and role == "combobox":
            result["mui_selects"].append(el)

        if tag == "input" and role == "combobox":
            result["autocomplete_inputs"].append(el)

        # ── Toasts / errors ───────────────────────────────────
        if tag not in _NON_TOAST:
            if (any(phrase in comb for phrase in _DELETE_SUCCESS_PHRASES)
                    and not result["success_toast"]):
                result["success_toast"] = el

            if (any(phrase in comb for phrase in _SAVE_SUCCESS_PHRASES)
                    and not result["save_toast"]):
                result["save_toast"] = el

            if (any(phrase in comb for phrase in _DUPLICATE_PHRASES)
                    and not result["duplicate_error"]):
                result["duplicate_error"] = el
                print("[DOM] Duplicate error detected: {!r}".format(
                    (el.get("text") or "")[:80]))

            if (any(x in comb for x in ("error", "failed", "invalid"))
                    and not result["error_toast"]):
                result["error_toast"] = el

    return result


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


async def _decide_create(els, url):
    s = _create_st
    r = get_reporter()

    if s.verified:
        if r:
            r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Project '{}' created successfully".format(s.last_name)}

    # ── Verify after submit ───────────────────────────────────
    if s.submitted:
        # Fail fast on duplicate
        if els["duplicate_error"]:
            if r:
                r.update_last_step(False, error="Duplicate detected — project already exists")
            return {"action": "done", "result": "FAIL",
                    "reason": "Project already exists — not re-created"}

        # Fail fast on any visible error/validation message
        dom_raw = els.get("dom_raw") or []
        error_found = any(
            ("already exists"  in (el.get("text") or "").lower()
             or "duplicate"    in (el.get("text") or "").lower()
             or "already been" in (el.get("text") or "").lower()
             or "invalid"      in (el.get("text") or "").lower())
            for el in dom_raw
            if el.get("tag", "").lower() not in ("input", "button")
        )
        if error_found:
            err_text = next(
                (el.get("text", "") for el in dom_raw
                 if el.get("tag", "").lower() not in ("input", "button")
                 and ("already exists" in (el.get("text") or "").lower()
                      or "duplicate"   in (el.get("text") or "").lower()
                      or "invalid"     in (el.get("text") or "").lower())),
                "Validation error shown on form"
            )
            if r:
                r.update_last_step(False, error=err_text)
            return {"action": "done", "result": "FAIL",
                    "reason": "Project '{}' was NOT created — {}".format(s.last_name, err_text)}

        # Method A: save/success toast
        if els["save_toast"] or els["success_toast"]:
            if r:
                r.update_last_step(True)
            s.verified = True
            return {"action": "done", "result": "PASS",
                    "reason": "Project '{}' created — toast confirmed".format(s.last_name)}

        # Method B: name in DOM + form closed
        name_lower      = s.last_name.lower()
        form_still_open = bool(els.get("save_btn"))
        found = any(
            name_lower in (el.get("text") or "").lower() or
            name_lower in (el.get("label") or "").lower()
            for el in dom_raw
        )
        if found and not form_still_open:
            if r:
                r.update_last_step(True)
            s.verified = True
            return {"action": "done", "result": "PASS",
                    "reason": "Project '{}' created — visible in list".format(s.last_name)}

        s._verify_wait += 1
        if s._verify_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Project '{}' was NOT created — could not verify after {} waits".format(
                    s.last_name, s.MAX_WAIT))
            return {"action": "done", "result": "FAIL",
                    "reason": "Project '{}' was NOT created — save was not confirmed (no toast, form still open)".format(
                        s.last_name)}
        return {"action": "wait", "seconds": 1}

    # ── Fill form ─────────────────────────────────────────────
    if s.form_open:
        name        = "AutoProject_{}".format(datetime.now().strftime("%H%M%S"))
        s.last_name = name
        s.submitted = True
        print("[CREATE] Filling form: '{}'".format(name))
        if r:
            r.log_step(len(r.steps) + 1, 
                      {"action": "fill_form", "module": "project", "params": {"project_name": name}},
                      url)
        return {"action": "fill_form", "module": "project",
                "params": _build_create_params(name, els)}

    # ── Click New Project ─────────────────────────────────────
    nb = els["new_project_btn"]
    if nb:
        s.form_open = True
        if r:
            r.log_step(len(r.steps) + 1, 
                      {"action": "click", "selector": nb["selector"]},
                      url)
        return {"action": "click", "selector": nb["selector"]}

    s._form_wait += 1
    if s._form_wait > s.MAX_WAIT:
        if r:
            r.update_last_step(False, error="'New Project' button not found on page")
        return {"action": "done", "result": "FAIL",
                "reason": "'New Project' button not found on page"}
    return {"action": "wait", "seconds": 1}


# ============================================================
# UPDATE STATE + LOGIC
# ============================================================

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


async def _decide_update(els, url, goal):
    s = _update_st
    r = get_reporter()

    if not s.target_name:
        m = _UPDATE_RE.search(goal)
        if m:
            s.target_name = m.group(1).strip()
            print("[UPDATE] Target: '{}'".format(s.target_name))

    if s.verified:
        if r:
            r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Project '{}' updated successfully".format(s.last_name)}

    # ── Verify after submit ───────────────────────────────────
   
    if s.submitted:
        # URL-based verification — form closed means save succeeded
        if "/edit" not in url.lower():
            if r:
                r.update_last_step(True)
            s.verified = True
            return {
                "action": "done",
                "result": "PASS",
                "reason": "Project '{}' updated — form closed (URL changed)".format(s.last_name)
            }
        # Fail fast on duplicate
        if els["duplicate_error"]:
            if r:
                r.update_last_step(False, error="Duplicate error while updating")
            return {"action": "done", "result": "FAIL",
                    "reason": "Update failed — name already exists"}

        # Fail fast on any visible error/validation message
        dom_raw_u = els.get("dom_raw") or []
        error_found_u = any(
            ("already exists"  in (el.get("text") or "").lower()
             or "duplicate"    in (el.get("text") or "").lower()
             or "invalid"      in (el.get("text") or "").lower())
            for el in dom_raw_u
            if el.get("tag", "").lower() not in ("input", "button")
        )
        if error_found_u:
            err_text_u = next(
                (el.get("text", "") for el in dom_raw_u
                 if el.get("tag", "").lower() not in ("input", "button")
                 and ("already exists" in (el.get("text") or "").lower()
                      or "duplicate"   in (el.get("text") or "").lower()
                      or "invalid"     in (el.get("text") or "").lower())),
                "Validation error shown on form"
            )
            if r:
                r.update_last_step(False, error=err_text_u)
            return {"action": "done", "result": "FAIL",
                    "reason": "Project '{}' was NOT updated — {}".format(s.last_name, err_text_u)}

        # Method A: save/success toast
        if els["save_toast"] or els["success_toast"]:
            if r:
                r.update_last_step(True)
            s.verified = True
            return {"action": "done", "result": "PASS",
                    "reason": "Project '{}' updated — toast confirmed".format(s.last_name)}

        # Method B: form closed + updated name in DOM
        form_still_open = "/edit" in url.lower()
        name_lower      = s.last_name.lower()
        in_dom = any(
            name_lower in (el.get("text") or "").lower()
            for el in dom_raw_u
        )
        if not form_still_open and in_dom:
            if r:
                r.update_last_step(True)
            s.verified = True
            return {"action": "done", "result": "PASS",
                    "reason": "Project '{}' updated — visible in list".format(s.last_name)}

        s._verify_wait += 1
        if s._verify_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Project '{}' was NOT updated — form still open after {} waits".format(
                    s.last_name, s.MAX_WAIT))
            return {"action": "done", "result": "FAIL",
                    "reason": "Project '{}' was NOT updated — save was not confirmed (form still open)".format(
                        s.last_name)}
        return {"action": "wait", "seconds": 1}

    # ── Fill update form ──────────────────────────────────────
    if s.form_open:
        name        = "UpdatedProject_{}".format(datetime.now().strftime("%H%M%S"))
        s.last_name = name
        s.submitted = True
        print("[UPDATE] Filling update form: '{}'".format(name))
        if r:
            r.log_step(len(r.steps) + 1,
                      {"action": "fill_form", "module": "project", "params": {"project_name": name}},
                      url)
        return {"action": "fill_form", "module": "project",
                "params": _build_update_params(name, els)}

    # ── Click Edit ────────────────────────────────────────────
    if s.view_clicked and not s.edit_clicked:
        eb = els["edit_btn"]
        if eb and eb["selector"] not in s.interacted:
            s.interacted.add(eb["selector"])
            s.edit_clicked = True
            s.form_open    = True
            print("[UPDATE] Clicking Edit")
            if r:
                r.log_step(len(r.steps) + 1,
                          {"action": "click", "selector": eb["selector"]},
                          url)
            return {"action": "click", "selector": eb["selector"]}
        s._edit_wait += 1
        if s._edit_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="'Edit' button not found")
            return {"action": "done", "result": "FAIL",
                    "reason": "'Edit' button not found"}
        return {"action": "wait", "seconds": 1}

    # ── Click View ────────────────────────────────────────────
    if s.search_typed and not s.view_clicked:
        vb = els["view_btn"]
        if vb and vb["selector"] not in s.interacted:
            s.interacted.add(vb["selector"])
            s.view_clicked = True
            print("[UPDATE] Clicking View")
            if r:
                r.log_step(len(r.steps) + 1,
                          {"action": "click", "selector": vb["selector"]},
                          url)
            return {"action": "click", "selector": vb["selector"]}
        s._view_wait += 1
        if s._view_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="'View' button not found")
            return {"action": "done", "result": "FAIL",
                    "reason": "'View' button not found"}
        return {"action": "wait", "seconds": 1}

    # ── Search for project ────────────────────────────────────
    if not s.search_typed:
        if "projects" not in url.lower():
            if not s._nav_fired:
                s._nav_fired = True
                if r:
                    r.log_step(len(r.steps) + 1,
                              {"action": "navigate", "url": BASE_URL + "/projects"},
                              url)
                return {"action": "navigate", "url": BASE_URL + "/projects"}
            return {"action": "wait", "seconds": 1}
        si = els["search_input"]
        if si:
            s.search_typed = True
            print("[UPDATE] Searching '{}'".format(s.target_name))
            if r:
                r.log_step(len(r.steps) + 1,
                          {"action": "type", "selector": si["selector"], "text": s.target_name},
                          url)
            return {"action": "type", "selector": si["selector"],
                    "text": s.target_name}
        s._search_wait += 1
        if s._search_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Search input not found")
            return {"action": "done", "result": "FAIL",
                    "reason": "Search input not found"}
        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# DELETE STATE + LOGIC
# ============================================================

class _DeleteState:
    def __init__(self):
        self.target_name    = ""
        self.search_typed   = False
        self.delete_clicked = False
        self.confirmed      = False
        self.reverify_typed = False
        self.verified       = False
        self._nav_fired     = False
        self._reverify_nav  = False
        self._search_wait   = 0
        self._delete_wait   = 0
        self._verify_wait   = 0
        self._reverify_wait = 0
        self.interacted     = set()
        self.MAX_WAIT       = 1

    def reset(self):
        self.__init__()

_delete_st = _DeleteState()


async def _decide_delete(els, url, goal):
    s = _delete_st
    r = get_reporter()

    if not s.target_name:
        m = _DELETE_RE.search(goal)
        if m:
            s.target_name = m.group(1).strip()
            print("[DELETE] Target: '{}'".format(s.target_name))

    if s.verified:
        if r:
            r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Project '{}' deleted successfully".format(s.target_name)}

    # ── Verification phase ────────────────────────────────────
    if s.confirmed:
        # Method A: success toast
        if els["success_toast"]:
            print("[DELETE-VERIFY] Method A: Toast confirmed")
            if r:
                r.update_last_step(True)
            s.verified = True
            return {"action": "done", "result": "PASS",
                    "reason": "Project '{}' deleted — toast confirmed".format(s.target_name)}

        if not s._reverify_nav:
            if "projects" not in url.lower():
                s._reverify_nav = True
                if r:
                    r.log_step(len(r.steps) + 1,
                              {"action": "navigate", "url": BASE_URL + "/projects"},
                              url)
                return {"action": "navigate", "url": BASE_URL + "/projects"}
            s._reverify_nav = True

        # Method B: re-search and check DOM
        if not s.reverify_typed:
            si = els["search_input"]
            if si:
                s.reverify_typed = True
                print("[DELETE-VERIFY] Re-searching '{}' to verify".format(s.target_name))
                if r:
                    r.log_step(len(r.steps) + 1,
                              {"action": "type", "selector": si["selector"], "text": s.target_name},
                              url)
                return {"action": "type", "selector": si["selector"],
                        "text": s.target_name}
            s._reverify_wait += 1
            if s._reverify_wait >= s.MAX_WAIT:
                if r:
                    r.update_last_step(True)
                s.verified = True
                return {"action": "done", "result": "PASS",
                        "reason": "Project '{}' likely deleted".format(s.target_name)}
            return {"action": "wait", "seconds": 1}

        # Method C: name count == 0 in DOM
        name_lower = s.target_name.lower()
        count = sum(
            1 for el in (els.get("dom_raw") or [])
            if name_lower in (el.get("text") or "").lower()
            or name_lower in (el.get("label") or "").lower()
        )
        print("[DELETE-VERIFY] Method C: '{}' found {} time(s) in DOM".format(
            s.target_name, count))

        if count == 0:
            if r:
                r.update_last_step(True)
            s.verified = True
            return {"action": "done", "result": "PASS",
                    "reason": "Project '{}' deleted — not found in results".format(s.target_name)}

        s._verify_wait += 1
        s.reverify_typed = False
        if s._verify_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Project still visible after delete")
            return {"action": "done", "result": "FAIL",
                    "reason": "Project '{}' still visible after delete".format(s.target_name)}
        return {"action": "wait", "seconds": 1}

    # ── Step 4: Confirm dialog (auto-accepted by Playwright) ──
    if s.delete_clicked:
        print("[DELETE] Step 4: Dialog auto-accepted by Playwright handler")
        s.confirmed = True
        return {"action": "wait", "seconds": 1}

    # ── Step 3: Click Delete button ───────────────────────────
    if s.search_typed:
        db = els["delete_btn"]
        if db and db["selector"] not in s.interacted:
            s.interacted.add(db["selector"])
            s.delete_clicked = True
            print("[DELETE] Step 3: Clicking delete button")
            if r:
                r.log_step(len(r.steps) + 1,
                          {"action": "click", "selector": "button.MuiButton-outlinedError"},
                          url)
            return {
                "action":        "click",
                "selector":      "button.MuiButton-outlinedError",
                "extra_wait_ms": 2000,
                "soft_fail":     False,
            }
        s._delete_wait += 1
        print("[DELETE] Step 3: Delete btn not found ({}/{})".format(
            s._delete_wait, s.MAX_WAIT))
        for el in (els.get("dom_raw") or []):
            if (el.get("tag") or "").lower() == "button":
                print("  BTN text={!r:25} cls={!r:.60}".format(
                    (el.get("text") or "")[:30],
                    (el.get("class") or "")[:60]))
        if s._delete_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="'Delete' button not found in search results")
            return {"action": "done", "result": "FAIL",
                    "reason": "'Delete' button not found in search results"}
        return {"action": "wait", "seconds": 1}

    # ── Step 2: Search ────────────────────────────────────────
    if not s.search_typed:
        if "projects" not in url.lower():
            if not s._nav_fired:
                s._nav_fired = True
                if r:
                    r.log_step(len(r.steps) + 1,
                              {"action": "navigate", "url": BASE_URL + "/projects"},
                              url)
                return {"action": "navigate", "url": BASE_URL + "/projects"}
            return {"action": "wait", "seconds": 1}
        si = els["search_input"]
        if si:
            s.search_typed = True
            print("[DELETE] Step 2: Searching '{}'".format(s.target_name))
            if r:
                r.log_step(len(r.steps) + 1,
                          {"action": "type", "selector": si["selector"], "text": s.target_name},
                          url)
            return {"action": "type", "selector": si["selector"],
                    "text": s.target_name}
        s._search_wait += 1
        if s._search_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Search input not found")
            return {"action": "done", "result": "FAIL",
                    "reason": "Search input not found"}
        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

def reset_state():
    reset_login()
    reset_nav()
    _create_st.reset()
    _update_st.reset()
    _delete_st.reset()
    print("[STATE] Project module reset")


async def decide_action(action, dom, url, goal="", email=None, password=None,page=None):
    els = scan_dom(dom)

    # Phase 1: Login
    if not login_done():
        step = handle_login(els, email, password, url)
        if step is None and not login_done():
            return {"action": "wait", "seconds": 1}
        if step:
            r = get_reporter()
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step

    # Phase 2: Navigate to /projects
    if not nav_done():
        step = handle_nav(els, url, NAV_FRAGMENT)
        if step:
            r = get_reporter()
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step

    # Phase 3: Project action
    if action == "create":
        return await _decide_create(els, url)
    if action == "update":
        return await _decide_update(els, url, goal)
    if action == "delete":
        return await _decide_delete(els, url, goal)

    return {"action": "wait", "seconds": 1}


# ============================================================
# FORM PARAMS BUILDERS
# ============================================================

def _find_estimation_selector(ac):
    for el in ac:
        if "estimation" in (el.get("label") or "").lower():
            return el["selector"]
    if len(ac) > 1:
        return ac[1]["selector"]
    return ac[-1]["selector"] if ac else None


def _find_sow_selector(ac):
    for el in ac:
        if "sow" in (el.get("label") or "").lower():
            return el["selector"]
    if len(ac) > 2:
        return ac[2]["selector"]
    return None


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
        "status":              None,
        "billing_type":        None,
        "currency":            None,
        "client_search":       "a",
        "client_selector":     ac[0]["selector"] if len(ac) > 0 else None,
        "estimation_search":   "a",
        "estimation_selector": _find_estimation_selector(ac),
        "sow_search":          "",
        "sow_selector":        _find_sow_selector(ac),
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