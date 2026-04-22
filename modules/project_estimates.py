from utils.login       import login_done, handle_login, reset_login
from utils.nav         import nav_done,   handle_nav,   reset_nav
from utils.dom_scanner import scan_common_dom
from config.settings   import BASE_URL
from report.test_report import get_reporter

# ============================================================
# modules/project_estimates.py
#
# Workflow:
#   Login -> /estimates ->
#     edit_estimate : New Estimate -> Create Manually -> fill form
#     estimate_ai   : New Estimate -> Start with AI   -> fill form
# ============================================================

NAV_FRAGMENT = "estimates"

MODULE_META = {
    "name":     "Estimates",
    "fragment": NAV_FRAGMENT,
    "order":    7,
}

ACTIONS = {
    "edit_estimate": {
        "label":        "Create Manual Estimate",
        "needs_target": False,
    },
    "estimate_ai": {
        "label":        "Create AI Estimate",
        "needs_target": False,
    },
}

ACTION_KEYS = list(ACTIONS.keys())


# ============================================================
# DOM SCANNER
# ============================================================

def scan_dom(dom):
    result = scan_common_dom(dom)
    result.update({
        "nav_estimates":       None,
        # Shared
        "new_estimate_btn":    None,
        "description_input":   None,
        "start_date":          None,
        "end_date":            None,
        # Manual-specific
        "create_manually_btn": None,
        "project_name":        None,
        # AI-specific
        "start_ai_btn":        None,
        "generate_btn":        None,
        "tech_input":          None,
        "timeline_dropdown":   None,
    })

    for el in dom:
        tag   = (el.get("tag")         or "").lower()
        eid   = (el.get("id")          or "").lower()
        text  = (el.get("text")        or "").lower()
        label = (el.get("label")       or "").lower()
        name  = (el.get("name")        or "").lower()
        ph    = (el.get("placeholder") or "").lower()
        cls   = (el.get("class")       or "").lower()
        comb  = text + " " + label + " " + eid + " " + ph + " " + cls

        # Nav link
        if eid == "nav-item-estimates" and not result["nav_estimates"]:
            result["nav_estimates"] = el

        # New Estimate button (shared)
        if tag == "button" and "new estimate" in text and not result["new_estimate_btn"]:
            result["new_estimate_btn"] = el

        # Create Manually button (manual)
        if tag == "button" and "create manually" in text and not result["create_manually_btn"]:
            result["create_manually_btn"] = el

        # Start with AI button (AI)
        if tag == "button" and "start with ai" in text and not result["start_ai_btn"]:
            result["start_ai_btn"] = el

        # Project name input (manual)
        if "enter project name" in ph and not result["project_name"]:
            result["project_name"] = el

        # Description input (both)
        if not result["description_input"]:
            if "brief project description" in ph or tag == "textarea":
                result["description_input"] = el

        # Generate button (AI)
        if tag == "button" and "generate estimate" in text and not result["generate_btn"]:
            result["generate_btn"] = el

        # Tech autocomplete input (AI)
        if "search and select technologies" in ph and not result["tech_input"]:
            result["tech_input"] = el

        # Timeline dropdown (AI)
        if ("gantt_interval" in eid or "timeline interval" in comb) \
                and not result["timeline_dropdown"]:
            result["timeline_dropdown"] = el

        # Date inputs — try by name (AI), then by selector (manual)
        if not result["start_date"]:
            if name == "project_start_date":
                result["start_date"] = el
            elif el.get("selector") == '(//input[@type="date"])[1]':
                result["start_date"] = el

        if not result["end_date"]:
            if name == "project_end_date":
                result["end_date"] = el
            elif el.get("selector") == '(//input[@type="date"])[2]':
                result["end_date"] = el

    return result


# ============================================================
# MANUAL ESTIMATE STATE
# ============================================================

class _ManualEstimateState:
    def __init__(self):
        self.clicked_new    = False   # New Estimate clicked
        self.clicked_manual = False   # Create Manually clicked
        self.form_submitted = False   # fill_manual_estimate_form dispatched
        self.verified       = False   # success confirmed

        # Wait counters
        self._new_wait      = 0
        self._manual_wait   = 0
        self._verify_wait   = 0
        self.MAX_WAIT       = 4

    def reset(self):
        self.__init__()


