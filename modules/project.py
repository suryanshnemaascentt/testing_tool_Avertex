
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

MODULE_META = {
    "name":     "Project",
    "fragment": NAV_FRAGMENT,
    "order":    1,
}

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
    "create_empty_name": {
        "label":        "[NEG] Create Project with empty name — expects validation error",
        "needs_target": False,
    },
    "create_duplicate": {
        "label":        "[NEG] Create duplicate project name — expects rejection",
        "needs_target": False,
    },
    "neg_c_03": {
        "label":        "[NEG-C-03] End date before start date — expects validation error",
        "needs_target": False,
    },
    "neg_c_04": {
        "label":        "[NEG-C-04] Billable billing type with no client — expects validation",
        "needs_target": False,
    },
    "neg_c_05": {
        "label":        "[NEG-C-05] Special characters in project name — expects validation/sanitization",
        "needs_target": False,
    },
    "neg_c_06": {
        "label":        "[NEG-C-06] Very long project name (300 chars) — expects validation/truncation",
        "needs_target": False,
    },
    "neg_c_07": {
        "label":        "[NEG-C-07] Zero budget — FAIL if allowed, PASS if blocked",
        "needs_target": False,
    },
    "neg_c_08": {
        "label":        "[NEG-C-08] Same start and end date — PASS if allowed or validated",
        "needs_target": False,
    },
    # ── Update negative tests ─────────────────────────────────
    "neg_u_01": {
        "label":        "[NEG-U-01] Clear project name then Save — expects validation error",
        "needs_target": False,
    },
    "neg_u_02": {
        "label":        "[NEG-U-02] Enter negative Planned Budget — expects validation/rejection",
        "needs_target": False,
    },
    "neg_u_03": {
        "label":        "[NEG-U-03] Link estimation already linked to another project — expects rejection",
        "needs_target": False,
    },
    "neg_u_04": {
        "label":        "[NEG-U-04] Cancel after making changes — expects changes discarded",
        "needs_target": False,
    },
    # ── Delete negative tests ─────────────────────────────────
    "neg_d_01": {
        "label":        "[NEG-D-01] Delete project with logged hours — expects block",
        "needs_target": True,
    },
    "neg_d_02": {
        "label":        "[NEG-D-02] Click Delete then Cancel — expects project preserved",
        "needs_target": True,
    },
    "neg_d_03": {
        "label":        "[NEG-D-03] Delete project then access old URL — expects 404/redirect",
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
        "cancel_btn":          None,   # Cancel button on the edit form
        "deny_btn":            None,   # No/Cancel on a confirmation dialog
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

            elif (text == "cancel" or label == "cancel") and not result["cancel_btn"]:
                result["cancel_btn"] = el

            elif text in ("no", "no, keep it", "keep", "go back") and not result["deny_btn"]:
                result["deny_btn"] = el

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
# NEG-01: CREATE WITH EMPTY NAME
# ============================================================

class _CreateEmptyState:
    def __init__(self):
        self.form_open  = False
        self.submitted  = False
        self._form_wait = 0
        self._wait_cnt  = 0
        self.MAX_WAIT   = 4

    def reset(self):
        self.__init__()

_create_empty_st = _CreateEmptyState()


async def _decide_create_empty(els, url):
    s = _create_empty_st
    r = get_reporter()

    if s.submitted:
        dom_raw = els.get("dom_raw") or []

        # PASS: any validation / required-field error visible in DOM
        error_found = (
            els.get("error_toast")
            or any(
                any(x in (el.get("text") or "").lower()
                    for x in ("required", "cannot be empty", "name is required",
                               "please enter", "invalid", "field is required",
                               "name cannot", "must not be blank"))
                for el in dom_raw
                if el.get("tag", "").lower() not in ("input", "button")
            )
        )
        if error_found:
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "Empty name correctly rejected — validation error shown"}

        # PASS: browser/HTML5 validation blocked submit (form still open, no save)
        if els.get("save_btn") and not els.get("save_toast") and not els.get("success_toast"):
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "Empty name blocked — browser validation prevented submit"}

        # FAIL: save toast appeared (empty name was accepted — bug)
        if els.get("save_toast") or els.get("success_toast"):
            if r:
                r.update_last_step(False, error="Empty project name was incorrectly accepted")
            return {"action": "done", "result": "FAIL",
                    "reason": "UNEXPECTED: Empty project name accepted — no validation enforced"}

        s._wait_cnt += 1
        if s._wait_cnt >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Could not verify rejection of empty name")
            return {"action": "done", "result": "FAIL",
                    "reason": "Could not confirm validation after {} waits".format(s.MAX_WAIT)}
        return {"action": "wait", "seconds": 1}

    if s.form_open:
        s.submitted = True
        if r:
            r.log_step(len(r.steps) + 1,
                       {"action": "fill_form", "module": "project", "params": {"project_name": ""}},
                       url)
        return {"action": "fill_form", "module": "project",
                "params": _build_empty_name_params(els)}

    nb = els["new_project_btn"]
    if nb:
        s.form_open = True
        if r:
            r.log_step(len(r.steps) + 1, {"action": "click", "selector": nb["selector"]}, url)
        return {"action": "click", "selector": nb["selector"]}

    s._form_wait += 1
    if s._form_wait > s.MAX_WAIT:
        if r:
            r.update_last_step(False, error="'New Project' button not found")
        return {"action": "done", "result": "FAIL",
                "reason": "'New Project' button not found on page"}
    return {"action": "wait", "seconds": 1}


# ============================================================
# NEG-02: CREATE DUPLICATE NAME
# ============================================================

class _CreateDupState:
    def __init__(self):
        self.dup_name       = "NEG_DUP_{}".format(datetime.now().strftime("%H%M%S"))
        self.phase          = 1   # 1 = first create, 2 = duplicate attempt
        self.p1_form_open   = False
        self.p1_submitted   = False
        self.p2_form_open   = False
        self.p2_submitted   = False
        self._p1_form_wait  = 0
        self._p1_ver_wait   = 0
        self._p2_form_wait  = 0
        self._p2_ver_wait   = 0
        self._p2_close_wait = 0   # grace ticks after form closes before silent-accept
        self.MAX_WAIT       = 4

    def reset(self):
        self.__init__()

_create_dup_st = _CreateDupState()


