# import re
# from datetime import datetime, timedelta

# from utils.login       import login_done, handle_login, reset_login
# from utils.nav         import nav_done,   handle_nav,   reset_nav
# from utils.dom_scanner import scan_common_dom
# from config.settings   import BASE_URL

# # ============================================================
# # modules/job.py
# #
# # Workflow:
# #   Login -> /projects -> search project -> View ->
# #   Jobs tab -> Add Job -> fill form -> submit (tick button)
# # ============================================================

# NAV_FRAGMENT = "projects"

# ACTIONS = {
#     "add_job": {
#         "label":        "Create new Job in a Project",
#         "needs_target": ["Project name", "Job name"],
#     },
# }

# ACTION_KEYS = list(ACTIONS.keys())

# # Regex to parse goal string: "add_job job <project_name>"
# _ADD_JOB_RE = re.compile(r"add_job\s+job\s+(.+?)\s*\|\s*(.+?)$", re.IGNORECASE)

# # Fallback if only project name given (no job name)
# _ADD_JOB_RE_SIMPLE = re.compile(r"add_job\s+job\s+(.+?)$", re.IGNORECASE)
# # ============================================================
# # DOM SCANNER
# # ============================================================

# def scan_dom(dom):
#     """
#     Extend common DOM scan with job-specific elements.
#     """
#     result = scan_common_dom(dom)

#     result.update({
#         "nav_projects":   None,   # sidebar nav link -> /projects
#         "search_input":   None,   # project search box
#         "view_btn":       None,   # View button on project row
#         "jobs_tab":       None,   # Jobs tab inside project view
#         "add_job_btn":    None,   # + Add Job inline row trigger
#         "job_name_input": None,   # Job Name text input
#         "job_start_input":None,   # Start date input (type=date)
#         "job_end_input":  None,   # End date input (type=date)
#         "job_hours_input":None,   # Hours number input
#         "job_save_btn":   None,   # Tick/checkmark submit button
#         "job_cancel_btn": None,   # X cancel button
#     })

#     _NAV_TAGS  = ("a", "li", "span")
#     _BTN_TAGS  = ("button", "input")
#     _BTN_TYPES = ("button", "submit", "")

#     for el in dom:
#         tag   = (el.get("tag")         or "").lower()
#         etype = (el.get("type")        or "").lower()
#         eid   = (el.get("id")          or "").lower()
#         label = (el.get("label")       or "").lower().strip()
#         text  = (el.get("text")        or "").lower().strip()
#         role  = (el.get("role")        or "").lower()
#         ph    = (el.get("placeholder") or "").lower()
#         cls   = (el.get("class")       or "").lower()
#         lv    = label + " " + text
#         comb  = lv + " " + eid + " " + ph + " " + cls

#         # ── Nav link ──────────────────────────────────────────
#         if tag in _NAV_TAGS and "project" in comb and not result["nav_projects"]:
#             result["nav_projects"] = el

#         # ── Search input ──────────────────────────────────────
#         if (tag == "input" and etype in ("text", "search")
#                 and ("search" in ph or "search" in eid or "search" in cls)
#                 and not result["search_input"]):
#             result["search_input"] = el

#         # ── View button ───────────────────────────────────────
#         if tag in _BTN_TAGS and etype in _BTN_TYPES:
#             if text in ("view", "view details") or label == "view":
#                 if not result["view_btn"]:
#                     result["view_btn"] = el

#         # ── Jobs tab ──────────────────────────────────────────
#         # id="project-jobs-tab" or role=tab + text=jobs
#         if (tag == "button" and role == "tab"
#                 and "jobs" in text
#                 and not result["jobs_tab"]):
#             result["jobs_tab"] = el
#         if eid == "project-jobs-tab" and not result["jobs_tab"]:
#             result["jobs_tab"] = el

#         # ── Add Job button ────────────────────────────────────
#         # Usually a small button/link with text "add job" or "+ add job"
#         if tag in _BTN_TAGS and ("add job" in lv or "add job" in comb):
#             if not result["add_job_btn"]:
#                 result["add_job_btn"] = el

