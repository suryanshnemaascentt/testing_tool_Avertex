
import re
from datetime import datetime, timedelta

from utils.login       import login_done, handle_login, reset_login
from utils.nav         import nav_done,   handle_nav,   reset_nav
from utils.dom_scanner import scan_common_dom
from config.settings   import BASE_URL
from report.test_report import get_reporter

# ============================================================
# modules/job.py
#
# Workflow:
#   Login -> /projects -> search project -> View ->
#   Jobs tab -> Add Job -> fill form -> tick button (in form_filler)
# ============================================================

NAV_FRAGMENT = "projects"

MODULE_META = {
    "name":     "Jobs",
    "fragment": NAV_FRAGMENT,
    "order":    2,
}

ACTIONS = {
    "add_job": {
        "label":        "Create new Job in a Project",
        "needs_target": ["Project name", "Job name"],
    },
}

ACTION_KEYS = list(ACTIONS.keys())

# Regex to parse goal string: "add_job job <project_name> | <job_name>"
_ADD_JOB_RE        = re.compile(r"add_job\s+job\s+(.+?)\s*\|\s*(.+?)$", re.IGNORECASE)
_ADD_JOB_RE_SIMPLE = re.compile(r"add_job\s+job\s+(.+?)$",              re.IGNORECASE)


# ============================================================
# DOM SCANNER
# ============================================================