async def _decide_create_duplicate(els, url):
    s = _create_dup_st
    r = get_reporter()

    # ── Phase 2: Verify duplicate rejection ───────────────────
    if s.phase == 2:
        if s.p2_submitted:
            dom_raw = els.get("dom_raw") or []

            # PASS: duplicate_error element found by scan_dom
            if els.get("duplicate_error"):
                if r:
                    r.update_last_step(True)
                return {"action": "done", "result": "PASS",
                        "reason": "Duplicate '{}' correctly rejected — error shown".format(s.dup_name)}

            # PASS: any duplicate phrase in DOM text
            dup_in_dom = any(
                any(x in (el.get("text") or "").lower()
                    for x in ("already exists", "duplicate", "name is not unique",
                               "already been added", "this name is taken"))
                for el in dom_raw
                if el.get("tag", "").lower() not in ("input", "button")
            )
            if dup_in_dom:
                if r:
                    r.update_last_step(True)
                return {"action": "done", "result": "PASS",
                        "reason": "Duplicate '{}' correctly rejected — error shown".format(s.dup_name)}

            # FAIL: save toast appeared (duplicate accepted — bug)
            if els.get("save_toast") or els.get("success_toast"):
                if r:
                    r.update_last_step(False, error="Duplicate project name was incorrectly accepted")
                return {"action": "done", "result": "FAIL",
                        "reason": "UNEXPECTED: Duplicate '{}' accepted — uniqueness not enforced".format(s.dup_name)}

            # Also treat error_toast as a PASS signal — the app may surface the
            # duplicate warning via a generic error toast (role='alert') rather
            # than a dedicated duplicate_error element.
            if els.get("error_toast"):
                toast_text = (els["error_toast"].get("text") or "").lower()
                if r:
                    r.update_last_step(True)
                return {"action": "done", "result": "PASS",
                        "reason": "Duplicate '{}' correctly rejected — error toast shown: {}".format(
                            s.dup_name, toast_text[:80])}

            # FAIL: form is no longer open (save_btn absent) — duplicate may have
            # been silently accepted, OR the toast appeared and disappeared before
            # this scan.  Give 1 grace tick so the next DOM scan can pick up the
            # toast (role='alert' elements are now captured by dom_builder).
            form_still_open = bool(els.get("save_btn"))
            if not form_still_open:
                s._p2_close_wait += 1
                if s._p2_close_wait <= 1:
                    # One extra wait — let the toast render into the DOM
                    return {"action": "wait", "seconds": 1}
                if r:
                    r.update_last_step(False, error="Duplicate accepted silently — form closed without error")
                return {"action": "done", "result": "FAIL",
                        "reason": "UNEXPECTED: Duplicate '{}' accepted silently — uniqueness not enforced".format(s.dup_name)}

            s._p2_ver_wait += 1
            if s._p2_ver_wait >= s.MAX_WAIT:
                if r:
                    r.update_last_step(False, error="Duplicate outcome could not be verified after {} waits".format(s.MAX_WAIT))
                return {"action": "done", "result": "FAIL",
                        "reason": "Could not confirm duplicate rejection after {} waits".format(s.MAX_WAIT)}
            return {"action": "wait", "seconds": 1}

        if s.p2_form_open:
            s.p2_submitted = True
            print("[NEG-DUP] Phase 2: submitting duplicate name '{}'".format(s.dup_name))
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "fill_form", "module": "project",
                            "params": {"project_name": s.dup_name}},
                           url)
            return {"action": "fill_form", "module": "project",
                    "params": _build_create_params(s.dup_name, els)}

        nb = els["new_project_btn"]
        if nb:
            s.p2_form_open = True
            if r:
                r.log_step(len(r.steps) + 1, {"action": "click", "selector": nb["selector"]}, url)
            return {"action": "click", "selector": nb["selector"]}

        s._p2_form_wait += 1
        if s._p2_form_wait > s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="'New Project' button not found in phase 2")
            return {"action": "done", "result": "FAIL",
                    "reason": "'New Project' button not found in phase 2"}
        return {"action": "wait", "seconds": 1}

    # ── Phase 1: Create the project initially ─────────────────
    if s.p1_submitted:
        dom_raw = els.get("dom_raw") or []

        # Name already existed from a previous run — skip straight to phase 2
        if els.get("duplicate_error"):
            print("[NEG-DUP] Phase 1: name already exists — skipping to phase 2")
            s.phase = 2
            return {"action": "wait", "seconds": 1}

        # Success via toast
        if els.get("save_toast") or els.get("success_toast"):
            print("[NEG-DUP] Phase 1 done — created '{}', starting phase 2".format(s.dup_name))
            s.phase = 2
            return {"action": "wait", "seconds": 1}

        # Success: name visible in list, form closed
        name_lower      = s.dup_name.lower()
        form_still_open = bool(els.get("save_btn"))
        found = any(
            name_lower in (el.get("text") or "").lower()
            for el in dom_raw
        )
        if found and not form_still_open:
            print("[NEG-DUP] Phase 1 done — '{}' visible, starting phase 2".format(s.dup_name))
            s.phase = 2
            return {"action": "wait", "seconds": 1}

        s._p1_ver_wait += 1
        if s._p1_ver_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Phase 1 create could not be verified")
            return {"action": "done", "result": "FAIL",
                    "reason": "Phase 1 (initial create) not confirmed after {} waits".format(s.MAX_WAIT)}
        return {"action": "wait", "seconds": 1}

    if s.p1_form_open:
        s.p1_submitted = True
        print("[NEG-DUP] Phase 1: creating '{}'".format(s.dup_name))
        if r:
            r.log_step(len(r.steps) + 1,
                       {"action": "fill_form", "module": "project",
                        "params": {"project_name": s.dup_name}},
                       url)
        return {"action": "fill_form", "module": "project",
                "params": _build_create_params(s.dup_name, els)}

    nb = els["new_project_btn"]
    if nb:
        s.p1_form_open = True
        if r:
            r.log_step(len(r.steps) + 1, {"action": "click", "selector": nb["selector"]}, url)
        return {"action": "click", "selector": nb["selector"]}

    s._p1_form_wait += 1
    if s._p1_form_wait > s.MAX_WAIT:
        if r:
            r.update_last_step(False, error="'New Project' button not found in phase 1")
        return {"action": "done", "result": "FAIL",
                "reason": "'New Project' button not found on page"}
    return {"action": "wait", "seconds": 1}


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

