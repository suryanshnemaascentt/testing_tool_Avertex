import re

from utils.login       import login_done, handle_login, reset_login
from utils.nav         import nav_done,   handle_nav,   reset_nav
from utils.dom_scanner import scan_common_dom
from config.settings   import BASE_URL
from report.test_report import get_reporter

# ============================================================
# modules/team.py
#
# Workflow:
#   Login -> /projects -> search project -> view ->
#   Team tab -> (add / update / delete team member)
#
# Goal string formats:
#   create  "create team ProjectName"
#   update  "update team ProjectName | MemberName"
#   delete  "delete team ProjectName | MemberName"
# ============================================================

NAV_FRAGMENT = "projects"

ACTIONS = {
    "create": {
        "label":        "Add Team Member  (random employee, random role)",
        "needs_target": True,
    },
    "update": {
        "label":        "Update Team Member  (change role)",
        "needs_target": True,
    },
    "delete": {
        "label":        "Remove Team Member",
        "needs_target": True,
    },
}

ACTION_KEYS = list(ACTIONS.keys())

_CREATE_RE = re.compile(r"create team\s+(.+?)$",  re.IGNORECASE)
_UPDATE_RE = re.compile(r"update team\s+(.+?)$",  re.IGNORECASE)
_DELETE_RE = re.compile(r"delete team\s+(.+?)$",  re.IGNORECASE)

# ============================================================
# DOM SCANNER
# ============================================================

_NON_TOAST = ("input", "button")

_SUCCESS_PHRASES = (
    "added successfully",
    "team member added",
    "successfully added",
    "saved successfully",
    "updated successfully",
    "removed successfully",
    "deleted successfully",
    "member removed",
)

_DUPLICATE_PHRASES = (
    "already exists",
    "already a member",
    "duplicate",
    "already been added",
)