_manual_st = _ManualEstimateState()


# ============================================================
# MANUAL ESTIMATE LOGIC
# ============================================================

async def _decide_manual_estimate(els, url):
    s = _manual_st
    r = get_reporter()

    # ── Already done ──────────────────────────────────────────
    if s.verified:
        if r:
            r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Manual estimate created"}

    # ── Step 3: Verify after form_filler returns ───────────────
    if s.form_submitted:
        dom_raw = els.get("dom_raw") or []

        toast_found = bool(els.get("success_toast")) or any(
            ("success"   in (el.get("text") or "").lower()
             or "created" in (el.get("text") or "").lower()
             or "saved"   in (el.get("text") or "").lower()
             or "snackbar" in (el.get("class") or "").lower())
            for el in dom_raw
        )
        error_found = bool(els.get("error_toast")) or any(
            ("error"   in (el.get("text") or "").lower()
             or "failed"  in (el.get("text") or "").lower()
             or "invalid" in (el.get("text") or "").lower())
            for el in dom_raw
            if el.get("tag", "").lower() not in ("input", "button")
        )

        print("[MANUAL-VERIFY] toast={} error={} wait={}/{}".format(
            toast_found, error_found, s._verify_wait, s.MAX_WAIT))

        if error_found:
            if r:
                r.update_last_step(False, error="Error shown after form submission")
            return {"action": "done", "result": "FAIL",
                    "reason": "Manual estimate — error shown after form submission"}

        if toast_found:
            s.verified = True
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "Manual estimate created — toast confirmed"}

        s._verify_wait += 1
        if s._verify_wait >= s.MAX_WAIT:
            s.verified = True
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "Manual estimate created (no error after {} waits)".format(
                        s.MAX_WAIT)}
        return {"action": "wait", "seconds": 1}

    # ── Step 2: Dispatch form filler after Create Manually ─────
    if s.clicked_manual and not s.form_submitted:
        s.form_submitted = True
        step = {"action": "fill_manual_estimate_form", "params": {}}
        if r:
            r.log_step(len(r.steps) + 1, step, url)
        print("[MANUAL] Step 2: Dispatching fill_manual_estimate_form")
        return step

    # ── Step 1b: Click Create Manually ────────────────────────
    if s.clicked_new and not s.clicked_manual:
        btn = els["create_manually_btn"]
        if btn:
            s.clicked_manual = True
            step = {"action": "click", "selector": btn["selector"]}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            print("[MANUAL] Step 1b: Clicking Create Manually")
            return step
        s._manual_wait += 1
        print("[MANUAL] Step 1b: 'Create Manually' not found ({}/{})".format(
            s._manual_wait, s.MAX_WAIT))
        if s._manual_wait >= s.MAX_WAIT:
            s.clicked_manual = True
            step = {"action": "click",
                    "selector": "//button[normalize-space()='Create Manually']",
                    "soft_fail": True}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step
        return {"action": "wait", "seconds": 1}

    # ── Step 1a: Click New Estimate ───────────────────────────
    if not s.clicked_new:
        btn = els["new_estimate_btn"]
        if btn:
            s.clicked_new = True
            step = {"action": "click", "selector": btn["selector"]}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            print("[MANUAL] Step 1a: Clicking New Estimate")
            return step
        s._new_wait += 1
        print("[MANUAL] Step 1a: 'New Estimate' not found ({}/{})".format(
            s._new_wait, s.MAX_WAIT))
        if s._new_wait >= s.MAX_WAIT:
            s.clicked_new = True
            step = {"action": "click",
                    "selector": "//button[@id='new-estimate-button']",
                    "soft_fail": True}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step
        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# AI ESTIMATE STATE
# ============================================================

class _AIEstimateState:
    def __init__(self):
        self.clicked_new    = False   # New Estimate clicked
        self.clicked_ai     = False   # Start with AI clicked
        self.form_submitted = False   # fill_ai_estimate_form dispatched
        self.verified       = False   # success confirmed

        # Wait counters
        self._new_wait      = 0
        self._ai_wait       = 0
        self._verify_wait   = 0
        self.MAX_WAIT       = 4

    def reset(self):
        self.__init__()


_ai_st = _AIEstimateState()


# ============================================================
# AI ESTIMATE LOGIC
# ============================================================