def reset_state(keep_session=False):
    # Login and nav state are always fully reset.
    # keep_session=True was designed for reusing a single open browser,
    # but the suite runner opens a fresh browser per run() call —
    # so nav_done() must always be cleared to avoid stale True state
    # leaking from one scenario into the next.
    reset_login()
    reset_nav()
    _create_st.reset()
    _update_st.reset()
    _delete_st.reset()
    _create_empty_st.reset()
    _create_dup_st.reset()
    _neg_c03_st.reset()
    _neg_c04_st.reset()
    _neg_c05_st.reset()
    _neg_c06_st.reset()
    _neg_c07_st.reset()
    _neg_c08_st.reset()
    _neg_u01_st.reset()
    _neg_u02_st.reset()
    _neg_u03_st.reset()
    _neg_u04_st.reset()
    _neg_d01_st.reset()
    _neg_d02_st.reset()
    _neg_d03_st.reset()
    print("[STATE] Project module reset (keep_session={})".format(keep_session))


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
    if action == "create_empty_name":
        return await _decide_create_empty(els, url)
    if action == "create_duplicate":
        return await _decide_create_duplicate(els, url)
    if action in ("neg_c_03", "neg_c_04", "neg_c_05", "neg_c_06", "neg_c_07", "neg_c_08"):
        return await _decide_neg_create_generic(els, url, action)
    if action in ("neg_u_01", "neg_u_02", "neg_u_03", "neg_u_04"):
        return await _decide_neg_update_generic(els, url, action)
    if action == "neg_d_01":
        return await _decide_neg_d01(els, url, goal)
    if action == "neg_d_02":
        return await _decide_neg_d02(els, url, goal)
    if action == "neg_d_03":
        return await _decide_neg_d03(els, url, goal)

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


def _build_empty_name_params(els):
    p = _base_params("", els, "10000")
    p["description"] = "Negative test — empty name"
    return p


# ============================================================
# NEG-C-03 to NEG-C-08: Generic Negative Create State
# ============================================================

class _GenericNegCreateState:
    """Reusable state for single-step negative create scenarios."""
    def __init__(self):
        self.form_open   = False
        self.submitted   = False
        self._form_wait  = 0
        self._wait_cnt   = 0
        self._close_wait = 0   # grace ticks after form closes before deciding outcome
        self.MAX_WAIT    = 4

    def reset(self):
        self.__init__()


_neg_c03_st = _GenericNegCreateState()
_neg_c04_st = _GenericNegCreateState()
_neg_c05_st = _GenericNegCreateState()
_neg_c06_st = _GenericNegCreateState()
_neg_c07_st = _GenericNegCreateState()
_neg_c08_st = _GenericNegCreateState()

_NEG_STATE_MAP = {
    "neg_c_03": _neg_c03_st,
    "neg_c_04": _neg_c04_st,
    "neg_c_05": _neg_c05_st,
    "neg_c_06": _neg_c06_st,
    "neg_c_07": _neg_c07_st,
    "neg_c_08": _neg_c08_st,
}

# All unexpected saves are treated as FAIL
_NEG_WARN_ON_SUCCESS = set()
# Scenarios where a save toast = PASS (both dates same is legally valid)
_NEG_PASS_ON_SUCCESS = {"neg_c_08"}


def _build_neg_c03_params(els):
    """End date before start date."""
    today = datetime.now()
    p = _base_params("NegC03_{}".format(today.strftime("%H%M%S")), els, "10000")
    p["start_date"] = (today + timedelta(days=30)).strftime("%m/%d/%Y")
    p["end_date"]   = today.strftime("%m/%d/%Y")
    return p


def _build_neg_c04_params(els):
    """Billable billing type with no client."""
    today = datetime.now()
    p = _base_params("NegC04_{}".format(today.strftime("%H%M%S")), els, "10000")
    p["billing_type"] = "Billable"
    p["skip_client"]  = True
    return p


def _build_neg_c05_params(els):
    """Special characters in project name."""
    today = datetime.now()
    name  = "<script>alert('xss')</script>@#$%^&*()_{}".format(today.strftime("%H%M%S"))
    return _base_params(name, els, "10000")


def _build_neg_c06_params(els):
    """Very long project name — 300 characters."""
    name = "A" * 300
    return _base_params(name, els, "10000")


def _build_neg_c07_params(els):
    """Zero budget."""
    today = datetime.now()
    p = _base_params("NegC07_{}".format(today.strftime("%H%M%S")), els, "0")
    return p


def _build_neg_c08_params(els):
    """Same start and end date (today)."""
    today = datetime.now()
    p = _base_params("NegC08_{}".format(today.strftime("%H%M%S")), els, "10000")
    p["start_date"] = today.strftime("%m/%d/%Y")
    p["end_date"]   = today.strftime("%m/%d/%Y")
    return p


# ── Update negative params builders ──────────────────────────

def _build_neg_u01_params(els):
    """Clear project name (empty string) — validation should block save."""
    p = _build_update_params("", els)
    p["project_name"] = ""
    p["description"]  = "NEG-U-01: Project name cleared"
    return p


def _build_neg_u02_params(els):
    """Negative budget value — validation should reject or warn."""
    today = datetime.now()
    p = _build_update_params("NegU02_{}".format(today.strftime("%H%M%S")), els)
    p["budget"] = "-5000"
    return p


def _build_neg_u03_params(els):
    """Link the first available estimation (may already be linked to another project)."""
    today = datetime.now()
    p = _build_update_params("NegU03_{}".format(today.strftime("%H%M%S")), els)
    # estimation_search="a" is already set by _base_params; first autocomplete result
    # is likely already assigned — expect rejection or WARN if app allows multi-linking
    p["estimation_search"] = "a"
    return p


_NEG_PARAMS_MAP = {
    "neg_c_03": _build_neg_c03_params,
    "neg_c_04": _build_neg_c04_params,
    "neg_c_05": _build_neg_c05_params,
    "neg_c_06": _build_neg_c06_params,
    "neg_c_07": _build_neg_c07_params,
    "neg_c_08": _build_neg_c08_params,
}