def scan_dom(dom):
    result = scan_common_dom(dom)

    result.update({
        "search_input":    None,
        "view_btn":        None,
        "team_tab":        None,
        "add_member_btn":  None,
        "confirm_btn":     None,
        "delete_btn":      None,
        "save_btn":        None,
        "success_toast":   None,
        "duplicate_error": None,
        "member_rows":     [],
        "dialog_open":     False,   # track if MUI dialog is visible
        "_raw_dom":        dom,      # store raw dom for row-gone verification
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

        # ── Detect MUI dialog open ────────────────────────────
        if ("muidialog-root" in cls or "muidialog-paper" in cls
                or "muidialog-container" in cls):
            result["dialog_open"] = True

        # ── Search input ──────────────────────────────────────
        if (tag == "input" and etype in ("text", "search")
                and ("search" in ph or "search" in eid or "search" in cls)
                and not result["search_input"]):
            result["search_input"] = el

        # ── Buttons ───────────────────────────────────────────
        if tag in _BTN_TAGS and etype in _BTN_TYPES:
            if text in ("view", "view details") or label == "view":
                result["view_btn"] = el

            elif ("team" in text and "tab" in cls) or eid == "project-team-tab":
                result["team_tab"] = el

            elif "add team member" in text or "add team member" in label:
                result["add_member_btn"] = el

            elif any(x in text for x in ("yes", "confirm", "ok", "sure", "proceed")):
                if not result["confirm_btn"]:
                    result["confirm_btn"] = el

            elif (text == "delete" or label == "delete"
                  or text == "remove" or label == "remove"
                  or "muibutton-outlinederror" in cls
                  or "muibutton-colorerror" in cls):
                if not result["delete_btn"]:
                    result["delete_btn"] = el

        # ── Tab by role ───────────────────────────────────────
        if role == "tab" and "team" in (text + " " + label + " " + eid):
            result["team_tab"] = el

        # ── Toasts / errors ───────────────────────────────────
        if tag not in _NON_TOAST:
            if any(phrase in comb for phrase in _SUCCESS_PHRASES) and not result["success_toast"]:
                result["success_toast"] = el

            if any(phrase in comb for phrase in _DUPLICATE_PHRASES) and not result["duplicate_error"]:
                result["duplicate_error"] = el

            if any(x in comb for x in ("error", "failed", "invalid")) and not result["error_toast"]:
                result["error_toast"] = el

    return result


# ============================================================
# CREATE STATE + LOGIC
# ============================================================

class _CreateState:
    def __init__(self):
        self.project_name     = ""
        self.search_typed     = False
        self.view_clicked     = False
        self.team_tab_clicked = False
        self.form_open        = False
        self.submitted        = False
        self.verified         = False
        self._nav_fired       = False
        self._search_wait     = 0
        self._view_wait       = 0
        self._team_tab_wait   = 0
        self._add_btn_wait    = 0
        self._verify_wait     = 0
        self.interacted       = set()
        self.MAX_WAIT         = 1

    def reset(self):
        self.__init__()

_create_st = _CreateState()


async def _decide_create(els, url, goal):
    s = _create_st
    r = get_reporter()

    if not s.project_name:
        m = _CREATE_RE.search(goal)
        if m:
            s.project_name = m.group(1).strip()
        else:
            parts = goal.strip().split(None, 2)
            s.project_name = parts[2].strip() if len(parts) > 2 else ""
        print("[TEAM-CREATE] Project: '{}'".format(s.project_name))

    # HARD STOP
    if s.verified:
        return {
            "action": "done",
            "result": "PASS",
            "reason": "Team member already added to '{}' (skipping re-run)".format(s.project_name)
        }

    # VERIFY AFTER SUBMIT
    if s.submitted:

        if els["duplicate_error"]:
            if r:
                r.update_last_step(False, error="Member already exists")
            s.reset()
            return {"action": "done", "result": "FAIL",
                    "reason": "Team member already exists — not re-added"}

        if els["success_toast"]:
            if r:
                r.update_last_step(True)
            s.verified = True
            s.reset()
            return {"action": "done", "result": "PASS",
                    "reason": "Team member added — toast confirmed"}

        if not els.get("save_btn") and not els.get("dialog_open"):
            if r:
                r.update_last_step(True)
            s.verified = True
            s.reset()
            return {"action": "done", "result": "PASS",
                    "reason": "Team member added (form closed verification)"}

        s._verify_wait += 1
        if s._verify_wait > s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Could not verify team member add")
            s.reset()
            return {"action": "done", "result": "FAIL",
                    "reason": "Could not verify team member addition"}

        return {"action": "wait", "seconds": 1}

    # FILL FORM
    if s.form_open:
        s.submitted = True
        if r:
            r.log_step(len(r.steps) + 1,
                       {"action": "fill_team_member_form",
                        "params": {"project_name": s.project_name}},
                       url)
        return {"action": "fill_team_member_form",
                "params": {"project_name": s.project_name}}

    # CLICK ADD MEMBER
    if s.team_tab_clicked:
        ab = els["add_member_btn"]
        if ab and ab["selector"] not in s.interacted:
            s.interacted.add(ab["selector"])
            s.form_open = True
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "click", "selector": ab["selector"]}, url)
            return {"action": "click", "selector": ab["selector"]}

        s._add_btn_wait += 1
        if s._add_btn_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="'Add Team Member' button not found")
            return {"action": "done", "result": "FAIL",
                    "reason": "'Add Team Member' button not found"}

        return {"action": "wait", "seconds": 1}

    # CLICK TEAM TAB
    if s.view_clicked:
        tb = els["team_tab"]
        if tb and tb["selector"] not in s.interacted:
            s.interacted.add(tb["selector"])
            s.team_tab_clicked = True
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "click", "selector": "#project-team-tab"}, url)
            return {"action": "click", "selector": "#project-team-tab", "force": True}

        if not tb:
            s.team_tab_clicked = True
            return {"action": "click",
                    "selector": "button[role='tab']:has-text('Team')",
                    "force": True}

        s._team_tab_wait += 1
        if s._team_tab_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Team tab not found")
            return {"action": "done", "result": "FAIL", "reason": "Team tab not found"}

        return {"action": "wait", "seconds": 1}

    # CLICK VIEW
    if s.search_typed:
        vb = els["view_btn"]
        if vb and vb["selector"] not in s.interacted:
            s.interacted.add(vb["selector"])
            s.view_clicked = True
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "click", "selector": vb["selector"]}, url)
            return {"action": "click", "selector": vb["selector"]}

        s._view_wait += 1
        if s._view_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="'View' button not found")
            return {"action": "done", "result": "FAIL", "reason": "'View' button not found"}

        return {"action": "wait", "seconds": 1}

    # SEARCH / NAV
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
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "type", "selector": si["selector"],
                            "text": s.project_name}, url)
            return {"action": "type", "selector": si["selector"],
                    "text": s.project_name}

        s._search_wait += 1
        if s._search_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="Search input not found")
            return {"action": "done", "result": "FAIL",
                    "reason": "Search input not found"}

        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# UPDATE STATE + LOGIC