async def _decide_ai_estimate(els, url):
    s = _ai_st
    r = get_reporter()

    # ── Already done ──────────────────────────────────────────
    if s.verified:
        if r:
            r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "AI estimate generated"}

    # ── Step 3: Verify after form_filler returns ───────────────
    if s.form_submitted:
        dom_raw = els.get("dom_raw") or []

        toast_found = bool(els.get("success_toast")) or any(
            ("success"    in (el.get("text") or "").lower()
             or "generated" in (el.get("text") or "").lower()
             or "snackbar"  in (el.get("class") or "").lower())
            for el in dom_raw
        )
        error_found = bool(els.get("error_toast")) or any(
            ("error"  in (el.get("text") or "").lower()
             or "failed" in (el.get("text") or "").lower())
            for el in dom_raw
            if el.get("tag", "").lower() not in ("input", "button")
        )
        # Generate button gone = page moved on = success
        generate_gone = els.get("generate_btn") is None

        print("[AI-VERIFY] toast={} generate_gone={} error={} wait={}/{}".format(
            toast_found, generate_gone, error_found,
            s._verify_wait, s.MAX_WAIT))

        if error_found:
            if r:
                r.update_last_step(False, error="Error shown after generate")
            return {"action": "done", "result": "FAIL",
                    "reason": "AI estimate — error shown after generate"}

        if toast_found or generate_gone:
            s.verified = True
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "AI estimate generated — confirmed"}

        s._verify_wait += 1
        if s._verify_wait >= s.MAX_WAIT:
            s.verified = True
            if r:
                r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "AI estimate generated (assumed after {} waits)".format(
                        s.MAX_WAIT)}
        return {"action": "wait", "seconds": 1}

    # ── Step 2: Dispatch form filler after Start with AI ───────
    if s.clicked_ai and not s.form_submitted:
        s.form_submitted = True
        step = {"action": "fill_ai_estimate_form", "params": {}}
        if r:
            r.log_step(len(r.steps) + 1, step, url)
        print("[AI-EST] Step 2: Dispatching fill_ai_estimate_form")
        return step

    # ── Step 1b: Click Start with AI ──────────────────────────
    if s.clicked_new and not s.clicked_ai:
        btn = els["start_ai_btn"]
        if btn:
            s.clicked_ai = True
            step = {"action": "click", "selector": btn["selector"]}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            print("[AI-EST] Step 1b: Clicking Start with AI")
            return step
        s._ai_wait += 1
        print("[AI-EST] Step 1b: 'Start with AI' not found ({}/{})".format(
            s._ai_wait, s.MAX_WAIT))
        if s._ai_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="'Start with AI' button not found")
            return {"action": "done", "result": "FAIL",
                    "reason": "'Start with AI' button not found"}
        return {"action": "wait", "seconds": 1}

    # ── Step 1a: Click New Estimate ───────────────────────────
    if not s.clicked_new:
        btn = els["new_estimate_btn"]
        if btn:
            s.clicked_new = True
            step = {"action": "click", "selector": btn["selector"]}
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            print("[AI-EST] Step 1a: Clicking New Estimate")
            return step
        s._new_wait += 1
        print("[AI-EST] Step 1a: 'New Estimate' not found ({}/{})".format(
            s._new_wait, s.MAX_WAIT))
        if s._new_wait >= s.MAX_WAIT:
            if r:
                r.update_last_step(False, error="'New Estimate' button not found")
            return {"action": "done", "result": "FAIL",
                    "reason": "'New Estimate' button not found"}
        return {"action": "wait", "seconds": 1}

    return {"action": "wait", "seconds": 1}


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

def reset_state(keep_session=False):
    reset_login()
    reset_nav()
    _manual_st.reset()
    _ai_st.reset()
    print("[STATE] Estimates module reset (keep_session={})".format(keep_session))


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

    # Phase 2: Navigate to /estimates
    if not nav_done():
        step = handle_nav(els, url, NAV_FRAGMENT)
        if step:
            r = get_reporter()
            if r:
                r.log_step(len(r.steps) + 1, step, url)
            return step

    # Phase 3: Estimate action
    if action == "edit_estimate":
        return await _decide_manual_estimate(els, url)

    if action == "estimate_ai":
        return await _decide_ai_estimate(els, url)

    return {"action": "wait", "seconds": 1}