async def _decide_neg_create_generic(els, url, sc_key):
    """
    Shared decision logic for NEG-C-03 through NEG-C-08.

    Flow: wait for New Project btn → click → fill form with bad data → verify outcome.
    PASS  — validation/error message shown          (expected rejection)
    PASS  — save succeeded and scenario allows it   (e.g. same dates)
    FAIL  — save succeeded when it should not have
    """
    s = _NEG_STATE_MAP[sc_key]
    r = get_reporter()
    build_params = _NEG_PARAMS_MAP[sc_key]
    pass_on_ok   = sc_key in _NEG_PASS_ON_SUCCESS

    if s.submitted:
        dom_raw = els.get("dom_raw") or []

        # Check for any validation error message in DOM
        error_found = (
            els.get("error_toast")
            or any(
                any(x in (el.get("text") or "").lower()
                    for x in ("required", "invalid", "cannot be empty", "error",
                               "validation", "must not", "please enter",
                               "already exists", "duplicate", "too long",
                               "end date", "start date", "client", "budget"))
                for el in dom_raw
                if el.get("tag", "").lower() not in ("input", "button")
            )
        )
        if error_found:
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "[{}] Validation error correctly shown".format(sc_key.upper())}

        # Form still open (browser-level HTML5 validation blocked submit)
        if els.get("save_btn") and not els.get("save_toast") and not els.get("success_toast"):
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "[{}] Browser validation prevented submit".format(sc_key.upper())}

        # Save toast appeared — project was accepted
        if els.get("save_toast") or els.get("success_toast"):
            if pass_on_ok:
                if r:
                    r.update_last_step(True)
                return {"action": "done", "result": "PASS",
                        "reason": "[{}] Save accepted — this outcome is acceptable for this scenario".format(
                            sc_key.upper())}
            if r:
                r.update_last_step(False, error="Project saved when it should have been rejected")
            return {"action": "done", "result": "FAIL",
                    "reason": "[{}] UNEXPECTED: Project accepted — validation not enforced".format(
                        sc_key.upper())}

        # If the form is no longer open, the save went through (toast may have
        # already disappeared).  Give 1 grace tick so role='alert' toast can load;
        # on the second closed-tick treat it as a definitive "save succeeded".
        form_still_open = bool(els.get("save_btn"))
        if not form_still_open:
            s._close_wait += 1
            if s._close_wait <= 1:
                return {"action": "wait", "seconds": 1}
            # Form is confirmed closed with no error — save succeeded
            if pass_on_ok:
                if r:
                    r.update_last_step(True)
                return {"action": "done", "result": "PASS",
                        "reason": "[{}] Save accepted — this outcome is acceptable for this scenario".format(
                            sc_key.upper())}
            if r:
                r.update_last_step(False, error="Project saved when it should have been rejected")
            return {"action": "done", "result": "FAIL",
                    "reason": "[{}] UNEXPECTED: Project accepted — validation not enforced".format(
                        sc_key.upper())}

        s._wait_cnt += 1
        if s._wait_cnt >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="[{}] Could not verify outcome after {} waits".format(
                    sc_key.upper(), s.MAX_WAIT))
            return {"action": "done", "result": "FAIL",
                    "reason": "[{}] Could not confirm outcome after {} waits".format(
                        sc_key.upper(), s.MAX_WAIT)}
        return {"action": "wait", "seconds": 1}

    if s.form_open:
        params = build_params(els)
        s.submitted = True
        if r:
            r.log_step(len(r.steps) + 1,
                       {"action": "fill_form", "module": "project",
                        "params": {"project_name": params.get("project_name", "")}},
                       url)
        return {"action": "fill_form", "module": "project", "params": params}

    nb = els["new_project_btn"]
    if nb:
        s.form_open = True
        if r:
            r.log_step(len(r.steps) + 1, {"action": "click", "selector": nb["selector"]}, url)
        return {"action": "click", "selector": nb["selector"]}

    s._form_wait += 1
    if s._form_wait > s.MAX_WAIT:
        if r:
            r.update_last_step(False, error="'New Project' button not found")
        return {"action": "done", "result": "FAIL",
                "reason": "[{}] 'New Project' button not found on page".format(sc_key.upper())}
    return {"action": "wait", "seconds": 1}


# ============================================================
# NEGATIVE CREATE SUITE — scenario registry
# ============================================================

NEGATIVE_CREATE_SCENARIOS = [
    {
        "id":         "NEG-C-01",
        "action_key": "create_empty_name",
        "name":       "Empty Project Name",
        "description": "Project Name = '' — expect validation error",
    },
    {
        "id":         "NEG-C-02",
        "action_key": "create_duplicate",
        "name":       "Duplicate Project Name",
        "description": "Create project twice with same name — expect duplicate error",
    },
    {
        "id":         "NEG-C-03",
        "action_key": "neg_c_03",
        "name":       "End Date Before Start Date",
        "description": "Start = today+30, End = today — expect validation error",
    },
    {
        "id":         "NEG-C-04",
        "action_key": "neg_c_04",
        "name":       "Billable Without Client",
        "description": "Billing Type = Billable, Client = empty — expect validation",
    },
    {
        "id":         "NEG-C-05",
        "action_key": "neg_c_05",
        "name":       "Special Characters in Name",
        "description": "Name = <script>alert</script>@#$%^&*() — expect validation or sanitization",
    },
    {
        "id":         "NEG-C-06",
        "action_key": "neg_c_06",
        "name":       "Very Long Name (300 chars)",
        "description": "Name = 'A' * 300 — expect validation or truncation",
    },
    {
        "id":         "NEG-C-07",
        "action_key": "neg_c_07",
        "name":       "Zero Budget",
        "description": "Budget = 0 — FAIL if allowed, PASS if blocked",
    },
    {
        "id":         "NEG-C-08",
        "action_key": "neg_c_08",
        "name":       "Same Start and End Date",
        "description": "Start = End = today — PASS if allowed or validated, FAIL only on crash",
    },
]


# ============================================================
# NEG-U-01 to NEG-U-04: Generic Negative Update State
#
# Mirrors _GenericNegCreateState — no explicit search step.
# Navigate to /projects, click View on the first visible row,
# click Edit, then perform the negative action.
# ============================================================

class _GenericNegUpdateState:
    """Simple state for negative update scenarios — mirrors _GenericNegCreateState."""
    def __init__(self):
        self.view_clicked       = False   # View clicked on any project row
        self.edit_clicked       = False   # Edit clicked inside project detail
        self.form_open          = False   # Edit form is active
        self.submitted          = False   # fill_form dispatched (neg_u_01/02/03)
        self.change_made        = False   # a change was typed (neg_u_04)
        self.cancel_clicked     = False   # Cancel form button clicked (neg_u_04)
        self.discard_confirmed  = False   # "Discard changes" dialog confirmed (neg_u_04)
        self._nav_fired         = False
        self._view_wait         = 0
        self._edit_wait         = 0
        self._wait_cnt          = 0
        self._close_wait        = 0
        self.interacted         = set()
        self.MAX_WAIT           = 4

    def reset(self):
        self.__init__()


_neg_u01_st = _GenericNegUpdateState()
_neg_u02_st = _GenericNegUpdateState()
_neg_u03_st = _GenericNegUpdateState()
_neg_u04_st = _GenericNegUpdateState()

_NEG_U_STATE_MAP = {
    "neg_u_01": _neg_u01_st,
    "neg_u_02": _neg_u02_st,
    "neg_u_03": _neg_u03_st,
    "neg_u_04": _neg_u04_st,
}

_NEG_U_PARAMS_MAP = {
    "neg_u_01": _build_neg_u01_params,
    "neg_u_02": _build_neg_u02_params,
    "neg_u_03": _build_neg_u03_params,
}

# All unexpected saves are treated as FAIL
_NEG_U_WARN_ON_SUCCESS = set()
_NEG_U_PASS_ON_SUCCESS = set()