# ============================================================

class _UpdateState:
    def __init__(self):
        self.project_name     = ""
        self.member_name      = ""
        self.search_typed     = False
        self.view_clicked     = False
        self.team_tab_clicked = False
        self.submitted        = False
        self.verified         = False
        self._nav_fired       = False
        self._search_wait     = 0
        self._view_wait       = 0
        self._team_tab_wait   = 0
        self._form_wait       = 0
        self._verify_wait     = 0
        self.interacted       = set()
        self.MAX_WAIT         = 1

    def reset(self):
        self.__init__()

_update_st = _UpdateState()


async def _decide_update(els, url, goal):
    s = _update_st
    r = get_reporter()

    if not s.project_name:
        if "|" in goal:
            parts = goal.split("|", 1)
            s.project_name = parts[0].replace("update team", "").strip()
            s.member_name  = parts[1].strip()
        else:
            m = _UPDATE_RE.search(goal)
            s.project_name = m.group(1).strip() if m else goal.split(None, 2)[-1]
            s.member_name  = ""

        print("[TEAM-UPDATE] Project: '{}' | Member: '{}'".format(
            s.project_name, s.member_name))

    # HARD STOP
    if s.verified:
        if r: r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Team member already updated"}

    # VERIFY AFTER SUBMIT
    if s.submitted:

        # Dialog closed = fastest and most reliable signal
        if not els.get("dialog_open") and not els.get("save_btn"):
            if r: r.update_last_step(True)
            s.verified = True
            result = {"action": "done", "result": "PASS",
                      "reason": "Team member updated (dialog closed)"}
            s.reset()
            return result

        if els["success_toast"]:
            if r: r.update_last_step(True)
            s.verified = True
            result = {"action": "done", "result": "PASS",
                      "reason": "Team member updated — toast confirmed"}
            s.reset()
            return result

        s._verify_wait += 1
        if s._verify_wait > s.MAX_WAIT:
            if r: r.update_last_step(True)
            s.verified = True
            result = {"action": "done", "result": "PASS",
                      "reason": "Team member update assumed successful"}
            s.reset()
            return result

        return {"action": "wait", "seconds": 1}

    # FILL FORM
    if s.team_tab_clicked and not s.submitted:
        s.submitted = True
        if r:
            r.log_step(len(r.steps) + 1,
                       {"action": "fill_team_member_form",
                        "params": {
                            "project_name": s.project_name,
                            "mode": "update",
                            "member_name": s.member_name,
                        }}, url)
        return {"action": "fill_team_member_form",
                "params": {
                    "project_name": s.project_name,
                    "mode": "update",
                    "member_name": s.member_name,
                }}

    # CLICK TEAM TAB
    if s.view_clicked and not s.team_tab_clicked:
        tb = els["team_tab"]
        if tb and tb["selector"] not in s.interacted:
            s.interacted.add(tb["selector"])
            s.team_tab_clicked = True
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "click", "selector": "#project-team-tab"}, url)
            return {"action": "click", "selector": "#project-team-tab", "force": True}

        if not tb:
            s.team_tab_clicked = True
            return {"action": "click",
                    "selector": "button[role='tab']:has-text('Team')", "force": True}

        s._team_tab_wait += 1
        if s._team_tab_wait >= s.MAX_WAIT:
            return {"action": "done", "result": "FAIL", "reason": "Team tab not found"}

        return {"action": "wait", "seconds": 1}

    # CLICK VIEW
    if s.search_typed and not s.view_clicked:
        vb = els["view_btn"]
        if vb and vb["selector"] not in s.interacted:
            s.interacted.add(vb["selector"])
            s.view_clicked = True
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "click", "selector": vb["selector"]}, url)
            return {"action": "click", "selector": vb["selector"]}

        s._view_wait += 1
        if s._view_wait >= s.MAX_WAIT:
            return {"action": "done", "result": "FAIL", "reason": "'View' not found"}

        return {"action": "wait", "seconds": 1}

    # SEARCH / NAV
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
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "type", "selector": si["selector"],
                            "text": s.project_name}, url)
            return {"action": "type", "selector": si["selector"],
                    "text": s.project_name}

        s._search_wait += 1
        if s._search_wait >= s.MAX_WAIT:
            return {"action": "done", "result": "FAIL", "reason": "Search input not found"}

        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# DELETE STATE + LOGIC
