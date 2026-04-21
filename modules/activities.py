import re
import random
from datetime import datetime, timedelta

from utils.login       import login_done, handle_login, reset_login
from utils.nav         import nav_done,   handle_nav,   reset_nav
from utils.dom_scanner import scan_common_dom
from config.settings   import BASE_URL
from report.test_report import get_reporter

# ============================================================
# modules/activity.py
#
# Workflow:
#   Login -> /projects -> search project -> View ->
#   Activities tab -> Add Activity -> fill form -> tick button
# ============================================================

NAV_FRAGMENT = "projects"

ACTIONS = {
    "add_activities": {
        "label":        "Create new Activity in a job of  Project ",
        "needs_target": ["Project name", "Job name", "Activities name"],
    },
}

ACTION_KEYS = list(ACTIONS.keys())

_ADD_ACTIVITIES_RE = re.compile(
    r"add_activities\s+project\s+(.+?)\s*\|\s*job\s+(.+?)\s*\|\s*activities\s+(.+?)$",
    re.IGNORECASE
)
_ADD_ACTIVITIES_RE_SIMPLE = re.compile(
    r"add_activities\s+project\s+(.+?)$", re.IGNORECASE
)

# ============================================================
# DOM SCANNER
# ============================================================

def scan_dom(dom):
    result = scan_common_dom(dom)
    result.update({
        "nav_projects":        None,
        "search_input":        None,
        "view_btn":            None,
        "activities_tab":      None,
        "add_activity_btn":    None,
        "activity_name_input": None,
        "save_toast":          None,   # saved/updated successfully toast
        "dom_raw":             dom,    # raw list passed through for verification
    })

    _NON_TOAST = ("input", "button")

    _SAVE_SUCCESS_PHRASES = (
        "saved successfully",
        "updated successfully",
        "activity added",
        "successfully added",
        "changes saved",
        "activity saved",
    )

    _NAV_TAGS  = ("a", "li", "span")
    _BTN_TAGS  = ("button", "input")
    _BTN_TYPES = ("button", "submit", "")

    for el in dom:
        tag   = (el.get("tag")         or "").lower()
        etype = (el.get("type")        or "").lower()
        eid   = (el.get("id")          or "").lower()
        label = (el.get("label")       or "").lower().strip()
        text  = (el.get("text")        or "").lower().strip()
        role  = (el.get("role")        or "").lower()
        ph    = (el.get("placeholder") or "").lower()
        cls   = (el.get("class")       or "").lower()
        lv    = label + " " + text
        comb  = lv + " " + eid + " " + ph + " " + cls

        # Nav link
        if tag in _NAV_TAGS and "project" in comb and not result["nav_projects"]:
            result["nav_projects"] = el

        # Search input
        if (tag == "input" and etype in ("text", "search")
                and ("search" in ph or "search" in eid or "search" in cls)
                and not result["search_input"]):
            result["search_input"] = el

        # View button
        if tag in _BTN_TAGS and etype in _BTN_TYPES:
            if text in ("view", "view details") or label == "view":
                if not result["view_btn"]:
                    result["view_btn"] = el

        # Activities tab
        if tag == "button" and role == "tab" and "activit" in text and not result["activities_tab"]:
            result["activities_tab"] = el
        if eid == "project-activities-tab" and not result["activities_tab"]:
            result["activities_tab"] = el

        # Add Activity button
        if tag in _BTN_TAGS and ("add activity" in lv or "add activity" in comb):
            if not result["add_activity_btn"]:
                result["add_activity_btn"] = el

        # Activity name input
        if (tag == "input" and etype == "text"
                and ("task" in ph or "activity" in ph or "name" in ph)
                and not result["activity_name_input"]):
            result["activity_name_input"] = el

        # Save / success toast
        if tag not in _NON_TOAST:
            if (any(phrase in comb for phrase in _SAVE_SUCCESS_PHRASES)
                    and not result["save_toast"]):
                result["save_toast"] = el

    return result


# ============================================================
# ADD ACTIVITY STATE
# ============================================================

class _AddActivityState:
    def __init__(self):
        self.project_name           = ""
        self.job_name               = ""
        self.activity_name_override = ""

        # Step flags
        self.search_typed       = False
        self.view_clicked       = False
        self.activities_clicked = False
        self.add_clicked        = False
        self.form_filled        = False
        self.submitted          = False
        self.verified           = False

        # Navigation
        self._nav_fired         = False

        # Wait counters
        self._search_wait       = 0
        self._view_wait         = 0
        self._activities_wait   = 0
        self._add_wait          = 0
        self._submit_wait       = 0

        self.interacted         = set()
        self.MAX_WAIT           = 4

    def reset(self):
        self.__init__()