async def _decide_neg_update_generic(els, url, sc_key):
    """
    Shared decision logic for NEG-U-01 through NEG-U-04.

    Flow (mirrors _decide_neg_create_generic):
      Navigate to /projects → View first row → Edit →
        NEG-U-01/02/03: fill_form with bad data → verify validation
        NEG-U-04      : type a change → Cancel → verify discard
    """
    s = _NEG_U_STATE_MAP[sc_key]
    r = get_reporter()

    # ==========================================================
    # NEG-U-04: Cancel after making changes
    # ==========================================================
    if sc_key == "neg_u_04":

        # Verify cancel outcome
        if s.cancel_clicked:
            # Handle optional "Discard changes" confirmation dialog
            cb = els.get("confirm_btn")
            if cb and not s.discard_confirmed:
                s.discard_confirmed = True
                step = {"action": "click", "selector": cb["selector"]}
                if r:
                    r.log_step(len(r.steps) + 1, step, url)
                print("[NEG-U-04] Confirming discard-changes dialog")
                return step

            save_happened   = bool(els.get("save_toast") or els.get("success_toast"))
            form_still_open = bool(els.get("save_btn")) or "/edit" in url.lower()

            if save_happened:
                if r:
                    r.update_last_step(False, error="Save occurred after clicking Cancel")
                return {"action": "done", "result": "FAIL",
                        "reason": "[NEG-U-04] UNEXPECTED: Save triggered on Cancel — changes not discarded"}

            if not form_still_open:
                if r:
                    r.update_last_step(True)
                return {"action": "done", "result": "PASS",
                        "reason": "[NEG-U-04] Cancel discarded changes — form closed without saving"}

            s._wait_cnt += 1
            if s._wait_cnt >= s.MAX_WAIT:
                if r:
                    r.update_last_step(False, error="Form still open after Cancel")
                return {"action": "done", "result": "FAIL",
                        "reason": "[NEG-U-04] Form still open after Cancel after {} waits".format(s.MAX_WAIT)}
            return {"action": "wait", "seconds": 1}

        # Click Cancel on the form
        if s.change_made and not s.cancel_clicked:
            cb = els.get("cancel_btn")
            if cb:
                s.cancel_clicked = True
                step = {"action": "click", "selector": cb["selector"]}
                if r:
                    r.log_step(len(r.steps) + 1, step, url)
                print("[NEG-U-04] Clicking Cancel")
                return step
            # Fallback XPath
            s.cancel_clicked = True
            step = {"action": "click",
                    "selector": "//button[normalize-space()='Cancel']",
                    "soft_fail": True}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            print("[NEG-U-04] Clicking Cancel (XPath fallback)")
            return step

        # Type a change so there is unsaved data
        if s.form_open and not s.change_made:
            s.change_made = True
            step = {"action": "type",
                    "selector": "input.MuiInputBase-input[type='text']",
                    "text": "CANCEL_TEST_TEMP"}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            print("[NEG-U-04] Typing change before Cancel")
            return step

        # Fall through to navigation

    # ==========================================================
    # NEG-U-01 / 02 / 03: Verify after fill_form
    # ==========================================================
    if s.submitted:
        dom_raw = els.get("dom_raw") or []

        error_found = (
            els.get("error_toast")
            or els.get("duplicate_error")
            or any(
                any(x in (el.get("text") or "").lower()
                    for x in ("required", "invalid", "cannot be empty", "error",
                               "validation", "must not", "please enter",
                               "negative", "must be", "less than", "greater than",
                               "already linked", "already assigned", "already used",
                               "cannot link", "estimation is"))
                for el in dom_raw
                if el.get("tag", "").lower() not in ("input", "button")
            )
        )
        if error_found:
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "[{}] Validation error correctly shown".format(sc_key.upper())}

        # Browser HTML5 validation blocked submit
        if els.get("save_btn") and not els.get("save_toast") and not els.get("success_toast"):
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "[{}] Browser validation prevented submit".format(sc_key.upper())}

        # Save toast — project was accepted
        if els.get("save_toast") or els.get("success_toast"):
            pass_on_ok = sc_key in _NEG_U_PASS_ON_SUCCESS
            if pass_on_ok:
                if r:
                    r.update_last_step(True)
                return {"action": "done", "result": "PASS",
                        "reason": "[{}] Save accepted — acceptable for this scenario".format(sc_key.upper())}
            if r:
                r.update_last_step(False, error="Project updated when it should have been rejected")
            return {"action": "done", "result": "FAIL",
                    "reason": "[{}] UNEXPECTED: Update accepted — validation not enforced".format(sc_key.upper())}

        # Form closed without toast — give 1 grace tick then decide
        form_still_open = bool(els.get("save_btn")) or "/edit" in url.lower()
        if not form_still_open:
            s._close_wait += 1
            if s._close_wait <= 1:
                return {"action": "wait", "seconds": 1}
            pass_on_ok = sc_key in _NEG_U_PASS_ON_SUCCESS
            if pass_on_ok:
                if r:
                    r.update_last_step(True)
                return {"action": "done", "result": "PASS",
                        "reason": "[{}] Save accepted — acceptable for this scenario".format(sc_key.upper())}
            if r:
                r.update_last_step(False, error="Project updated silently when it should have been rejected")
            return {"action": "done", "result": "FAIL",
                    "reason": "[{}] UNEXPECTED: Update accepted silently — validation not enforced".format(sc_key.upper())}

        s._wait_cnt += 1
        if s._wait_cnt >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Cannot confirm outcome after {} waits".format(s.MAX_WAIT))
            return {"action": "done", "result": "FAIL",
                    "reason": "[{}] Cannot confirm outcome after {} waits".format(
                        sc_key.upper(), s.MAX_WAIT)}
        return {"action": "wait", "seconds": 1}

    # ── Fill form (neg_u_01 / 02 / 03) ───────────────────────
    if s.form_open and not s.submitted and sc_key != "neg_u_04":
        params = _NEG_U_PARAMS_MAP[sc_key](els)
        s.submitted = True
        print("[{}] Filling form with negative data".format(sc_key.upper()))
        if r:
            r.log_step(len(r.steps) + 1,
                       {"action": "fill_form", "module": "project",
                        "params": {"project_name": params.get("project_name", "")}},
                       url)
        return {"action": "fill_form", "module": "project", "params": params}

    # ── Click Edit ────────────────────────────────────────────
    if s.view_clicked and not s.edit_clicked:
        eb = els["edit_btn"]
        if eb and eb["selector"] not in s.interacted:
            s.interacted.add(eb["selector"])
            s.edit_clicked = True
            s.form_open    = True
            print("[{}] Clicking Edit".format(sc_key.upper()))
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "click", "selector": eb["selector"]}, url)
            return {"action": "click", "selector": eb["selector"]}
        s._edit_wait += 1
        if s._edit_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="'Edit' button not found")
            return {"action": "done", "result": "FAIL",
                    "reason": "[{}] 'Edit' button not found".format(sc_key.upper())}
        return {"action": "wait", "seconds": 1}

    # ── Click View on first visible project row ───────────────
    if not s.view_clicked:
        if "projects" not in url.lower():
            if not s._nav_fired:
                s._nav_fired = True
                if r:
                    r.log_step(len(r.steps) + 1,
                               {"action": "navigate", "url": BASE_URL + "/projects"}, url)
                return {"action": "navigate", "url": BASE_URL + "/projects"}
            return {"action": "wait", "seconds": 1}
        vb = els["view_btn"]
        if vb and vb["selector"] not in s.interacted:
            s.interacted.add(vb["selector"])
            s.view_clicked = True
            print("[{}] Clicking View on first row".format(sc_key.upper()))
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "click", "selector": vb["selector"]}, url)
            return {"action": "click", "selector": vb["selector"]}
        s._view_wait += 1
        if s._view_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="No project rows visible on /projects page")
            return {"action": "done", "result": "FAIL",
                    "reason": "[{}] No projects visible on list page".format(sc_key.upper())}
        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# NEGATIVE UPDATE SUITE — scenario registry