#         # ── Job form fields ───────────────────────────────────
#         # Job Name — text input with placeholder "e.g., Discovery..."
#         if (tag == "input" and etype == "text"
#                 and ("discovery" in ph or "development" in ph
#                      or "job" in ph or eid == "_r_rk_")
#                 and not result["job_name_input"]):
#             result["job_name_input"] = el

#         # Start date — type=date, appears before end date
#         if tag == "input" and etype == "date":
#             if not result["job_start_input"]:
#                 result["job_start_input"] = el
#             elif not result["job_end_input"]:
#                 result["job_end_input"] = el

#         # Hours — type=number with min=0
#         if (tag == "input" and etype == "number"
#                 and not result["job_hours_input"]):
#             result["job_hours_input"] = el

#         # Save (tick) button — enabled MuiIconButton with checkmark SVG
#         # The disabled one has tabindex="-1" and disabled attribute
#         # The enabled X (cancel) button has tabindex="0"
#         if tag == "button" and "muiiconbutton" in cls:
#             if "disabled" not in cls and "tabindex" not in el.get("selector", ""):
#                 # Two icon buttons: save (check) and cancel (X)
#                 # Save is first, Cancel is second
#                 if not result["job_save_btn"]:
#                     result["job_save_btn"] = el
#                 elif not result["job_cancel_btn"]:
#                     result["job_cancel_btn"] = el

#     return result


# # ============================================================
# # ADD JOB STATE + LOGIC
# # ============================================================

# class _AddJobState:
#     def __init__(self):
#         self.project_name   = ""    # project to open

#         # Step flags
#         self.search_typed   = False  # Step 2: typed project name in search
#         self.view_clicked   = False  # Step 3: clicked View on project row
#         self.jobs_clicked   = False  # Step 4: clicked Jobs tab
#         self.add_clicked    = False  # Step 5: clicked Add Job
#         self.form_filled    = False  # Step 6: filled form fields
#         self.submitted      = False  # Step 7: clicked save (tick)
#         self.verified       = False  # done

#         # Navigation
#         self._nav_fired     = False

#         # Wait counters
#         self._search_wait   = 0
#         self._view_wait     = 0
#         self._jobs_wait     = 0
#         self._add_wait      = 0
#         self._form_wait     = 0
#         self._submit_wait   = 0

#         self.interacted     = set()
#         self.MAX_WAIT       = 4

#     def reset(self):
#         self.__init__()

# _add_job_st = _AddJobState()


# async def _decide_add_job(els, url, goal):
#     s = _add_job_st

#     # Parse project name from goal on first call
#     if not s.project_name:
#         m = _ADD_JOB_RE.search(goal)
#         if m:
#             s.project_name = m.group(1).strip()
#             s.job_name_override = m.group(2).strip()
#             print("[JOB] Project target: '{}'|Job name override: '{}'".format(s.project_name, s.job_name_override))
#         else:
#             m2= _ADD_JOB_RE_SIMPLE.search(goal)
#             if m2:
#                 s.project_name = m2.group(1).strip()
#                 print("[JOB] Project target: '{}'".format(s.project_name))  

#     if s.verified:
#         return {"action": "done", "result": "PASS",
#                 "reason": "Job added to project '{}'".format(s.project_name)}

#     # ── Step 7: Verify after submit ───────────────────────────
#     if s.submitted:
#         job_name_still_visible = bool(els.get("job_name_input"))
#         job_in_dom = any(
#             (s.job_name_override or "").lower() in (el.get("text") or "").lower()
#             for el in (els.get("dom_raw") or [])
#         ) if s.job_name_override else False

#         if not job_name_still_visible or job_in_dom or els["success_toast"]:
#             s.verified = True
#             return {"action": "done", "result": "PASS",
#                     "reason": "Job '{}' added to project '{}'".format(
#                         s.job_name_override or "job", s.project_name)}
#         s._submit_wait += 1
#         print("[JOB-VERIFY] Waiting ({}/{})".format(s._submit_wait, s.MAX_WAIT))
#         if s._submit_wait >= s.MAX_WAIT:
#             s.verified = True
#             return {"action": "done", "result": "PASS",
#                     "reason": "Job submitted (save clicked, form closed)"}
#         return {"action": "wait", "seconds": 1}