_add_act_st = _AddActivityState()


# ============================================================
# ADD ACTIVITY LOGIC
# ============================================================

async def _decide_add_activity(els, url, goal):
    s = _add_act_st
    r = get_reporter()

    # ── Parse project / job / activity name from goal ─────────
    if not s.project_name:
        m = _ADD_ACTIVITIES_RE.search(goal)
        if m:
            s.project_name           = m.group(1).strip()
            s.job_name               = m.group(2).strip()
            s.activity_name_override = m.group(3).strip()
            print("[ACTIVITY] Project: '{}' | Job: '{}' | Activity: '{}'".format(
                s.project_name, s.job_name, s.activity_name_override))
        else:
            m2 = _ADD_ACTIVITIES_RE_SIMPLE.search(goal)
            if m2:
                s.project_name = m2.group(1).strip()
                print("[ACTIVITY] Project target: '{}'".format(s.project_name))

    # ── Already done ──────────────────────────────────────────
    if s.verified:
        if r:
            r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Activity '{}' added to project '{}'".format(
                    s.activity_name_override or "activity", s.project_name)}

    # ── Step 7: Verify after submit ───────────────────────────
    if s.submitted:
        dom_raw          = els.get("dom_raw") or []
        act_name_target  = (s.activity_name_override or "").lower()

        # ── Signal 1: success toast / save toast present ──────
        toast_found = bool(els.get("success_toast") or els.get("save_toast"))
        if not toast_found:
            toast_found = any(
                ("success"   in (el.get("text")  or "").lower()
                 or "added"   in (el.get("text")  or "").lower()
                 or "created" in (el.get("text")  or "").lower()
                 or "snackbar" in (el.get("class") or "").lower()
                 or "toast"    in (el.get("class") or "").lower())
                for el in dom_raw
            )

        # ── Signal 2: activity name visible in a table/list row ─
        activity_row_found = bool(act_name_target) and any(
            act_name_target in (el.get("text") or "").lower()
            for el in dom_raw
            if el.get("tag", "").lower() in ("td", "tr", "span", "div", "li")
        )

        # ── Signal 3: inline form inputs gone (form closed) ───
        form_closed = not bool(els.get("activity_name_input"))

        # ── Error signal: duplicate / validation error visible ──
        error_found = any(
            ("already exists"  in (el.get("text") or "").lower()
             or "duplicate"    in (el.get("text") or "").lower()
             or "already been" in (el.get("text") or "").lower()
             or "error"        in (el.get("class") or "").lower()
             or "invalid"      in (el.get("text") or "").lower())
            for el in dom_raw
            if el.get("tag", "").lower() not in ("input", "button")
        )

        print("[ACTIVITY-VERIFY] toast={} act_row={} form_closed={} error={}".format(
            toast_found, activity_row_found, form_closed, error_found))

        # Immediate FAIL if an error/duplicate message is visible
        if error_found:
            s.verified = True
            err_text = next(
                (el.get("text", "") for el in dom_raw
                 if el.get("tag", "").lower() not in ("input", "button")
                 and ("already exists" in (el.get("text") or "").lower()
                      or "duplicate"    in (el.get("text") or "").lower()
                      or "already been" in (el.get("text") or "").lower())),
                "Validation error shown on form"
            )
            if r:
                r.update_last_step(False, error=err_text)
            return {"action": "done", "result": "FAIL",
                    "reason": "Activity '{}' was NOT created — {}".format(
                        s.activity_name_override or "activity", err_text)}

        # Toast confirms success
        if toast_found:
            s.verified = True
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "Activity '{}' added to project '{}' — toast confirmed".format(
                        s.activity_name_override or "activity", s.project_name)}

        # Activity row visible — record is in the UI
        if activity_row_found:
            s.verified = True
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "Activity '{}' row confirmed in project '{}'".format(
                        s.activity_name_override or "activity", s.project_name)}

        # Form closed without error — save succeeded
        if form_closed:
            s.verified = True
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "Activity '{}' saved to project '{}' — form closed".format(
                        s.activity_name_override or "activity", s.project_name)}

        # Nothing confirmed yet — wait up to MAX_WAIT then FAIL
        s._submit_wait += 1
        print("[ACTIVITY-VERIFY] Waiting ({}/{})".format(s._submit_wait, s.MAX_WAIT))

        if s._submit_wait >= s.MAX_WAIT:
            s.verified = True
            if r:
                r.update_last_step(
                    False,
                    error="No confirmation received after {} waits — "
                          "activity was not created".format(s.MAX_WAIT),
                )
            return {"action": "done", "result": "FAIL",
                    "reason": "Activity '{}' was NOT created in project '{}' — "
                              "save was not confirmed (no toast, no row, form did not close)".format(
                                  s.activity_name_override or "activity", s.project_name)}

        return {"action": "wait", "seconds": 1}

    # ── Step 6: Fill form ─────────────────────────────────────
    if s.add_clicked and not s.form_filled:
        activity_name = s.activity_name_override or "Activity_{}".format(
            datetime.now().strftime("%H%M%S"))
        hours = str(random.randint(1, 8))

        print("[ACTIVITY] Step 6: Filling form: name='{}' hours={} job='{}'".format(
            activity_name, hours, s.job_name))

        s.form_filled = True
        s.submitted   = True   # tick is clicked inside fill_activity_form

        step = {
            "action": "fill_activity_form",
            "params": {
                "activity_name": activity_name,
                "hours":         hours,
                "job_name":      s.job_name,
            },
        }
        if r:
            r.log_step(len(r.steps) + 1, step, url)
        return step

    # ── Step 5: Click Add Activity ────────────────────────────
    if s.activities_clicked and not s.add_clicked:
        ab = els["add_activity_btn"]
        if ab and ab["selector"] not in s.interacted:
            s.interacted.add(ab["selector"])
            s.add_clicked = True
            print("[ACTIVITY] Step 5: Clicking Add Activity")
            step = {"action": "click", "selector": ab["selector"],
                    "extra_wait_ms": 1000}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step

        s._add_wait += 1
        print("[ACTIVITY] Step 5: Add Activity not found ({}/{})".format(
            s._add_wait, s.MAX_WAIT))
        if s._add_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False,
                    error="'Add Activity' button not found on Activities tab")
            return {"action": "done", "result": "FAIL",
                    "reason": "'Add Activity' button not found"}
        return {"action": "wait", "seconds": 1}

    # ── Step 4: Click Activities tab ──────────────────────────
    if s.view_clicked and not s.activities_clicked:
        at = els["activities_tab"]
        if at and at["selector"] not in s.interacted:
            s.interacted.add(at["selector"])
            s.activities_clicked = True
            print("[ACTIVITY] Step 4: Clicking Activities tab")
            step = {"action": "click", "selector": at["selector"],
                    "extra_wait_ms": 800}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step

        s._activities_wait += 1
        print("[ACTIVITY] Step 4: Activities tab not found ({}/{})".format(
            s._activities_wait, s.MAX_WAIT))
        if s._activities_wait >= s.MAX_WAIT:
            step = {"action": "click",
                    "selector": "#project-activities-tab",
                    "soft_fail": True}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step
        return {"action": "wait", "seconds": 1}

    # ── Step 3: Click View ────────────────────────────────────
    if s.search_typed and not s.view_clicked:
        vb = els["view_btn"]
        if vb and vb["selector"] not in s.interacted:
            s.interacted.add(vb["selector"])
            s.view_clicked = True
            print("[ACTIVITY] Step 3: Clicking View")
            step = {"action": "click", "selector": vb["selector"],
                    "extra_wait_ms": 1000}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step

        s._view_wait += 1
        print("[ACTIVITY] Step 3: View btn not found ({}/{})".format(
            s._view_wait, s.MAX_WAIT))
        if s._view_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False,
                    error="'View' button not found after search")
            return {"action": "done", "result": "FAIL",
                    "reason": "'View' button not found"}
        return {"action": "wait", "seconds": 1}

    # ── Step 2: Search project ────────────────────────────────
    if not s.search_typed:
        if "projects" not in url.lower():
            if not s._nav_fired:
                s._nav_fired = True
                step = {"action": "navigate", "url": BASE_URL + "/projects"}
                if r:
                    r.log_step(len(r.steps) + 1, step, url)
                return step
            return {"action": "wait", "seconds": 1}

        si = els["search_input"]
        if si:
            s.search_typed = True
            print("[ACTIVITY] Step 2: Searching '{}'".format(s.project_name))
            step = {"action": "type", "selector": si["selector"],
                    "text": s.project_name}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step

        s._search_wait += 1
        print("[ACTIVITY] Step 2: Search input not found ({}/{})".format(
            s._search_wait, s.MAX_WAIT))
        if s._search_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False,
                    error="Search input not found on /projects page")
            return {"action": "done", "result": "FAIL",
                    "reason": "Search input not found"}
        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

def reset_state(keep_session=False):
    reset_login()
    reset_nav()
    _add_act_st.reset()
    print("[STATE] Activity module reset")


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

    # Phase 3: Activity action
    if action == "add_activities":
        return await _decide_add_activity(els, url, goal)

    return {"action": "wait", "seconds": 1}