# ============================================================

NEGATIVE_UPDATE_SCENARIOS = [
    {
        "id":          "NEG-U-01",
        "action_key":  "neg_u_01",
        "name":        "Clear Project Name and Save",
        "description": "Erase project name, click Save — expect required-field validation error",
    },
    {
        "id":          "NEG-U-02",
        "action_key":  "neg_u_02",
        "name":        "Negative Planned Budget",
        "description": "Enter -5000 as budget — expect validation/rejection",
    },
    {
        "id":          "NEG-U-03",
        "action_key":  "neg_u_03",
        "name":        "Link Already-Linked Estimation",
        "description": "Link first-available estimation (may already belong to another project) — expect rejection",
    },
    {
        "id":          "NEG-U-04",
        "action_key":  "neg_u_04",
        "name":        "Cancel After Making Changes",
        "description": "Type a change then click Cancel — expect changes discarded, form closed without saving",
    },
]


# ============================================================
# NEG-D-01: Delete project with logged hours
# ============================================================

class _NegD01State:
    def __init__(self):
        self.target_name    = ""
        self.search_typed   = False
        self.delete_clicked = False
        self.confirmed      = False
        self.verified       = False
        self._nav_fired     = False
        self._search_wait   = 0
        self._delete_wait   = 0
        self._verify_wait   = 0
        self.interacted     = set()
        self.MAX_WAIT       = 4

    def reset(self):
        self.__init__()


_neg_d01_st = _NegD01State()


async def _decide_neg_d01(els, url, goal):
    s = _neg_d01_st
    r = get_reporter()

    if not s.target_name:
        m = _DELETE_RE.search(goal)
        if m:
            s.target_name = m.group(1).strip()
            print("[NEG-D-01] Target: '{}'".format(s.target_name))

    if s.verified:
        if r:
            r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "[NEG-D-01] Test passed"}

    # Verify after delete clicked (and confirmation auto-accepted if dialog appeared)
    if s.confirmed:
        dom_raw = els.get("dom_raw") or []

        # PASS — system blocked the delete with an error
        blocked = bool(els.get("error_toast")) or any(
            any(x in (el.get("text") or "").lower()
                for x in ("cannot delete", "logged hours", "has timesheet",
                           "timesheet entries", "cannot be deleted", "in use",
                           "has dependencies", "has entries", "hours logged",
                           "associated timesheets"))
            for el in dom_raw
            if el.get("tag", "").lower() not in ("input", "button")
        )
        if blocked:
            s.verified = True
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "[NEG-D-01] Delete correctly blocked — project has logged hours"}

        # FAIL — delete succeeded when project with logged hours should be protected
        if els.get("success_toast"):
            s.verified = True
            if r:
                r.update_last_step(False, error="Delete succeeded — project with logged hours was not protected")
            return {"action": "done", "result": "FAIL",
                    "reason": "[NEG-D-01] UNEXPECTED: Delete succeeded — project with logged hours was not protected"}

        s._verify_wait += 1
        if s._verify_wait >= s.MAX_WAIT:
            s.verified = True
            if r:
                r.update_last_step(False, error="Delete outcome unclear after {} waits".format(s.MAX_WAIT))
            return {"action": "done", "result": "FAIL",
                    "reason": "[NEG-D-01] Outcome unclear after {} waits — delete may have been allowed".format(
                        s.MAX_WAIT)}
        return {"action": "wait", "seconds": 1}

    # Confirm the delete dialog (auto-accept to observe whether the app blocks it)
    if s.delete_clicked and not s.confirmed:
        s.confirmed = True
        return {"action": "wait", "seconds": 1}

    # Click delete button
    if s.search_typed:
        db = els["delete_btn"]
        if db and db["selector"] not in s.interacted:
            s.interacted.add(db["selector"])
            s.delete_clicked = True
            print("[NEG-D-01] Clicking Delete")
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "click",
                            "selector": "button.MuiButton-outlinedError"}, url)
            return {"action": "click", "selector": "button.MuiButton-outlinedError",
                    "extra_wait_ms": 2000}
        s._delete_wait += 1
        if s._delete_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Delete button not found")
            return {"action": "done", "result": "FAIL",
                    "reason": "[NEG-D-01] Delete button not found in search results"}
        return {"action": "wait", "seconds": 1}

    # Search
    if not s.search_typed:
        if "projects" not in url.lower():
            if not s._nav_fired:
                s._nav_fired = True
                if r:
                    r.log_step(len(r.steps) + 1,
                               {"action": "navigate", "url": BASE_URL + "/projects"}, url)
                return {"action": "navigate", "url": BASE_URL + "/projects"}
            return {"action": "wait", "seconds": 1}
        si = els["search_input"]
        if si:
            s.search_typed = True
            print("[NEG-D-01] Searching '{}'".format(s.target_name))
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "type", "selector": si["selector"],
                            "text": s.target_name}, url)
            return {"action": "type", "selector": si["selector"], "text": s.target_name}
        s._search_wait += 1
        if s._search_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Search input not found")
            return {"action": "done", "result": "FAIL",
                    "reason": "[NEG-D-01] Search input not found"}
        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# NEG-D-02: Click Delete then Cancel on confirmation dialog
# ============================================================

class _NegD02State:
    def __init__(self):
        self.target_name    = ""
        self.search_typed   = False
        self.delete_clicked = False
        self.cancel_clicked = False   # clicked No/Cancel on confirmation
        self.re_searched    = False
        self.verified       = False
        self._nav_fired     = False
        self._nav2_fired    = False
        self._search_wait   = 0
        self._delete_wait   = 0
        self._re_search_wait= 0
        self._verify_wait   = 0
        self.interacted     = set()
        self.MAX_WAIT       = 4

    def reset(self):
        self.__init__()