#     # ── Step 6: Fill form ─────────────────────────────────────
#     if s.add_clicked and not s.form_filled:
#         job_name   = "Job_{}".format(datetime.now().strftime("%H%M%S"))
#         today      = datetime.now()
#         start_date = today.strftime("%Y-%m-%d")               # type=date format
#         end_date   = (today + timedelta(days=7)).strftime("%Y-%m-%d")
#         hours      = "8"

#         print("[JOB] Filling form: name={} start={} end={} hours={}".format(
#             job_name, start_date, end_date, hours))

#         s.form_filled = True
#         return {
#             "action": "fill_job_form",
#             "params": {
#                 "job_name":   job_name,
#                 "start_date": start_date,
#                 "end_date":   end_date,
#                 "hours":      hours,
#             }
#         }

#     # ── Step 6b: Submit (click tick/save button) ──────────────
#     if s.form_filled and not s.submitted:
#         # Save button — the enabled MuiIconButton (checkmark)
#         # After filling form it becomes enabled
#         # Selector: button.MuiIconButton-colorPrimary (not disabled)
#         print("[JOB] Step 6b: Clicking save (tick) button")
#         s.submitted = True
#         return {
#     "action":        "js_click_save_job",
#     "extra_wait_ms": 1500,
#     "soft_fail":     True,
# }
#     # ── Step 5: Click Add Job ─────────────────────────────────
#     if s.jobs_clicked and not s.add_clicked:
#         ab = els["add_job_btn"]
#         if ab and ab["selector"] not in s.interacted:
#             s.interacted.add(ab["selector"])
#             s.add_clicked = True
#             print("[JOB] Step 5: Clicking Add Job")
#             return {"action": "click", "selector": ab["selector"],
#                     "extra_wait_ms": 800}
#         s._add_wait += 1
#         print("[JOB] Step 5: Add Job button not found ({}/{})".format(
#             s._add_wait, s.MAX_WAIT))
#         if s._add_wait >= s.MAX_WAIT:
#             return {"action": "done", "result": "FAIL",
#                     "reason": "'Add Job' button not found on Jobs tab"}
#         return {"action": "wait", "seconds": 1}

#     # ── Step 4: Click Jobs tab ────────────────────────────────
#     if s.view_clicked and not s.jobs_clicked:
#         jt = els["jobs_tab"]
#         if jt and jt["selector"] not in s.interacted:
#             s.interacted.add(jt["selector"])
#             s.jobs_clicked = True
#             print("[JOB] Step 4: Clicking Jobs tab")
#             return {"action": "click", "selector": jt["selector"],
#                     "extra_wait_ms": 800}
#         # Also try by id directly
#         s._jobs_wait += 1
#         print("[JOB] Step 4: Jobs tab not found ({}/{})".format(
#             s._jobs_wait, s.MAX_WAIT))
#         if s._jobs_wait >= s.MAX_WAIT:
#             # Fallback: navigate directly by clicking tab with id
#             return {"action": "click",
#                     "selector": "#project-jobs-tab",
#                     "soft_fail": True}
#         return {"action": "wait", "seconds": 1}

#     # ── Step 3: Click View on project row ────────────────────
#     if s.search_typed and not s.view_clicked:
#         vb = els["view_btn"]
#         if vb and vb["selector"] not in s.interacted:
#             s.interacted.add(vb["selector"])
#             s.view_clicked = True
#             print("[JOB] Step 3: Clicking View")
#             return {"action": "click", "selector": vb["selector"],
#                     "extra_wait_ms": 1000}
#         s._view_wait += 1
#         if s._view_wait >= s.MAX_WAIT:
#             return {"action": "done", "result": "FAIL",
#                     "reason": "'View' button not found after search"}
#         return {"action": "wait", "seconds": 1}

#     # ── Step 2: Search for project ────────────────────────────
#     if not s.search_typed:
#         if "projects" not in url.lower():
#             if not s._nav_fired:
#                 s._nav_fired = True
#                 return {"action": "navigate", "url": BASE_URL + "/projects"}
#             return {"action": "wait", "seconds": 1}
#         si = els["search_input"]
#         if si:
#             s.search_typed = True
#             print("[JOB] Step 2: Searching project '{}'".format(s.project_name))
#             return {"action": "type", "selector": si["selector"],
#                     "text": s.project_name}
#         s._search_wait += 1
#         if s._search_wait >= s.MAX_WAIT:
#             return {"action": "done", "result": "FAIL",
#                     "reason": "Search input not found on /projects page"}
#         return {"action": "wait", "seconds": 1}