def scan_dom(dom):
    result = scan_common_dom(dom)
    result.update({
        "nav_projects":    None,   # sidebar nav link -> /projects
        "search_input":    None,   # project search box
        "view_btn":        None,   # View button on project row
        "jobs_tab":        None,   # Jobs tab inside project view
        "add_job_btn":     None,   # + Add Job inline row trigger
        "job_name_input":  None,   # Job Name text input
        "job_start_input": None,   # Start date input (type=date)
        "job_end_input":   None,   # End date input (type=date)
        "job_hours_input": None,   # Hours number input
        "job_save_btn":    None,   # Tick/checkmark submit button
        "job_cancel_btn":  None,   # X cancel button
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

        if tag in _NAV_TAGS and "project" in comb and not result["nav_projects"]:
            result["nav_projects"] = el

        if (tag == "input" and etype in ("text", "search")
                and ("search" in ph or "search" in eid or "search" in cls)
                and not result["search_input"]):
            result["search_input"] = el

        if tag in _BTN_TAGS and etype in _BTN_TYPES:
            if text in ("view", "view details") or label == "view":
                if not result["view_btn"]:
                    result["view_btn"] = el

        # ── Jobs tab ──────────────────────────────────────────
        if (tag == "button" and role == "tab"
                and "jobs" in text
                and not result["jobs_tab"]):
            result["jobs_tab"] = el
        if eid == "project-jobs-tab" and not result["jobs_tab"]:
            result["jobs_tab"] = el

        # ── Add Job button ────────────────────────────────────
        if tag in _BTN_TAGS and ("add job" in lv or "add job" in comb):
            if not result["add_job_btn"]:
                result["add_job_btn"] = el

        # ── Job form fields ───────────────────────────────────
        if (tag == "input" and etype == "text"
                and ("discovery" in ph or "development" in ph
                     or "e.g" in ph or "testing" in ph)
                and not result["job_name_input"]):
            result["job_name_input"] = el

        if tag == "input" and etype == "date":
            if not result["job_start_input"]:
                result["job_start_input"] = el
            elif not result["job_end_input"]:
                result["job_end_input"] = el

        if (tag == "input" and etype == "number"
                and not result["job_hours_input"]):
            result["job_hours_input"] = el

        if tag == "button" and "muiiconbutton" in cls:
            if "disabled" not in cls and "tabindex" not in el.get("selector", ""):
                if not result["job_save_btn"]:
                    result["job_save_btn"] = el
                elif not result["job_cancel_btn"]:
                    result["job_cancel_btn"] = el

    return result


# ============================================================
# ADD JOB STATE
# ============================================================

class _AddJobState:
    def __init__(self):
        self.project_name      = ""
        self.job_name_override = ""

        # Step flags
        self.search_typed  = False
        self.view_clicked  = False
        self.jobs_clicked  = False
        self.add_clicked   = False
        self.form_filled   = False
        self.submitted     = False
        self.verified      = False

        # Navigation
        self._nav_fired    = False

        # Wait counters
        self._search_wait  = 0
        self._view_wait    = 0
        self._jobs_wait    = 0
        self._add_wait     = 0
        self._form_wait    = 0
        self._submit_wait  = 0

        self._dom_at_submit = 0   # DOM count snapshot when save was clicked

        self.interacted    = set()
        self.MAX_WAIT      = 1

    def reset(self):
        self.__init__()

_add_job_st = _AddJobState()


# ============================================================
# ADD JOB LOGIC
# ============================================================

async def _decide_add_job(els, url, goal):
    s = _add_job_st
    r = get_reporter()

    # ── Parse project / job name from goal on first call ─────
    if not s.project_name:
        m = _ADD_JOB_RE.search(goal)
        if m:
            s.project_name      = m.group(1).strip()
            s.job_name_override = m.group(2).strip()
            print("[JOB] Project target: '{}'  |  Job name override: '{}'".format(
                s.project_name, s.job_name_override))
        else:
            m2 = _ADD_JOB_RE_SIMPLE.search(goal)
            if m2:
                s.project_name = m2.group(1).strip()
                print("[JOB] Project target: '{}'".format(s.project_name))

    # ── Already done ──────────────────────────────────────────
    if s.verified:
        if r:
            r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Job '{}' added to project '{}'".format(
                    s.job_name_override or "job", s.project_name)}

    # ── Step 7: Verify after submit ───────────────────────────
    if s.submitted:
        dom_raw           = els.get("dom_raw") or []
        current_dom_count = len(dom_raw)
        job_name_target   = (s.job_name_override or "").lower()

        # ── Signal 1: success toast / snackbar present ────────
        toast_found = any(
            ("success" in (el.get("text")  or "").lower()
             or "success" in (el.get("class") or "").lower()
             or "snackbar" in (el.get("class") or "").lower()
             or "toast"   in (el.get("class") or "").lower()
             or "added"   in (el.get("text")  or "").lower()
             or "created" in (el.get("text")  or "").lower())
            for el in dom_raw
        )

        # ── Signal 2: job name now appears in a table/list row ─
        job_row_found = bool(job_name_target) and any(
            job_name_target in (el.get("text") or "").lower()
            for el in dom_raw
            if el.get("tag", "").lower() in ("td", "tr", "span", "div", "li")
        )

        # ── Signal 3: DOM count dropped significantly since save ─
        # The inline job form adds ~6 elements when open.
        # A drop of >= 4 from the DOM count at save time means the
        # form closed — which only happens on a successful save.
        form_closed = (
            s._dom_at_submit > 0
            and current_dom_count <= s._dom_at_submit - 4
        )

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

        print("[JOB-VERIFY] toast={} job_row={} form_closed={} error={} (dom {} -> {})".format(
            toast_found, job_row_found, form_closed, error_found,
            s._dom_at_submit, current_dom_count))

        # Immediate FAIL if an error/duplicate message is visible
        if error_found:
            s.verified = True
            err_text = next(
                (el.get("text", "") for el in dom_raw
                 if el.get("tag", "").lower() not in ("input", "button")
                 and ("already exists" in (el.get("text") or "").lower()
                      or "duplicate"   in (el.get("text") or "").lower()
                      or "already been" in (el.get("text") or "").lower())),
                "Validation error shown on form"
            )
            if r:
                r.update_last_step(False, error=err_text)
            return {"action": "done", "result": "FAIL",
                    "reason": "Job '{}' was NOT created — {}".format(
                        s.job_name_override or "job", err_text)}

        # DOM reduction alone is definitive — form can only close on success
        if form_closed:
            s.verified = True
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "Job '{}' saved to project '{}' (form closed, dom {} -> {})".format(
                        s.job_name_override or "job", s.project_name,
                        s._dom_at_submit, current_dom_count)}

        # Toast or row visible — also definitive
        if toast_found or job_row_found:
            s.verified = True
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "Job '{}' added to project '{}' (toast={}, row={})".format(
                        s.job_name_override or "job", s.project_name,
                        toast_found, job_row_found)}

        # Nothing confirmed yet — wait up to MAX_WAIT (2) times then FAIL
        s._submit_wait += 1
        print("[JOB-VERIFY] Waiting ({}/{})".format(s._submit_wait, s.MAX_WAIT))

        if s._submit_wait >= s.MAX_WAIT:
            # No confirmation signal after full wait — job was NOT created
            s.verified = True
            if r:
                r.update_last_step(
                    False,
                    error="No success confirmation received after {} waits — "
                          "job was not created (dom {} -> {})".format(
                              s.MAX_WAIT, s._dom_at_submit, current_dom_count),
                )
            return {"action": "done", "result": "FAIL",
                    "reason": "Job '{}' was NOT created in project '{}' — "
                              "save was not confirmed (no toast, no row, form did not close)".format(
                                  s.job_name_override or "job", s.project_name)}

        return {"action": "wait", "seconds": 1}

    # ── Step 6b: Submit (click tick/save button) ──────────────
    if s.form_filled and not s.submitted:
        print("[JOB] Step 6b: Clicking save (tick) button")
        s.submitted = True
        s._dom_at_submit = len(els.get("dom_raw") or [])
        step = {
            # Use :has() to match the button CONTAINING the checkmark path —
            # clicking the button element itself is reliable; clicking the
            # SVG path child is not (no pointer events on SVG children).
            "action":        "click",
            "selector":      "button.MuiIconButton-root:not([disabled]):not(.Mui-disabled):has(path[d='M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'])",
            "extra_wait_ms": 1500,
            "soft_fail":     True,
        }
        if r:
            r.log_step(len(r.steps) + 1, step, url)
        return step

    # ── Step 6: Fill form ─────────────────────────────────────
    if s.add_clicked and not s.form_filled:
        job_name   = s.job_name_override or "Job_{}".format(
            datetime.now().strftime("%H%M%S"))
        today      = datetime.now()
        start_date = today.strftime("%Y-%m-%d")
        end_date   = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        hours      = "8"   # default hours value

        print("[JOB] Filling form: name='{}' start={} end={}".format(
            job_name, start_date, end_date))

        s.form_filled = True
        step = {
            "action": "fill_job_form",
            "params": {
                "job_name":   job_name,
                "start_date": start_date,
                "end_date":   end_date,
                "hours":      hours,
            },
        }
        if r:
            r.log_step(len(r.steps) + 1, step, url)
        return step

    # ── Step 5: Click Add Job ─────────────────────────────────
    if s.jobs_clicked and not s.add_clicked:
        ab = els["add_job_btn"]
        if ab and ab["selector"] not in s.interacted:
            s.interacted.add(ab["selector"])
            s.add_clicked = True
            print("[JOB] Step 5: Clicking Add Job")
            step = {"action": "click", "selector": ab["selector"],
                    "extra_wait_ms": 800}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step

        s._add_wait += 1
        print("[JOB] Step 5: Add Job not found ({}/{})".format(
            s._add_wait, s.MAX_WAIT))
        if s._add_wait >= s.MAX_WAIT:
            err = ("'Add Job' button not found — Jobs tab may be empty "
                   "or the project does not allow adding jobs")
            if r:
                r.update_last_step(False, error=err)
            return {"action": "done", "result": "FAIL", "reason": err}
        return {"action": "wait", "seconds": 1}

    # ── Step 4: Click Jobs tab ────────────────────────────────
    if s.view_clicked and not s.jobs_clicked:
        jt = els["jobs_tab"]
        if jt and jt["selector"] not in s.interacted:
            s.interacted.add(jt["selector"])
            s.jobs_clicked = True
            print("[JOB] Step 4: Clicking Jobs tab")
            step = {"action": "click", "selector": jt["selector"],
                    "extra_wait_ms": 800}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step

        s._jobs_wait += 1
        if s._jobs_wait >= s.MAX_WAIT:
            step = {"action": "click", "selector": "#project-jobs-tab",
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
            print("[JOB] Step 3: Clicking View")
            step = {"action": "click", "selector": vb["selector"],
                    "extra_wait_ms": 1000}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step

        s._view_wait += 1
        if s._view_wait >= s.MAX_WAIT:
            dom_raw = els.get("dom_raw") or []
            name_in_dom = any(
                s.project_name.lower() in (el.get("text") or "").lower()
                for el in dom_raw
                if el.get("tag", "").lower() not in ("input", "button", "script")
            )
            err = (
                "Project '{}' found in results but View button is not available".format(s.project_name)
                if name_in_dom else
                "Project '{}' not found in search results — cannot add job".format(s.project_name)
            )
            if r:
                r.update_last_step(False, error=err)
            return {"action": "done", "result": "FAIL", "reason": err}
        return {"action": "wait", "seconds": 1}

    # ── Step 2: Search project ────────────────────────────────
    if not s.search_typed:
        if "projects" not in url.lower():
            if not s._nav_fired:
                s._nav_fired = True
                step = {"action": "navigate",
                        "url": BASE_URL + "/projects"}
                if r:
                    r.log_step(len(r.steps) + 1, step, url)
                return step
            return {"action": "wait", "seconds": 1}

        si = els["search_input"]
        if si:
            s.search_typed = True
            print("[JOB] Step 2: Searching project '{}'".format(s.project_name))
            step = {"action": "type", "selector": si["selector"],
                    "text": s.project_name}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step

        s._search_wait += 1
        if s._search_wait >= s.MAX_WAIT:
            err = "Search input not found — Projects page may not have loaded correctly (url: {})".format(url)
            if r:
                r.update_last_step(False, error=err)
            return {"action": "done", "result": "FAIL", "reason": err}
        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

def reset_state(keep_session=False):
    reset_login()
    reset_nav()
    _add_job_st.reset()
    print("[STATE] Job module reset")


async def decide_action(action, dom, url, goal="", email=None, password=None, page=None):
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

    # Phase 3: Job action
    if action == "add_job":
        return await _decide_add_job(els, url, goal)

    return {"action": "wait", "seconds": 1}