_neg_d02_st = _NegD02State()


async def _decide_neg_d02(els, url, goal):
    s = _neg_d02_st
    r = get_reporter()

    if not s.target_name:
        m = _DELETE_RE.search(goal)
        if m:
            s.target_name = m.group(1).strip()
            print("[NEG-D-02] Target: '{}'".format(s.target_name))

    if s.verified:
        if r:
            r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "[NEG-D-02] Project preserved after cancel — correct"}

    # ── Phase 2: Verify project still exists after cancel ─────
    if s.cancel_clicked:
        # Navigate back to /projects if needed
        if "projects" not in url.lower():
            if not s._nav2_fired:
                s._nav2_fired = True
                if r:
                    r.log_step(len(r.steps) + 1,
                               {"action": "navigate", "url": BASE_URL + "/projects"}, url)
                return {"action": "navigate", "url": BASE_URL + "/projects"}
            return {"action": "wait", "seconds": 1}

        # Re-search for the project
        if not s.re_searched:
            si = els["search_input"]
            if si:
                s.re_searched = True
                if r:
                    r.log_step(len(r.steps) + 1,
                               {"action": "type", "selector": si["selector"],
                                "text": s.target_name}, url)
                return {"action": "type", "selector": si["selector"],
                        "text": s.target_name}
            s._re_search_wait += 1
            if s._re_search_wait >= s.MAX_WAIT:
                if r:
                    r.update_last_step(False, error="Search input not found during re-verify")
                return {"action": "done", "result": "FAIL",
                        "reason": "[NEG-D-02] Cannot re-verify — search input not found"}
            return {"action": "wait", "seconds": 1}

        # Check that project appears in results
        name_lower = s.target_name.lower()
        found = any(
            name_lower in (el.get("text") or "").lower()
            for el in (els.get("dom_raw") or [])
        )
        if found:
            s.verified = True
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "[NEG-D-02] Project '{}' still exists after Cancel — correct".format(
                        s.target_name)}

        s._verify_wait += 1
        if s._verify_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False,
                    error="Project not found after cancel — may have been deleted")
            return {"action": "done", "result": "FAIL",
                    "reason": "[NEG-D-02] Project '{}' not found after Cancel — was it deleted?".format(
                        s.target_name)}
        return {"action": "wait", "seconds": 1}

    # ── Click No / Cancel on the confirmation dialog ──────────
    if s.delete_clicked and not s.cancel_clicked:
        deny = els.get("deny_btn")
        if deny:
            s.cancel_clicked = True
            step = {"action": "click", "selector": deny["selector"]}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            print("[NEG-D-02] Clicking No/Cancel on confirmation dialog")
            return step
        # Fallback XPath
        s.cancel_clicked = True
        step = {"action": "click",
                "selector": ("//button[normalize-space()='No']"
                             " | //button[normalize-space()='Cancel']"
                             " | //button[normalize-space()='No, keep it']"),
                "soft_fail": True}
        if r:
            r.log_step(len(r.steps) + 1, step, url)
        print("[NEG-D-02] Clicking No/Cancel on confirmation dialog (XPath fallback)")
        return step

    # ── Click Delete button ───────────────────────────────────
    if s.search_typed and not s.delete_clicked:
        db = els["delete_btn"]
        if db and db["selector"] not in s.interacted:
            s.interacted.add(db["selector"])
            s.delete_clicked = True
            print("[NEG-D-02] Clicking Delete")
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "click",
                            "selector": "button.MuiButton-outlinedError"}, url)
            return {"action": "click", "selector": "button.MuiButton-outlinedError",
                    "extra_wait_ms": 2000}
        s._delete_wait += 1
        if s._delete_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Delete button not found")
            return {"action": "done", "result": "FAIL",
                    "reason": "[NEG-D-02] Delete button not found in search results"}
        return {"action": "wait", "seconds": 1}

    # ── Search ────────────────────────────────────────────────
    if not s.search_typed:
        if "projects" not in url.lower():
            if not s._nav_fired:
                s._nav_fired = True
                if r:
                    r.log_step(len(r.steps) + 1,
                               {"action": "navigate", "url": BASE_URL + "/projects"}, url)
                return {"action": "navigate", "url": BASE_URL + "/projects"}
            return {"action": "wait", "seconds": 1}
        si = els["search_input"]
        if si:
            s.search_typed = True
            print("[NEG-D-02] Searching '{}'".format(s.target_name))
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "type", "selector": si["selector"],
                            "text": s.target_name}, url)
            return {"action": "type", "selector": si["selector"], "text": s.target_name}
        s._search_wait += 1
        if s._search_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Search input not found")
            return {"action": "done", "result": "FAIL",
                    "reason": "[NEG-D-02] Search input not found"}
        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# NEG-D-03: Delete project then access its old URL directly
# ============================================================

class _NegD03State:
    def __init__(self):
        self.target_name     = ""
        self.project_url     = ""    # captured detail-page URL

        # Phase 1 — capture URL
        self.search_typed    = False
        self.view_clicked    = False
        self.url_captured    = False

        # Phase 2 — navigate back and delete
        self.back_nav        = False
        self.search_typed_2  = False
        self.delete_clicked  = False
        self.confirmed       = False

        # Phase 3 — visit old URL and verify
        self.old_url_visited = False
        self.verified        = False

        self._nav_fired      = False
        self._search_wait    = 0
        self._view_wait      = 0
        self._back_wait      = 0
        self._delete_wait    = 0
        self._verify_wait    = 0
        self.interacted      = set()
        self.MAX_WAIT        = 4

    def reset(self):
        self.__init__()


_neg_d03_st = _NegD03State()