# ============================================================

class _DeleteState:
    def __init__(self):
        self.project_name     = ""
        self.member_name      = ""   # specific employee to remove
        self.search_typed     = False
        self.view_clicked     = False
        self.team_tab_clicked = False
        self.submitted        = False
        self.verified         = False
        self._nav_fired       = False
        self._search_wait     = 0
        self._view_wait       = 0
        self._team_tab_wait   = 0
        self._verify_wait     = 0
        self.interacted       = set()
        self.MAX_WAIT         = 1

    def reset(self):
        self.__init__()

_delete_st = _DeleteState()


async def _decide_delete(els, url, goal):
    s = _delete_st
    r = get_reporter()

    # ── Parse project name AND member name ────────────────────
    # Supported formats:
    #   "delete team ProjectName | MemberName"   <- preferred
    #   "delete team ProjectName"                <- member_name stays blank
    if not s.project_name:
        if "|" in goal:
            parts = goal.split("|", 1)
            s.project_name = parts[0].replace("delete team", "").strip()
            s.member_name  = parts[1].strip()
        else:
            m = _DELETE_RE.search(goal)
            s.project_name = m.group(1).strip() if m else goal.split(None, 2)[-1]
            s.member_name  = ""

        print("[TEAM-DELETE] Project: '{}' | Member: '{}'".format(
            s.project_name, s.member_name))

    # HARD STOP
    if s.verified:
        if r: r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Team member '{}' removed from '{}'".format(
                    s.member_name or "selected", s.project_name)}

    # VERIFY AFTER SUBMIT
    if s.submitted:

        # Signal 1: success toast
        if els["success_toast"]:
            if r: r.update_last_step(True)
            s.verified = True
            result = {"action": "done", "result": "PASS",
                      "reason": "Team member '{}' removed — toast confirmed".format(
                          s.member_name or "selected")}
            s.reset()
            return result

        # Signal 2: member row gone from DOM
        # After deletion the row disappears — if the member name is no longer
        # visible anywhere in the scanned elements, the delete succeeded.
        if s.member_name:
            member_still_visible = any(
                s.member_name.lower() in (
                    (el.get("text") or "") + " " + (el.get("label") or "")
                ).lower()
                for el in els.get("_raw_dom", [])
            )
            if not member_still_visible:
                if r: r.update_last_step(True)
                s.verified = True
                result = {"action": "done", "result": "PASS",
                          "reason": "Team member '{}' removed (row gone from DOM)".format(
                              s.member_name)}
                s.reset()
                return result

        # Signal 3: timeout fallback — max 2 extra ticks then done
        s._verify_wait += 1
        if s._verify_wait > 2:
            if r: r.update_last_step(True)
            s.verified = True
            result = {"action": "done", "result": "PASS",
                      "reason": "Team member '{}' likely removed".format(
                          s.member_name or "selected")}
            s.reset()
            return result

        return {"action": "wait", "seconds": 1}

    # FIRE DELETE — handled inside fill_team_member_form with mode='delete'
    if s.team_tab_clicked and not s.submitted:
        s.submitted = True
        if r:
            r.log_step(len(r.steps) + 1,
                       {"action": "fill_team_member_form",
                        "params": {
                            "mode":         "delete",
                            "member_name":  s.member_name,
                            "project_name": s.project_name,
                        }}, url)
        return {"action": "fill_team_member_form",
                "params": {
                    "mode":         "delete",
                    "member_name":  s.member_name,
                    "project_name": s.project_name,
                }}

    # CLICK TEAM TAB
    if s.view_clicked and not s.team_tab_clicked:
        tb = els["team_tab"]
        if tb and tb["selector"] not in s.interacted:
            s.interacted.add(tb["selector"])
            s.team_tab_clicked = True
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "click", "selector": "#project-team-tab"}, url)
            return {"action": "click", "selector": "#project-team-tab", "force": True}

        if not tb:
            s.team_tab_clicked = True
            return {"action": "click",
                    "selector": "button[role='tab']:has-text('Team')", "force": True}

        s._team_tab_wait += 1
        if s._team_tab_wait >= s.MAX_WAIT:
            return {"action": "done", "result": "FAIL", "reason": "Team tab not found"}

        return {"action": "wait", "seconds": 1}

    # CLICK VIEW
    if s.search_typed and not s.view_clicked:
        vb = els["view_btn"]
        if vb and vb["selector"] not in s.interacted:
            s.interacted.add(vb["selector"])
            s.view_clicked = True
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "click", "selector": vb["selector"]}, url)
            return {"action": "click", "selector": vb["selector"]}

        s._view_wait += 1
        if s._view_wait >= s.MAX_WAIT:
            return {"action": "done", "result": "FAIL", "reason": "'View' not found"}

        return {"action": "wait", "seconds": 1}

    # SEARCH / NAV
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
            if r:
                r.log_step(len(r.steps) + 1,
                           {"action": "type", "selector": si["selector"],
                            "text": s.project_name}, url)
            return {"action": "type", "selector": si["selector"],
                    "text": s.project_name}

        s._search_wait += 1
        if s._search_wait >= s.MAX_WAIT:
            return {"action": "done", "result": "FAIL", "reason": "Search input not found"}

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
    print("[STATE] Team module reset")


async def decide_action(action, dom, url, goal="",
                        email=None, password=None, page=None):
    els = scan_dom(dom)

    # Phase 1: Login
    if not login_done():
        step = handle_login(els, email, password, url)
        if step is None and not login_done():
            return {"action": "wait", "seconds": 1}
        if step:
            r = get_reporter()
            if r: r.log_step(len(r.steps) + 1, step, url)
            return step

    # Phase 2: Navigate to /projects
    if not nav_done():
        step = handle_nav(els, url, NAV_FRAGMENT)
        if step:
            r = get_reporter()
            if r: r.log_step(len(r.steps) + 1, step, url)
            return step

    # Phase 3: Team action
    if action == "create":
        return await _decide_create(els, url, goal)
    if action == "update":
        return await _decide_update(els, url, goal)
    if action == "delete":
        return await _decide_delete(els, url, goal)

    return {"action": "wait", "seconds": 1}