#     return {"action": "wait", "seconds": 1}


# # ============================================================
# # PUBLIC ENTRY POINT
# # ============================================================

# def reset_state():
#     reset_login()
#     reset_nav()
#     _add_job_st.reset()
#     print("[STATE] Job module reset")


# async def decide_action(action, dom, url, goal="", email=None, password=None):
#     els = scan_dom(dom)

#     # Phase 1: Login
#     if not login_done():
#         step = handle_login(els, email, password, url)
#         if step is None and not login_done():
#             return {"action": "wait", "seconds": 1}
#         if step:
#             return step

#     # Phase 2: Navigate to /projects
#     if not nav_done():
#         step = handle_nav(els, url, NAV_FRAGMENT)
#         if step:
#             return step

#     # Phase 3: Job action
#     if action == "add_job":
#         return await _decide_add_job(els, url, goal)

#     return {"action": "wait", "seconds": 1}


import re
from datetime import datetime, timedelta

from utils.login       import login_done, handle_login, reset_login
from utils.nav         import nav_done,   handle_nav,   reset_nav
from utils.dom_scanner import scan_common_dom
from config.settings   import BASE_URL

# ============================================================
# modules/job.py
#
# Workflow:
#   Login -> /projects -> search project -> View ->
#   Jobs tab -> Add Job -> fill form -> tick button (in form_filler)
# ============================================================

NAV_FRAGMENT = "projects"

ACTIONS = {
    "add_job": {
        "label":        "Create new Job in a Project",
        "needs_target": ["Project name", "Job name"],
    },
}

ACTION_KEYS = list(ACTIONS.keys())

# Goal format: "add_job job <project_name> | <job_name>"
_ADD_JOB_RE        = re.compile(r"add_job\s+job\s+(.+?)\s*\|\s*(.+?)$", re.IGNORECASE)
_ADD_JOB_RE_SIMPLE = re.compile(r"add_job\s+job\s+(.+?)$", re.IGNORECASE)


# ============================================================
# DOM SCANNER
# ============================================================