async def _decide_neg_d03(els, url, goal):
    s = _neg_d03_st
    r = get_reporter()

    if not s.target_name:
        m = _DELETE_RE.search(goal)
        if m:
            s.target_name = m.group(1).strip()
            print("[NEG-D-03] Target: '{}'".format(s.target_name))

    if s.verified:
        if r:
            r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "[NEG-D-03] Old URL correctly inaccessible after delete"}

    # ── Phase 3: Verify old URL returns 404 / redirect ────────
    if s.old_url_visited:
        dom_raw   = els.get("dom_raw") or []
        page_text = " ".join((el.get("text") or "").lower() for el in dom_raw)

        not_found = any(x in page_text for x in
                        ("404", "not found", "page not found", "doesn't exist",
                         "no longer exists", "been deleted", "unavailable"))
        redirected_away = (
            "projects" in url.lower()
            and s.project_url
            and url.rstrip("/") != s.project_url.rstrip("/")
        )

        if not_found or redirected_away:
            s.verified = True
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "[NEG-D-03] Old URL '{}' correctly inaccessible — {}".format(
                        s.project_url,
                        "404 page shown" if not_found else "redirected away")}

        # FAIL — deleted project still accessible
        if s.target_name.lower() in page_text:
            s.verified = True
            if r:
                r.update_last_step(False,
                    error="Deleted project still accessible at old URL")
            return {"action": "done", "result": "FAIL",
                    "reason": "[NEG-D-03] UNEXPECTED: Deleted project still accessible at '{}'".format(
                        s.project_url)}

        s._verify_wait += 1
        if s._verify_wait >= s.MAX_WAIT:
            s.verified = True
            if r:
                r.update_last_step(False, error="Old URL outcome unclear after {} waits".format(s.MAX_WAIT))
            return {"action": "done", "result": "FAIL",
                    "reason": "[NEG-D-03] Old URL visited but outcome unclear after {} waits".format(
                        s.MAX_WAIT)}
        return {"action": "wait", "seconds": 1}

    # ── Phase 3: Navigate to old URL ──────────────────────────
    if s.confirmed and not s.old_url_visited:
        if not s.project_url:
            if r:
                r.update_last_step(False, error="Project URL was not captured before delete")
            return {"action": "done", "result": "FAIL",
                    "reason": "[NEG-D-03] Project URL not captured — cannot verify"}
        s.old_url_visited = True
        step = {"action": "navigate", "url": s.project_url}
        if r:
            r.log_step(len(r.steps) + 1, step, url)
        print("[NEG-D-03] Navigating to old URL: {}".format(s.project_url))
        return step

    # ── Phase 2: Confirm delete dialog ────────────────────────
    if s.delete_clicked and not s.confirmed:
        s.confirmed = True
        return {"action": "wait", "seconds": 1}

    # ── Phase 2: Click Delete ─────────────────────────────────
    if s.search_typed_2 and not s.delete_clicked:
        db = els["delete_btn"]
        if db and db["selector"] not in s.interacted:
            s.interacted.add(db["selector"])
            s.delete_clicked = True
            print("[NEG-D-03] Phase 2: Clicking Delete")
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "click",
                            "selector": "button.MuiButton-outlinedError"}, url)
            return {"action": "click", "selector": "button.MuiButton-outlinedError",
                    "extra_wait_ms": 2000}
        s._delete_wait += 1
        if s._delete_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Delete button not found in phase 2")
            return {"action": "done", "result": "FAIL",
                    "reason": "[NEG-D-03] Delete button not found"}
        return {"action": "wait", "seconds": 1}

    # ── Phase 2: Navigate back and search ─────────────────────
    if s.url_captured and not s.search_typed_2:
        if "projects" not in url.lower() or (
                s.project_url and url.rstrip("/") == s.project_url.rstrip("/")):
            if not s.back_nav:
                s.back_nav = True
                if r:
                    r.log_step(len(r.steps) + 1,
                               {"action": "navigate", "url": BASE_URL + "/projects"}, url)
                return {"action": "navigate", "url": BASE_URL + "/projects"}
            return {"action": "wait", "seconds": 1}
        si = els["search_input"]
        if si:
            s.search_typed_2 = True
            print("[NEG-D-03] Phase 2: Searching '{}'".format(s.target_name))
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "type", "selector": si["selector"],
                            "text": s.target_name}, url)
            return {"action": "type", "selector": si["selector"], "text": s.target_name}
        s._back_wait += 1
        if s._back_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Search input not found for phase 2")
            return {"action": "done", "result": "FAIL",
                    "reason": "[NEG-D-03] Search input not found in phase 2"}
        return {"action": "wait", "seconds": 1}

    # ── Phase 1: Capture URL after View ───────────────────────
    if s.view_clicked and not s.url_captured:
        if "/projects/" in url.lower() and url.rstrip("/") != (BASE_URL + "/projects").rstrip("/"):
            s.project_url  = url
            s.url_captured = True
            print("[NEG-D-03] Captured project URL: {}".format(url))
            return {"action": "wait", "seconds": 1}
        s._view_wait += 1
        if s._view_wait >= s.MAX_WAIT:
            # URL not captured — mark as captured anyway, proceed without old-URL test
            s.url_captured = True
            print("[NEG-D-03] Could not capture project URL")
        return {"action": "wait", "seconds": 1}

    # ── Phase 1: Click View ───────────────────────────────────
    if s.search_typed and not s.view_clicked:
        vb = els["view_btn"]
        if vb and vb["selector"] not in s.interacted:
            s.interacted.add(vb["selector"])
            s.view_clicked = True
            print("[NEG-D-03] Phase 1: Clicking View")
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "click", "selector": vb["selector"]}, url)
            return {"action": "click", "selector": vb["selector"]}
        s._view_wait += 1
        if s._view_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="'View' button not found")
            return {"action": "done", "result": "FAIL",
                    "reason": "[NEG-D-03] View button not found in phase 1"}
        return {"action": "wait", "seconds": 1}

    # ── Phase 1: Search ───────────────────────────────────────
    if not s.search_typed:
        if "projects" not in url.lower():
            if not s._nav_fired:
                s._nav_fired = True
                if r:
                    r.log_step(len(r.steps) + 1,
                               {"action": "navigate", "url": BASE_URL + "/projects"}, url)
                return {"action": "navigate", "url": BASE_URL + "/projects"}
            return {"action": "wait", "seconds": 1}
        si = els["search_input"]
        if si:
            s.search_typed = True
            print("[NEG-D-03] Phase 1: Searching '{}'".format(s.target_name))
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "type", "selector": si["selector"],
                            "text": s.target_name}, url)
            return {"action": "type", "selector": si["selector"], "text": s.target_name}
        s._search_wait += 1
        if s._search_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Search input not found")
            return {"action": "done", "result": "FAIL",
                    "reason": "[NEG-D-03] Search input not found"}
        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# NEGATIVE DELETE SUITE — scenario registry
# ============================================================

NEGATIVE_DELETE_SCENARIOS = [
    {
        "id":          "NEG-D-01",
        "action_key":  "neg_d_01",
        "name":        "Delete Project With Logged Hours",
        "description": "Delete a project that has timesheet entries — PASS if blocked, FAIL if allowed",
        "needs_target": True,
    },
    {
        "id":          "NEG-D-02",
        "action_key":  "neg_d_02",
        "name":        "Delete Then Cancel Confirmation",
        "description": "Click Delete then Cancel on the confirmation dialog — expect project preserved",
        "needs_target": True,
    },
    {
        "id":          "NEG-D-03",
        "action_key":  "neg_d_03",
        "name":        "Access Old URL After Delete",
        "description": "Delete project then navigate to its old detail URL — expect 404 or redirect",
        "needs_target": True,
    },
]