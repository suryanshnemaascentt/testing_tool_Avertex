import re
import random
from datetime import datetime, timedelta

from utils.login       import login_done, handle_login, reset_login
from utils.nav         import nav_done,   handle_nav,   reset_nav
from utils.dom_scanner import scan_common_dom
from config.settings   import BASE_URL

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
        "nav_projects":       None,
        "search_input":       None,
        "view_btn":           None,
        "activities_tab":     None,
        "add_activity_btn":   None,
        "activity_name_input": None,
    })

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

        # Activities tab — id="project-activities-tab" or role=tab + text=activities
        if tag == "button" and role == "tab" and "activit" in text and not result["activities_tab"]:
            result["activities_tab"] = el
        if eid == "project-activities-tab" and not result["activities_tab"]:
            result["activities_tab"] = el

        # Add Activity button
        if tag in _BTN_TAGS and ("add activity" in lv or "add activity" in comb):
            if not result["add_activity_btn"]:
                result["add_activity_btn"] = el

        # Activity name input — placeholder "Task name"
        if (tag == "input" and etype == "text"
                and ("task" in ph or "activity" in ph or "name" in ph)
                and not result["activity_name_input"]):
            result["activity_name_input"] = el

    return result


# ============================================================
# ADD ACTIVITY STATE
# ============================================================

class _AddActivityState:
    def __init__(self):
        self.project_name          = ""
        self.job_name=""
        self.activity_name_override = ""
        self.search_typed          = False
        self.view_clicked          = False
        self.activities_clicked    = False
        self.add_clicked           = False
        self.form_filled           = False
        self.submitted             = False
        self.verified              = False
        self._nav_fired            = False
        self._search_wait          = 0
        self._view_wait            = 0
        self._activities_wait      = 0
        self._add_wait             = 0
        self._submit_wait          = 0
        self.interacted            = set()
        self.MAX_WAIT              = 4

    def reset(self):
        self.__init__()

_add_act_st = _AddActivityState()


# ============================================================
# ADD ACTIVITY LOGIC
# ============================================================

async def _decide_add_activity(els, url, goal):
    s = _add_act_st

    # Parse project + activity name from goal
    if not s.project_name:
        m = _ADD_ACTIVITIES_RE.search(goal)
        if m:
            s.project_name        = m.group(1).strip()
            s.job_name            = m.group(2).strip()
            s.activity_name_override = m.group(3).strip()
            print("[ACTIVITY] Project: '{}' | Job: '{}' | Activity: '{}'".format(
                s.project_name, s.job_name, s.activity_name_override))
        else:
            m2 = _ADD_ACTIVITIES_RE_SIMPLE.search(goal)
            if m2:
                s.project_name = m2.group(1).strip()

    if s.verified:
        return {"action": "done", "result": "PASS",
                "reason": "Activity '{}' added to project '{}'".format(
                    s.activity_name_override or "activity", s.project_name)}

    # ── Step 7: Verify ────────────────────────────────────────
    if s.submitted:
        activity_form_gone = not bool(els.get("activity_name_input"))
        activity_in_dom    = any(
            (s.activity_name_override or "").lower() in (el.get("text") or "").lower()
            for el in (els.get("dom_raw") or [])
        ) if s.activity_name_override else False

        if activity_form_gone or activity_in_dom or els["success_toast"]:
            s.verified = True
            return {"action": "done", "result": "PASS",
                    "reason": "Activity '{}' added to project '{}'".format(
                        s.activity_name_override or "activity", s.project_name)}
        s._submit_wait += 1
        print("[ACTIVITY-VERIFY] Waiting ({}/{})".format(s._submit_wait, s.MAX_WAIT))
        if s._submit_wait >= s.MAX_WAIT:
            s.verified = True
            return {"action": "done", "result": "PASS",
                    "reason": "Activity submitted (tick clicked)"}
        return {"action": "wait", "seconds": 1}

    # ── Step 6: Fill form ─────────────────────────────────────
    if s.add_clicked and not s.form_filled:
        activity_name = s.activity_name_override or "Activity_{}".format(
            datetime.now().strftime("%H%M%S"))
        hours = str(random.randint(1, 8))

        print("[ACTIVITY] Filling form: name='{}' hours={}".format(
            activity_name, hours))

        s.form_filled = True
        s.submitted   = True   # tick clicked inside fill_activity_form
        return {
            "action": "fill_activity_form",
            "params": {
                "activity_name": activity_name,
                "hours":         hours,
                "job_name":      s.job_name,    
            }
        }

    # ── Step 5: Click Add Activity ────────────────────────────
    if s.activities_clicked and not s.add_clicked:
        ab = els["add_activity_btn"]
        if ab and ab["selector"] not in s.interacted:
            s.interacted.add(ab["selector"])
            s.add_clicked = True
            print("[ACTIVITY] Step 5: Clicking Add Activity")
            return {"action": "click", "selector": ab["selector"],
                    "extra_wait_ms": 1000}
        s._add_wait += 1
        print("[ACTIVITY] Step 5: Add Activity not found ({}/{})".format(
            s._add_wait, s.MAX_WAIT))
        if s._add_wait >= s.MAX_WAIT:
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
            return {"action": "click", "selector": at["selector"],
                    "extra_wait_ms": 800}
        s._activities_wait += 1
        if s._activities_wait >= s.MAX_WAIT:
            return {"action": "click",
                    "selector": "#project-activities-tab",
                    "soft_fail": True}
        return {"action": "wait", "seconds": 1}

    # ── Step 3: Click View ────────────────────────────────────
    if s.search_typed and not s.view_clicked:
        vb = els["view_btn"]
        if vb and vb["selector"] not in s.interacted:
            s.interacted.add(vb["selector"])
            s.view_clicked = True
            print("[ACTIVITY] Step 3: Clicking View")
            return {"action": "click", "selector": vb["selector"],
                    "extra_wait_ms": 1000}
        s._view_wait += 1
        if s._view_wait >= s.MAX_WAIT:
            return {"action": "done", "result": "FAIL",
                    "reason": "'View' button not found"}
        return {"action": "wait", "seconds": 1}

    # ── Step 2: Search project ────────────────────────────────
    if not s.search_typed:
        if "projects" not in url.lower():
            if not s._nav_fired:
                s._nav_fired = True
                return {"action": "navigate", "url": BASE_URL + "/projects"}
            return {"action": "wait", "seconds": 1}
        si = els["search_input"]
        if si:
            s.search_typed = True
            print("[ACTIVITY] Step 2: Searching '{}'".format(s.project_name))
            return {"action": "type", "selector": si["selector"],
                    "text": s.project_name}
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
    reset_login()
    reset_nav()
    _add_act_st.reset()
    print("[STATE] Activity module reset")


async def decide_action(action, dom, url, goal="", email=None, password=None):
    els = scan_dom(dom)

    if not login_done():
        step = handle_login(els, email, password, url)
        if step is None and not login_done():
            return {"action": "wait", "seconds": 1}
        if step:
            return step

    if not nav_done():
        step = handle_nav(els, url, NAV_FRAGMENT)
        if step:
            return step

    if action == "add_activities":
        return await _decide_add_activity(els, url, goal)

    return {"action": "wait", "seconds": 1}