def scan_dom(dom):
    result = scan_common_dom(dom)
    result.update({
        "nav_projects":    None,
        "search_input":    None,
        "view_btn":        None,
        "jobs_tab":        None,
        "add_job_btn":     None,
        "job_name_input":  None,
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

        if tag == "button" and role == "tab" and "jobs" in text and not result["jobs_tab"]:
            result["jobs_tab"] = el
        if eid == "project-jobs-tab" and not result["jobs_tab"]:
            result["jobs_tab"] = el

        if tag in _BTN_TAGS and ("add job" in lv or "add job" in comb):
            if not result["add_job_btn"]:
                result["add_job_btn"] = el

        # Job name input — detected by placeholder
        if (tag == "input" and etype == "text"
                and ("discovery" in ph or "development" in ph
                     or "e.g" in ph or "testing" in ph)
                and not result["job_name_input"]):
            result["job_name_input"] = el

    return result


# ============================================================
# ADD JOB STATE
# ============================================================

class _AddJobState:
    def __init__(self):
        self.project_name      = ""
        self.job_name_override = ""
        self.search_typed      = False
        self.view_clicked      = False
        self.jobs_clicked      = False
        self.add_clicked       = False
        self.form_filled       = False
        self.submitted         = False
        self.verified          = False
        self._nav_fired        = False
        self._search_wait      = 0
        self._view_wait        = 0
        self._jobs_wait        = 0
        self._add_wait         = 0
        self._submit_wait      = 0
        self.interacted        = set()
        self.MAX_WAIT          = 4

    def reset(self):
        self.__init__()

_add_job_st = _AddJobState()


# ============================================================
# ADD JOB LOGIC
# ============================================================

async def _decide_add_job(els, url, goal):
    s = _add_job_st

    # Parse project + job name from goal on first call
    if not s.project_name:
        m = _ADD_JOB_RE.search(goal)
        if m:
            s.project_name      = m.group(1).strip()
            s.job_name_override = m.group(2).strip()
            print("[JOB] Project: '{}' | Job: '{}'".format(
                s.project_name, s.job_name_override))
        else:
            m2 = _ADD_JOB_RE_SIMPLE.search(goal)
            if m2:
                s.project_name = m2.group(1).strip()
                print("[JOB] Project: '{}'".format(s.project_name))

    if s.verified:
        return {"action": "done", "result": "PASS",
                "reason": "Job '{}' added to project '{}'".format(
                    s.job_name_override or "job", s.project_name)}

    # ── Step 7: Verify ────────────────────────────────────────
    if s.submitted:
        # form row gone = job_name_input disappeared from DOM
        job_form_gone = not bool(els.get("job_name_input"))
        job_in_dom    = any(
            (s.job_name_override or "").lower() in (el.get("text") or "").lower()
            for el in (els.get("dom_raw") or [])
        ) if s.job_name_override else False

        if job_form_gone or job_in_dom or els["success_toast"]:
            s.verified = True
            return {"action": "done", "result": "PASS",
                    "reason": "Job '{}' added to project '{}'".format(
                        s.job_name_override or "job", s.project_name)}
        s._submit_wait += 1
        print("[JOB-VERIFY] Waiting ({}/{})".format(s._submit_wait, s.MAX_WAIT))
        if s._submit_wait >= s.MAX_WAIT:
            s.verified = True
            return {"action": "done", "result": "PASS",
                    "reason": "Job submitted (tick clicked)"}
        return {"action": "wait", "seconds": 1}

    # ── Step 6: Fill form (tick click happens inside form_filler) ──
    if s.add_clicked and not s.form_filled:
        job_name   = s.job_name_override or "Job_{}".format(
            datetime.now().strftime("%H%M%S"))
        today      = datetime.now()
        start_date = today.strftime("%Y-%m-%d")
        end_date   = (today + timedelta(days=7)).strftime("%Y-%m-%d")

        print("[JOB] Filling form: name='{}' start={} end={}".format(
            job_name, start_date, end_date))

        s.form_filled = True
        s.submitted   = True   # tick is clicked inside fill_job_form
        return {
            "action": "fill_job_form",
            "params": {
                "job_name":   job_name,
                "start_date": start_date,
                "end_date":   end_date,
                "hours":      "8",
            }
        }

    # ── Step 5: Click Add Job ─────────────────────────────────
    if s.jobs_clicked and not s.add_clicked:
        ab = els["add_job_btn"]
        if ab and ab["selector"] not in s.interacted:
            s.interacted.add(ab["selector"])
            s.add_clicked = True
            print("[JOB] Step 5: Clicking Add Job")
            return {"action": "click", "selector": ab["selector"],
                    "extra_wait_ms": 800}
        s._add_wait += 1
        print("[JOB] Step 5: Add Job not found ({}/{})".format(
            s._add_wait, s.MAX_WAIT))
        if s._add_wait >= s.MAX_WAIT:
            return {"action": "done", "result": "FAIL",
                    "reason": "'Add Job' button not found"}
        return {"action": "wait", "seconds": 1}

    # ── Step 4: Click Jobs tab ────────────────────────────────
    if s.view_clicked and not s.jobs_clicked:
        jt = els["jobs_tab"]
        if jt and jt["selector"] not in s.interacted:
            s.interacted.add(jt["selector"])
            s.jobs_clicked = True
            print("[JOB] Step 4: Clicking Jobs tab")
            return {"action": "click", "selector": jt["selector"],
                    "extra_wait_ms": 800}
        s._jobs_wait += 1
        if s._jobs_wait >= s.MAX_WAIT:
            return {"action": "click", "selector": "#project-jobs-tab",
                    "soft_fail": True}
        return {"action": "wait", "seconds": 1}

    # ── Step 3: Click View ────────────────────────────────────
    if s.search_typed and not s.view_clicked:
        vb = els["view_btn"]
        if vb and vb["selector"] not in s.interacted:
            s.interacted.add(vb["selector"])
            s.view_clicked = True
            print("[JOB] Step 3: Clicking View")
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
            print("[JOB] Step 2: Searching '{}'".format(s.project_name))
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
    _add_job_st.reset()
    print("[STATE] Job module reset")


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

    if action == "add_job":
        return await _decide_add_job(els, url, goal)

    return {"action": "wait", "seconds": 1}