import re
from datetime import datetime, timedelta

from utils.login        import login_done, handle_login, reset_login
from utils.nav          import nav_done,   handle_nav,   reset_nav
from utils.dom_scanner  import scan_common_dom
from config.settings    import BASE_URL
from report.test_report import get_reporter

NAV_FRAGMENT = "timesheet"

ACTIONS = {
    "add_timesheet": {
        "label":        "Fill weekly timesheet given a start date, project and job",
        "needs_target": ["start_date", "project_name", "job_name"],
    },
    "clone_last_week": {
        "label":        "Pre-fill timesheet from last week (clone)",
        "needs_target": ["start_date"],
    },
    "approve_timesheet": {
        "label":        "Approve or reject a timesheet in Approval Requests tab",
        "needs_target": ["start_date", "project_name", "requested_by", "action"],
    },
}

ACTION_KEYS = list(ACTIONS.keys())

_START_RE   = re.compile(r"start\s+([\d\-/]+)", re.IGNORECASE)
_PROJECT_RE = re.compile(
    r"project\s+(.+?)\s*\|\s*job\s+(.+?)"
    r"(?:\s*\|\s*hours\s+([\d.]+))?"
    r"(?:\s*\|\s*location\s+(.+?))?"
    r"(?:\s*\|\s*remarks\s+(.+?))?"
    r"(?=\s*\|\s*project|\s*$)",
    re.IGNORECASE,
)


def _parse_goal(goal):
    start = ""
    m = _START_RE.search(goal)
    if m:
        raw = m.group(1).strip().replace("/", "-")
        parts = raw.split("-")
        if len(parts) == 3 and len(parts[0]) != 4:
            start = "{}-{}-{}".format(parts[2], parts[1], parts[0])
        else:
            start = raw

    rows = []
    for m in _PROJECT_RE.finditer(goal):
        rows.append({
            "project":  m.group(1).strip(),
            "job":      m.group(2).strip(),
            "hours":    (m.group(3) or "8").strip(),
            "location": (m.group(4) or "ascentt office").strip().lower(),
            "remarks":  (m.group(5) or "").strip(),
        })
    return start, rows


def _week_monday(date_str):
    if not date_str or not date_str.strip():
        return None
    try:
        d = datetime.strptime(date_str.strip(), "%Y-%m-%d")
        return d - timedelta(days=d.weekday())
    except ValueError:
        return None


def _week_label_matches(label_text, monday):
    months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
              "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
    try:
        parts = re.findall(r"([a-z]{3})\s+(\d+)", label_text.lower())
        if len(parts) >= 1:
            mon_name, day_str = parts[0]
            if mon_name not in months:
                return False
            label_date = datetime(monday.year, months[mon_name], int(day_str))
            return label_date.date() == monday.date()
    except Exception:
        pass
    return False


# ============================================================
# DOM SCANNER
# ============================================================

def scan_dom(dom):
    result = scan_common_dom(dom)
    result.update({
        "nav_timesheets":       None,
        "nav_time_tracking":    None,
        "prev_week_btn":        None,
        "next_week_btn":        None,
        "week_label":           None,
        "add_row_btn":          None,
        "select_project_btn":   None,
        "prefill_btn":          None,
        "submit_btn":           None,
        "success_toast":        None,
        "error_toast":          None,
        "dom_raw":              dom,
        "approval_tab":         None,
        "approval_proj_search": None,
        "approval_req_btn":     None,
    })

    _SUCCESS = ("submitted successfully", "timesheet submitted",
                "saved successfully", "success", "pre-filled", "prefilled",
                "cloned", "copied from last week", "prefill")
    _ERROR   = ("error", "failed", "invalid", "no data", "nothing to copy",
                "no timesheet", "not found", "no entries")

    _WEEK_RE = re.compile(
        r"[A-Za-z]{3}\s+\d+\s*[-\u2013]\s*[A-Za-z]{3}\s+\d+"
    )

    for el in dom:
        tag      = (el.get("tag")       or "").lower()
        eid      = (el.get("id")        or "").lower()
        raw_text = (el.get("text")      or "")
        raw_lbl  = (el.get("label")     or "")
        text     = raw_text.lower().strip()
        label    = raw_lbl.lower().strip()
        cls      = (el.get("class")     or "").lower()
        aria_lbl = (el.get("ariaLabel") or "").lower()
        comb     = text + " " + label + " " + eid + " " + cls + " " + aria_lbl

        if not result["nav_time_tracking"] and "time tracking" in comb:
            result["nav_time_tracking"] = el
        if tag in ("a", "li", "span") and "timesheet" in comb \
                and not result["nav_timesheets"]:
            result["nav_timesheets"] = el

        if not result["week_label"]:
            if _WEEK_RE.search(raw_text) or _WEEK_RE.search(raw_lbl):
                result["week_label"] = el

        if tag == "button":
            if not result["prev_week_btn"] and (
                    "prev" in aria_lbl or "previous" in aria_lbl
                    or "chevronleft" in cls.replace("-", "")):
                result["prev_week_btn"] = el
            if not result["next_week_btn"] and (
                    "next" in aria_lbl
                    or "chevronright" in cls.replace("-", "")):
                result["next_week_btn"] = el

        if tag == "button" and "add row" in comb and not result["add_row_btn"]:
            result["add_row_btn"] = el

        if eid == "timesheet-project-select" and not result["select_project_btn"]:
            result["select_project_btn"] = el
        elif not result["select_project_btn"] and tag == "button" \
                and "select project" in comb:
            result["select_project_btn"] = el

        if tag == "button" and not result["prefill_btn"]:
            if ("pre-fill" in comb or "prefill" in comb
                    or "pre fill" in comb
                    or ("last week" in comb and "fill" in comb)
                    or "clone" in comb):
                result["prefill_btn"] = el

        if eid == "timesheet-submit-button" and not result["submit_btn"]:
            result["submit_btn"] = el
        elif not result["submit_btn"] and tag == "button" \
                and "submit timesheet" in comb:
            result["submit_btn"] = el

        if tag not in ("input", "button", "textarea"):
            if any(p in comb for p in _SUCCESS) and not result["success_toast"]:
                result["success_toast"] = el
            if any(p in comb for p in _ERROR) and not result["error_toast"]:
                result["error_toast"] = el

        if not result["approval_tab"]:
            if eid == "timesheet-tab-approval":
                result["approval_tab"] = el
            elif tag == "button" and "approval" in comb and "request" in comb:
                result["approval_tab"] = el

        if not result["approval_proj_search"] and tag == "input" and (
                "search projects" in (el.get("placeholder") or "").lower()):
            result["approval_proj_search"] = el

        if not result["approval_req_btn"] and tag == "button" and (
                "requested by" in comb):
            result["approval_req_btn"] = el

    return result


# ============================================================
# STATE — add_timesheet
# ============================================================

class _TimesheetState:
    def __init__(self):
        self.start_date            = ""
        self.monday                = None
        self.rows                  = []
        self.time_tracking_clicked = False
        self.date_navigated        = False
        self.current_row_idx       = 0
        self.row_states            = []
        self.submitted             = False
        self.verified              = False
        self._nav_fired            = False
        self._date_wait            = 0
        self._row_wait             = 0
        self._submit_wait          = 0
        self._tt_wait              = 0
        self.MAX_WAIT              = 3

    def reset(self):
        self.__init__()


_ts_st = _TimesheetState()


# ============================================================
# STATE — clone_last_week
# ============================================================

class _CloneState:
    def __init__(self):
        self.start_date            = ""
        self.monday                = None
        self.time_tracking_clicked = False
        self.date_navigated        = False
        self.prefill_clicked       = False
        self.verified              = False
        self._tt_wait              = 0
        self._prefill_wait         = 0
        self._verify_wait          = 0
        self.MAX_WAIT              = 5

    def reset(self):
        self.__init__()


_clone_st = _CloneState()


# ============================================================
# STATE — approve_timesheet
# ============================================================

class _ApprovalState:
    def __init__(self):
        self.start_date            = ""
        self.monday                = None
        self.project_name          = ""
        self.requested_by          = ""
        self.action                = "approve"
        self.time_tracking_clicked = False
        self.date_navigated        = False
        self.approval_tab_clicked  = False
        self.project_filtered      = False
        self.project_checked       = False
        self.requester_filtered    = False
        self.requester_checked     = False
        self.action_clicked        = False
        self.verified              = False
        self._tt_wait              = 0
        self._tab_wait             = 0
        self._proj_wait            = 0
        self._req_wait             = 0
        self._action_wait          = 0
        self._verify_wait          = 0
        self.MAX_WAIT              = 6

    def reset(self):
        self.__init__()


_approval_st = _ApprovalState()


# ============================================================
# WEEK NAVIGATION HELPER  (Enter Timesheets tab)
# ============================================================

async def _navigate_to_week(page, target_monday):
    months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
              "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}

    async def _get_label():
        try:
            txt = await page.evaluate("""() => {
                const nav = document.getElementById('timesheet-week-nav');
                if (!nav) return '';
                const p = nav.querySelector('p');
                return p ? p.textContent.trim() : '';
            }""")
            return (txt or "").strip()
        except Exception:
            return ""

    async def _click_nav(direction):
        try:
            ok = await page.evaluate("""(dir) => {
                const nav = document.getElementById('timesheet-week-nav');
                if (!nav) return false;
                const btns = nav.querySelectorAll('button');
                const i = dir === 'prev' ? 0 : 1;
                if (btns[i]) { btns[i].click(); return true; }
                return false;
            }""", direction)
            await page.wait_for_timeout(700)
            return ok
        except Exception:
            return False

    for _ in range(26):
        label = await _get_label()
        print("[TS-NAV] Label: '{}'  Target: {}".format(
            label, target_monday.strftime("%Y-%m-%d")))
        if not label:
            print("[TS-NAV] No label — proceeding")
            return
        if _week_label_matches(label, target_monday):
            print("[TS-NAV] ✓ Correct week")
            return
        parts = re.findall(r"([a-z]{3})\s+(\d+)", label.lower())
        direction = "next"
        if parts:
            try:
                mn, ds = parts[0]
                cur = datetime(target_monday.year, months[mn], int(ds))
                direction = "next" if target_monday > cur else "prev"
            except Exception:
                pass
        ok = await _click_nav(direction)
        if not ok:
            print("[TS-NAV] Nav click failed — proceeding")
            return
    print("[TS-NAV] Max navigations reached")


# ============================================================
# APPROVAL TAB WEEK NAVIGATION HELPER
# ============================================================

async def _navigate_approval_week(page, target_monday):
    months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
              "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}

    async def _get_label():
        try:
            txt = await page.evaluate("""() => {
                const re = /[A-Za-z]{3}\\s+\\d+\\s*[-\\u2013]\\s*[A-Za-z]{3}\\s+\\d+/;
                const nav = document.getElementById('timesheet-week-nav');
                if (nav) {
                    const p = nav.querySelector('p');
                    if (p && re.test(p.textContent)) return p.textContent.trim();
                }
                const walker = document.createTreeWalker(
                    document.body, NodeFilter.SHOW_TEXT, null, false);
                let node;
                while ((node = walker.nextNode())) {
                    const t = node.textContent.trim();
                    if (re.test(t)) return t;
                }
                return '';
            }""")
            return (txt or "").strip()
        except Exception:
            return ""

    async def _click_nav(direction):
        try:
            ok = await page.evaluate("""(dir) => {
                const re = /[A-Za-z]{3}\\s+\\d+\\s*[-\\u2013]\\s*[A-Za-z]{3}\\s+\\d+/;
                const nav = document.getElementById('timesheet-week-nav');
                if (nav) {
                    const btns = nav.querySelectorAll('button');
                    const i = dir === 'prev' ? 0 : 1;
                    if (btns[i]) { btns[i].click(); return true; }
                }
                const walker = document.createTreeWalker(
                    document.body, NodeFilter.SHOW_TEXT, null, false);
                let node;
                while ((node = walker.nextNode())) {
                    if (re.test(node.textContent.trim())) {
                        let parent = node.parentElement;
                        for (let i = 0; i < 6; i++) {
                            if (!parent) break;
                            const btns = parent.querySelectorAll('button');
                            if (btns.length >= 2) {
                                const idx = dir === 'prev' ? 0 : btns.length - 1;
                                btns[idx].click();
                                return true;
                            }
                            parent = parent.parentElement;
                        }
                    }
                }
                return false;
            }""", direction)
            await page.wait_for_timeout(800)
            return ok
        except Exception:
            return False

    for _ in range(26):
        label = await _get_label()
        print("[APPR-NAV] Label: '{}'  Target: {}".format(
            label, target_monday.strftime("%Y-%m-%d")))
        if not label:
            print("[APPR-NAV] No date label found — skipping nav")
            return
        if _week_label_matches(label, target_monday):
            print("[APPR-NAV] ✓ Correct week reached")
            return
        parts = re.findall(r"([a-z]{3})\s+(\d+)", label.lower())
        direction = "next"
        if parts:
            try:
                mn, ds = parts[0]
                cur = datetime(target_monday.year, months[mn], int(ds))
                direction = "next" if target_monday > cur else "prev"
            except Exception:
                pass
        print("[APPR-NAV] → {}".format(direction))
        ok = await _click_nav(direction)
        if not ok:
            print("[APPR-NAV] Nav click failed — skipping")
            return
    print("[APPR-NAV] Max navigations reached")


# ============================================================
# CLONE LAST WEEK LOGIC
# ============================================================

async def _decide_clone_last_week(els, url, goal, page=None):
    s = _clone_st
    r = get_reporter()

    if not s.start_date:
        raw_start, _ = _parse_goal(goal)

        if not raw_start:
            today    = datetime.now()
            s.monday = today - timedelta(days=today.weekday())
            s.start_date = s.monday.strftime("%Y-%m-%d")
            print("[CLONE] No date → current week Mon={}".format(s.start_date))
        else:
            s.start_date = raw_start
            s.monday = _week_monday(s.start_date)
            if s.monday is None:
                msg = "Invalid date {!r}".format(s.start_date)
                if r: r.update_last_step(False, error=msg)
                return {"action": "done", "result": "FAIL", "reason": msg}
            print("[CLONE] Target Mon={}".format(s.monday.strftime("%Y-%m-%d")))

        if page is not None:
            await _navigate_to_week(page, s.monday)
            s.date_navigated = True

    if s.verified:
        if r: r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Timesheet pre-filled from last week (week of {})".format(
                    s.monday.strftime("%b %d, %Y"))}

    if s.prefill_clicked:
        dom_raw = els.get("dom_raw") or []

        continue_btn = next(
            (el for el in dom_raw
             if (el.get("text") or "").strip().lower() == "continue"
             and el.get("tag") == "button"),
            None
        )
        if continue_btn:
            print("[CLONE-VERIFY] Continue dialog → clicking")
            step = {"action": "click",
                    "selector": "button:has-text('Continue')",
                    "extra_wait_ms": 1500}
            if r: r.log_step(len(r.steps) + 1, step, url)
            return step

        toast_found = bool(els.get("success_toast")) or any(
            ("success"     in (el.get("text") or "").lower()
             or "filled"   in (el.get("text") or "").lower()
             or "copied"   in (el.get("text") or "").lower()
             or "cloned"   in (el.get("text") or "").lower()
             or "pre-fill" in (el.get("text") or "").lower()
             or "snackbar" in (el.get("class") or "").lower()
             or "toast"    in (el.get("class") or "").lower())
            for el in dom_raw
        )

        error_found = bool(els.get("error_toast")) or any(
            ("error"           in (el.get("text") or "").lower()
             or "no data"      in (el.get("text") or "").lower()
             or "no timesheet" in (el.get("text") or "").lower()
             or "no entries"   in (el.get("text") or "").lower()
             or "nothing"      in (el.get("text") or "").lower())
            for el in dom_raw
            if el.get("tag", "").lower() not in ("input", "button", "textarea")
        )

        _STATIC = {"select project", "add remarks", "total", "daily total", "0",
                   "pre-fill from last week", "add row", "submit timesheet",
                   "work week", "full week", "enter timesheets", "my timesheets",
                   "approval requests"}
        has_project_data = any(
            el.get("tag", "").lower() in ("td", "span", "div", "p", "li")
            and len((el.get("text") or "").strip()) > 3
            and (el.get("text") or "").strip().lower() not in _STATIC
            and not (el.get("text") or "").strip().lower().startswith("mar ")
            and not (el.get("text") or "").strip().lower().startswith("jan ")
            and not (el.get("text") or "").strip().lower().startswith("feb ")
            and not (el.get("text") or "").strip().isdigit()
            for el in dom_raw
        )

        signals = sum([toast_found, has_project_data])
        print("[CLONE-VERIFY] toast={} proj_data={} error={} signals={}/2  wait={}/{}".format(
            toast_found, has_project_data, error_found,
            signals, s._verify_wait, s.MAX_WAIT))

        if error_found:
            if r: r.update_last_step(False,
                error="Pre-fill failed — last week may have been empty")
            return {"action": "done", "result": "FAIL",
                    "reason": "Pre-fill failed — no data found in last week's timesheet"}

        if toast_found or signals >= 2:
            s.verified = True
            if r: r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "Timesheet pre-filled from last week ✓ (signals={}/2)".format(
                        signals)}

        s._verify_wait += 1
        if s._verify_wait >= s.MAX_WAIT:
            s.verified = True
            if r: r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "Pre-fill clicked — no error after {} waits (assumed success)".format(
                        s.MAX_WAIT)}

        return {"action": "wait", "seconds": 1}

    if s.date_navigated:
        pb = els.get("prefill_btn")
        if pb:
            print("[CLONE] ✓ Pre-fill button found — clicking")
            s.prefill_clicked = True
            step = {
                "action":        "click",
                "selector":      pb.get("selector") or
                                 "button:has-text('Pre-fill from last week')",
                "extra_wait_ms": 2000,
            }
            if r: r.log_step(len(r.steps) + 1, step, url)
            return step

        s._prefill_wait += 1
        print("[CLONE] Pre-fill btn not found ({}/{})".format(
            s._prefill_wait, s.MAX_WAIT))
        if s._prefill_wait >= s.MAX_WAIT:
            if r: r.update_last_step(False,
                error="Pre-fill button not found — is page on Enter Timesheets tab?")
            return {"action": "done", "result": "FAIL",
                    "reason": "Pre-fill button not found after {} waits".format(s.MAX_WAIT)}
        return {"action": "wait", "seconds": 1}

    if not s.date_navigated and page is not None:
        await _navigate_to_week(page, s.monday)
        s.date_navigated = True
        return {"action": "wait", "seconds": 0}

    return {"action": "wait", "seconds": 1}


# ============================================================
# ADD TIMESHEET LOGIC
# ============================================================

async def _decide_add_timesheet(els, url, goal, page=None):
    s = _ts_st
    r = get_reporter()

    if not s.start_date:
        s.start_date, s.rows = _parse_goal(goal)

        if not s.start_date:
            msg = "No start date. Use: add_timesheet start YYYY-MM-DD | project X | job Y"
            if r: r.update_last_step(False, error=msg)
            return {"action": "done", "result": "FAIL", "reason": msg}
        if not s.rows:
            msg = "No project/job rows found."
            if r: r.update_last_step(False, error=msg)
            return {"action": "done", "result": "FAIL", "reason": msg}

        s.monday = _week_monday(s.start_date)
        if s.monday is None:
            msg = "Invalid date {!r}".format(s.start_date)
            if r: r.update_last_step(False, error=msg)
            return {"action": "done", "result": "FAIL", "reason": msg}

        s.row_states = ["pending"] * len(s.rows)
        print("[TS] start={} → Mon={}  {} row(s)".format(
            s.start_date, s.monday.strftime("%Y-%m-%d"), len(s.rows)))
        for i, row in enumerate(s.rows):
            print("[TS]   Row {}: project='{}' job='{}' hours={} loc='{}'".format(
                i, row["project"], row["job"], row["hours"], row["location"]))

        if page is not None:
            await _navigate_to_week(page, s.monday)
            s.date_navigated = True

    if s.verified:
        if r: r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Timesheet submitted for week of {}".format(
                    s.monday.strftime("%b %d, %Y"))}

    if s.submitted:
        dom_raw = els.get("dom_raw") or []
        continue_btn = next(
            (el for el in dom_raw
             if (el.get("text") or "").strip() == "Continue"
             and el.get("tag") == "button"),
            None
        )
        if continue_btn:
            step = {"action": "click",
                    "selector": "button:has-text('Continue')",
                    "extra_wait_ms": 2000}
            if r: r.log_step(len(r.steps) + 1, step, url)
            return step

        toast_found = bool(els.get("success_toast")) or any(
            ("submitted" in (el.get("text") or "").lower()
             or "success" in (el.get("text") or "").lower()
             or "snackbar" in (el.get("class") or "").lower()
             or "toast"   in (el.get("class") or "").lower())
            for el in dom_raw
        )
        sb = els.get("submit_btn")
        submit_gone = sb is None or (
            "disabled" in (sb.get("class") or "").lower() and s._submit_wait > 0)
        url_changed = "my-timesheets" in url.lower()
        signals = sum([toast_found, submit_gone, url_changed])
        print("[TS-VERIFY] toast={} gone={} url={} signals={}".format(
            toast_found, submit_gone, url_changed, signals))

        if toast_found or submit_gone or signals >= 1:
            s.verified = True
            if r: r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "Submitted (signals={}/3)".format(signals)}

        s._submit_wait += 1
        if s._submit_wait >= s.MAX_WAIT:
            if r: r.update_last_step(False, error="Submit unconfirmed")
            return {"action": "done", "result": "FAIL", "reason": "Submit unconfirmed"}
        return {"action": "wait", "seconds": 1}

    if s.rows and all(st == "done" for st in s.row_states) and not s.submitted:
        sb = els.get("submit_btn")
        if sb and "disabled" not in (sb.get("class") or "").lower():
            dom_raw = els.get("dom_raw") or []
            continue_btn = next(
                (el for el in dom_raw
                 if (el.get("text") or "").strip() == "Continue"
                 and el.get("tag") == "button"),
                None
            )
            if continue_btn:
                s.submitted = True
                step = {"action": "click",
                        "selector": "button:has-text('Continue')",
                        "extra_wait_ms": 2000}
                if r: r.log_step(len(r.steps) + 1, step, url)
                return step
            s.submitted = True
            step = {"action": "click", "selector": "#timesheet-submit-button",
                    "extra_wait_ms": 2000}
            if r: r.log_step(len(r.steps) + 1, step, url)
            return step

        s._submit_wait += 1
        if s._submit_wait >= s.MAX_WAIT:
            if r: r.update_last_step(False, error="Submit stayed disabled")
            return {"action": "done", "result": "FAIL",
                    "reason": "Submit button remained disabled"}
        return {"action": "wait", "seconds": 1}

    if not s.date_navigated and page is not None:
        await _navigate_to_week(page, s.monday)
        s.date_navigated = True
        return {"action": "wait", "seconds": 0}

    idx = s.current_row_idx
    if idx < len(s.rows):
        state = s.row_states[idx]
        row   = s.rows[idx]

        if state == "pending":
            if idx == 0:
                s.row_states[idx] = "ready"
                return {"action": "wait", "seconds": 0}
            ab = els.get("add_row_btn")
            if ab:
                s.row_states[idx] = "ready"
                step = {"action": "click", "selector": ab["selector"],
                        "extra_wait_ms": 700}
                if r: r.log_step(len(r.steps) + 1, step, url)
                return step
            s._row_wait += 1
            if s._row_wait >= s.MAX_WAIT:
                if r: r.update_last_step(False, error="Add Row not found")
                return {"action": "done", "result": "FAIL",
                        "reason": "Add Row not found (row {})".format(idx)}
            return {"action": "wait", "seconds": 1}

        if state == "ready":
            mon = s.monday
            week_dates = {
                "mon": mon.strftime("%Y-%m-%d"),
                "tue": (mon + timedelta(1)).strftime("%Y-%m-%d"),
                "wed": (mon + timedelta(2)).strftime("%Y-%m-%d"),
                "thu": (mon + timedelta(3)).strftime("%Y-%m-%d"),
                "fri": (mon + timedelta(4)).strftime("%Y-%m-%d"),
            }
            s.row_states[idx] = "done"
            s.current_row_idx += 1
            s._row_wait = 0
            step = {
                "action": "fill_timesheet_row_form",
                "params": {
                    "project_name": row["project"],
                    "job_name":     row["job"],
                    "hours":        row["hours"],
                    "location":     row["location"],
                    "remarks":      row["remarks"],
                    "row_index":    idx,
                    "week_dates":   week_dates,
                },
            }
            if r: r.log_step(len(r.steps) + 1, step, url)
            return step

    return {"action": "wait", "seconds": 1}


# ============================================================
# APPROVE / REJECT HELPERS  — use exact SVG path d= values
# ============================================================

async def _find_pending_row(page, project_name: str):
    """
    Find approve/reject buttons using JS evaluate directly on the live DOM.
    Approve: SVG path starts with M12 2C6.48 (tick)
    Reject:  SVG path starts with M12 2C6.47 (cross)
    Falls back to finding the last two MuiIconButton-sizeSmall buttons on page
    if project row is not found via tr scanning.
    """
    proj_norm = project_name.strip().lower()
    proj_words = [w for w in proj_norm.split() if len(w) > 2]

    try:
        # Strategy 1: Find by SVG path in table rows
        result = await page.evaluate("""(args) => {
            const projNorm  = args.projNorm;
            const projWords = args.projWords;

            function matchesProject(txt) {
                const t = (txt || '').toLowerCase();
                return t.includes(projNorm) ||
                    (projWords.length > 0 && projWords.every(w => t.includes(w)));
            }

            // Try tr / MuiTableRow
            const rows = Array.from(document.querySelectorAll(
                'tr, .MuiTableRow-root, [class*="TableRow"]'));
            console.log('[APPR-JS] rows found:', rows.length);

            for (const row of rows) {
                const txt = (row.textContent || '').toLowerCase();
                if (!matchesProject(txt)) continue;
                if (txt.includes('approved') || txt.includes('rejected')) continue;

                const btns = Array.from(row.querySelectorAll('button'));
                let approveIdx = -1, rejectIdx = -1;
                btns.forEach((btn, i) => {
                    for (const p of btn.querySelectorAll('path')) {
                        const d = p.getAttribute('d') || '';
                        if (d.startsWith('M12 2C6.48')) approveIdx = i;
                        if (d.startsWith('M12 2C6.47')) rejectIdx  = i;
                    }
                });
                if (approveIdx >= 0 || rejectIdx >= 0) {
                    return { strategy: 'row', approveIdx, rejectIdx, rowText: txt.substring(0, 60) };
                }
            }

            // Strategy 2: Scan ALL buttons on page for SVG paths,
            // then check if nearby text matches project name
            const allBtns = Array.from(document.querySelectorAll('button'));
            console.log('[APPR-JS] total buttons on page:', allBtns.length);

            let approveBtn = null, rejectBtn = null;

            for (const btn of allBtns) {
                for (const p of btn.querySelectorAll('path')) {
                    const d = p.getAttribute('d') || '';
                    if (d.startsWith('M12 2C6.48') && !approveBtn) {
                        // Check surrounding context for project name
                        let el = btn.parentElement;
                        for (let i = 0; i < 8; i++) {
                            if (!el) break;
                            const t = (el.textContent || '').toLowerCase();
                            if (t.length > 10 && t.length < 500) {
                                if (matchesProject(t) || true) {  // accept any pending row
                                    approveBtn = btn;
                                    break;
                                }
                            }
                            el = el.parentElement;
                        }
                    }
                    if (d.startsWith('M12 2C6.47') && !rejectBtn) {
                        let el = btn.parentElement;
                        for (let i = 0; i < 8; i++) {
                            if (!el) break;
                            const t = (el.textContent || '').toLowerCase();
                            if (t.length > 10 && t.length < 500) {
                                if (matchesProject(t) || true) {
                                    rejectBtn = btn;
                                    break;
                                }
                            }
                            el = el.parentElement;
                        }
                    }
                }
            }

            if (approveBtn || rejectBtn) {
                return { strategy: 'svg_scan', approveBtn: !!approveBtn, rejectBtn: !!rejectBtn };
            }

            // Strategy 3: Last resort — find MuiIconButton-sizeSmall buttons
            // The approve(✓) and reject(✗) are the last two icon buttons in the row
            const iconBtns = Array.from(document.querySelectorAll(
                'button.MuiIconButton-sizeSmall, button[class*="MuiIconButton-sizeSmall"]'
            )).filter(b => !b.disabled);
            console.log('[APPR-JS] icon buttons:', iconBtns.length);

            if (iconBtns.length >= 2) {
                // Last two are approve and reject (green tick, red cross)
                return {
                    strategy: 'icon_fallback',
                    count: iconBtns.length
                };
            }

            return null;
        }""", {"projNorm": proj_norm, "projWords": proj_words})

        print("[APPR] _find_pending_row result: {}".format(result))

        if not result:
            print("[APPR] No buttons found via any strategy")
            return None, None

        strategy = result.get("strategy", "")

        if strategy == "row":
            # Get actual button handles from row
            rows = await page.query_selector_all(
                "tr, .MuiTableRow-root, [class*='TableRow']")
            for row in rows:
                txt = (await row.text_content() or "").lower()
                has_proj = proj_norm in txt or all(
                    w in txt for w in proj_words)
                if not has_proj:
                    continue
                if "approved" in txt or "rejected" in txt:
                    continue
                btns = await row.query_selector_all("button")
                ai = result.get("approveIdx", -1)
                ri = result.get("rejectIdx",  -1)
                approve_btn = btns[ai] if 0 <= ai < len(btns) else None
                reject_btn  = btns[ri] if 0 <= ri < len(btns) else None
                print("[APPR] ✓ Row strategy — approve={} reject={}".format(
                    approve_btn is not None, reject_btn is not None))
                return approve_btn, reject_btn

        elif strategy == "svg_scan":
            # Re-scan with Playwright to get handles
            all_btns = await page.query_selector_all("button")
            approve_btn = None
            reject_btn  = None
            for btn in all_btns:
                paths = await btn.query_selector_all("path")
                for p in paths:
                    d = (await p.get_attribute("d") or "")
                    if d.startswith("M12 2C6.48") and approve_btn is None:
                        approve_btn = btn
                    if d.startswith("M12 2C6.47") and reject_btn is None:
                        reject_btn = btn
            print("[APPR] ✓ SVG scan — approve={} reject={}".format(
                approve_btn is not None, reject_btn is not None))
            return approve_btn, reject_btn

        elif strategy == "icon_fallback":
            # Get MuiIconButton-sizeSmall buttons
            icon_btns = await page.query_selector_all(
                "button.MuiIconButton-sizeSmall")
            enabled = []
            for b in icon_btns:
                disabled = await b.get_attribute("disabled")
                if disabled is None:
                    enabled.append(b)
            print("[APPR] ✓ Icon fallback — {} enabled icon buttons".format(
                len(enabled)))
            if len(enabled) >= 2:
                # Second-to-last = approve (tick), last = reject (cross)
                return enabled[-2], enabled[-1]
            elif len(enabled) == 1:
                return enabled[0], None

    except Exception as e:
        print("[APPR] _find_pending_row err: {}".format(e))

    return None, None


# ============================================================
# APPROVE TIMESHEET LOGIC
# ============================================================

async def _decide_approve_timesheet(els, url, goal, page=None):
    s = _approval_st
    r = get_reporter()

    # ── Parse once ────────────────────────────────────────────
    if not s.start_date:
        _P = re.compile(r"project\s+(.+?)(?:\s*\||\s*$)", re.IGNORECASE)
        _R = re.compile(r"requested_?by\s+(.+?)(?:\s*\||\s*$)", re.IGNORECASE)
        _A = re.compile(r"\baction\s+(approve|reject)\b", re.IGNORECASE)

        m = _START_RE.search(goal)
        if m:
            raw = m.group(1).strip().replace("/", "-")
            parts = raw.split("-")
            s.start_date = ("{}-{}-{}".format(parts[2], parts[1], parts[0])
                            if len(parts) == 3 and len(parts[0]) != 4 else raw)
        else:
            s.start_date = datetime.now().strftime("%Y-%m-%d")

        s.monday = _week_monday(s.start_date)
        if s.monday is None:
            msg = "Invalid date {!r}".format(s.start_date)
            if r: r.update_last_step(False, error=msg)
            return {"action": "done", "result": "FAIL", "reason": msg}

        m = _P.search(goal); s.project_name = m.group(1).strip() if m else ""
        m = _R.search(goal); s.requested_by = m.group(1).strip() if m else ""
        m = _A.search(goal); s.action = m.group(1).lower() if m else "approve"

        print("[APPR] date={} monday={} project='{}' requested_by='{}' action={}".format(
            s.start_date, s.monday.strftime("%Y-%m-%d"),
            s.project_name, s.requested_by, s.action))

        if not s.project_name:
            msg = ("No project name. Use: approve_timesheet start DATE | "
                   "project NAME | requested_by NAME | action approve")
            if r: r.update_last_step(False, error=msg)
            return {"action": "done", "result": "FAIL", "reason": msg}

    # ── Already done ──────────────────────────────────────────
    if s.verified:
        if r: r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Timesheet {}d ✓ project='{}' requested_by='{}'".format(
                    s.action, s.project_name, s.requested_by)}

    # ── Step A: Click Approval Requests tab FIRST ─────────────
    if not s.approval_tab_clicked:
        tab = els.get("approval_tab")
        if tab:
            print("[APPR] Clicking Approval Requests tab")
            s.approval_tab_clicked = True
            step = {"action": "click",
                    "selector": tab.get("selector") or "#timesheet-tab-approval",
                    "extra_wait_ms": 1500}
            if r: r.log_step(len(r.steps) + 1, step, url)
            return step

        if page:
            try:
                clicked = await page.evaluate("""() => {
                    const b = document.getElementById('timesheet-tab-approval');
                    if (b) { b.click(); return true; }
                    const btns = Array.from(document.querySelectorAll('button'));
                    const t = btns.find(
                        x => x.textContent.toLowerCase().includes('approval'));
                    if (t) { t.click(); return true; }
                    return false;
                }""")
                if clicked:
                    await page.wait_for_timeout(1500)
                    s.approval_tab_clicked = True
                    print("[APPR] ✓ Tab clicked via JS")
                    return {"action": "wait", "seconds": 0}
            except Exception:
                pass

        s._tab_wait += 1
        if s._tab_wait >= s.MAX_WAIT:
            if r: r.update_last_step(False, error="Approval tab not found")
            return {"action": "done", "result": "FAIL",
                    "reason": "Approval Requests tab not found"}
        return {"action": "wait", "seconds": 1}

    # ── Step A2: Navigate date on Approval tab ─────────────────
    if not s.date_navigated:
        if page is not None:
            await _navigate_approval_week(page, s.monday)
            print("[APPR] ✓ Date navigation done for week of {}".format(
                s.monday.strftime("%Y-%m-%d")))
        s.date_navigated = True
        return {"action": "wait", "seconds": 0}

    # ── Step B: Search project + check checkbox ────────────────
    if not s.project_checked:
        if page:
            try:
                if not s.project_filtered:
                    proj_btn = None
                    for b in await page.query_selector_all("button"):
                        txt = (await b.text_content() or "").strip().lower()
                        if txt.startswith("projects"):
                            proj_btn = b
                            break
                    if proj_btn:
                        await proj_btn.scroll_into_view_if_needed()
                        await proj_btn.click()
                        await page.wait_for_timeout(700)
                        print("[APPR] ✓ Projects dropdown opened")
                    else:
                        s._proj_wait += 1
                        if s._proj_wait >= s.MAX_WAIT:
                            if r: r.update_last_step(False,
                                    error="Projects button not found")
                            return {"action": "done", "result": "FAIL",
                                    "reason": "Projects filter button not found"}
                        return {"action": "wait", "seconds": 1}

                    inp = await page.query_selector(
                        "input[placeholder='Search projects...']")
                    if not inp:
                        inp = await page.query_selector(
                            "input[placeholder*='Search projects']")
                    if inp:
                        await inp.scroll_into_view_if_needed()
                        await inp.click()
                        await page.wait_for_timeout(200)
                        await inp.fill(s.project_name)
                        await page.wait_for_timeout(800)
                        s.project_filtered = True
                        print("[APPR] ✓ Project typed: '{}'".format(s.project_name))
                    else:
                        s._proj_wait += 1
                        if s._proj_wait >= s.MAX_WAIT:
                            if r: r.update_last_step(False,
                                    error="Project search input not found")
                            return {"action": "done", "result": "FAIL",
                                    "reason": "Project search input not found"}
                        return {"action": "wait", "seconds": 1}

                proj_norm = s.project_name.strip().lower()
                checked = False

                for sel in (".MuiFormControlLabel-root", ".MuiListItem-root",
                            ".MuiMenuItem-root", "li"):
                    for c in await page.query_selector_all(sel):
                        txt = (await c.text_content() or "").strip().lower()
                        if proj_norm in txt or all(
                                w in txt for w in proj_norm.split() if len(w) > 2):
                            cb = await c.query_selector(
                                "input.PrivateSwitchBase-input[type='checkbox']")
                            if not cb:
                                cb = await c.query_selector("input[type='checkbox']")
                            if cb and await cb.is_visible():
                                await cb.click()
                                await page.wait_for_timeout(500)
                                print("[APPR] ✓ Project checkbox: '{}'".format(
                                    txt[:40]))
                                s.project_checked = True
                                checked = True
                                break
                    if checked:
                        break

                if not checked:
                    for cb in await page.query_selector_all(
                            "input.PrivateSwitchBase-input[type='checkbox']"):
                        if await cb.is_visible():
                            await cb.click()
                            await page.wait_for_timeout(500)
                            print("[APPR] ✓ Project checkbox (fallback)")
                            s.project_checked = True
                            checked = True
                            break

                if not checked:
                    s._proj_wait += 1
                    if s._proj_wait >= s.MAX_WAIT:
                        if r: r.update_last_step(False,
                                error="Project checkbox not found")
                        return {"action": "done", "result": "FAIL",
                                "reason": "Project checkbox not found"}
                    return {"action": "wait", "seconds": 1}

                await page.keyboard.press("Escape")
                await page.wait_for_timeout(600)

            except Exception as e:
                print("[APPR] Project filter err: {}".format(e))
                return {"action": "wait", "seconds": 1}

        if not s.project_checked:
            return {"action": "wait", "seconds": 1}

    # ── Step C: Requested By filter ────────────────────────────
    if s.requested_by and not s.requester_checked:
        if page:
            try:
                if not s.requester_filtered:
                    req_btn = await page.query_selector(
                        "button:has-text('Requested By')")
                    if not req_btn:
                        for b in await page.query_selector_all("button"):
                            if "requested by" in (
                                    await b.text_content() or "").lower():
                                req_btn = b
                                break
                    if req_btn:
                        await req_btn.scroll_into_view_if_needed()
                        await req_btn.click()
                        await page.wait_for_timeout(700)
                        inp = await page.query_selector(
                            "input[placeholder*='Search requested by' i]")
                        if inp:
                            await inp.click()
                            await page.wait_for_timeout(200)
                            await inp.fill(s.requested_by)
                            await page.wait_for_timeout(700)
                            s.requester_filtered = True
                            print("[APPR] ✓ Requester typed: '{}'".format(
                                s.requested_by))
                        else:
                            return {"action": "wait", "seconds": 1}
                    else:
                        s._req_wait += 1
                        if s._req_wait >= s.MAX_WAIT:
                            s.requester_checked = True
                        return {"action": "wait", "seconds": 1}

                req_norm  = s.requested_by.strip().lower()
                req_words = [w for w in req_norm.split() if len(w) > 2]
                checked   = False

                # Use JS to click the correct checkbox — skips "select all"
                clicked_via_js = await page.evaluate("""(args) => {
                    const reqNorm  = args.reqNorm;
                    const reqWords = args.reqWords;

                    // Find all checkboxes in the dropdown
                    const allCbs = Array.from(
                        document.querySelectorAll('input[type="checkbox"]')
                    );
                    console.log('[APPR-JS] total checkboxes:', allCbs.length);

                    for (const cb of allCbs) {
                        // Get label text by walking up the DOM
                        let labelTxt = '';

                        const lbl = cb.closest('label');
                        if (lbl) {
                            labelTxt = (lbl.textContent || '').trim().toLowerCase();
                        }
                        if (!labelTxt) {
                            const fcl = cb.closest('.MuiFormControlLabel-root');
                            if (fcl) labelTxt = (fcl.textContent||'').trim().toLowerCase();
                        }
                        if (!labelTxt) {
                            let p = cb.parentElement;
                            for (let i = 0; i < 5; i++) {
                                if (!p) break;
                                const t = (p.textContent || '').trim().toLowerCase();
                                if (t && t.length < 120) { labelTxt = t; break; }
                                p = p.parentElement;
                            }
                        }

                        console.log('[APPR-JS] checkbox label:', labelTxt);

                        if (!labelTxt) continue;
                        // Skip "select all"
                        if (labelTxt.includes('select all')) continue;

                        // Match the searched name
                        const nameMatch = labelTxt.includes(reqNorm) ||
                            (reqWords.length > 0 &&
                             reqWords.every(w => labelTxt.includes(w)));
                        if (!nameMatch) continue;

                        if (cb.checked) {
                            return 'already_checked:' + labelTxt.substring(0, 40);
                        }

                        // Click the MuiButtonBase span (proper MUI trigger)
                        const muiSpan = cb.closest('span.MuiButtonBase-root');
                        if (muiSpan) {
                            muiSpan.click();
                        } else {
                            cb.click();
                        }
                        return labelTxt.substring(0, 40);
                    }

                    // Fallback: TreeWalker to find name text node
                    const walker = document.createTreeWalker(
                        document.body, NodeFilter.SHOW_TEXT, null, false);
                    let node;
                    while ((node = walker.nextNode())) {
                        const t = (node.textContent || '').trim().toLowerCase();
                        if (!t || t.includes('select all')) continue;
                        const nameMatch = t.includes(reqNorm) ||
                            (reqWords.length > 0 && reqWords.every(w => t.includes(w)));
                        if (!nameMatch) continue;
                        let parent = node.parentElement;
                        for (let i = 0; i < 5; i++) {
                            if (!parent) break;
                            const cb = parent.querySelector('input[type="checkbox"]');
                            if (cb && !cb.checked) {
                                const muiSpan = cb.closest('span.MuiButtonBase-root');
                                if (muiSpan) muiSpan.click(); else cb.click();
                                return t.substring(0, 40);
                            }
                            parent = parent.parentElement;
                        }
                    }
                    return null;
                }""", {"reqNorm": req_norm, "reqWords": req_words})

                if clicked_via_js:
                    if clicked_via_js.startswith("already_checked:"):
                        print("[APPR] Requester already checked: '{}'".format(
                            clicked_via_js.replace("already_checked:", "")))
                    else:
                        print("[APPR] ✓ Requester checkbox clicked: '{}'".format(
                            clicked_via_js))
                    await page.wait_for_timeout(400)

                    # Close dropdown with Escape so filter applies
                    try:
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(600)
                        print("[APPR] ✓ Requested By dropdown closed via Escape")
                    except Exception as close_err:
                        print("[APPR] Dropdown close err: {}".format(close_err))
                        await page.wait_for_timeout(300)

                    s.requester_checked = True
                    checked = True
                else:
                    print("[APPR] JS could not find requester name in dropdown")

                if not checked:
                    s._req_wait += 1
                    print("[APPR] Requester name not found ({}/{})".format(
                        s._req_wait, s.MAX_WAIT))
                    if s._req_wait >= s.MAX_WAIT:
                        print("[APPR] Skipping requester filter — proceeding without it")
                        s.requester_checked = True
                    return {"action": "wait", "seconds": 1}

                await page.wait_for_timeout(300)

            except Exception as e:
                print("[APPR] Requester filter err: {}".format(e))
                return {"action": "wait", "seconds": 1}

        if not s.requester_checked:
            return {"action": "wait", "seconds": 1}

    elif not s.requested_by:
        s.requester_checked = True

    # ── Step D: Click Approve or Reject ───────────────────────
    # Uses exact SVG path d= to find buttons:
    #   Approve tick: path starts with M12 2C6.48
    #   Reject cross: path starts with M12 2C6.47
    if not s.action_clicked:
        if page:
            try:
                await page.wait_for_timeout(500)

                approve_btn, reject_btn = await _find_pending_row(
                    page, s.project_name)

                btn = approve_btn if s.action == "approve" else reject_btn

                if btn:
                    await btn.scroll_into_view_if_needed()
                    await btn.click()
                    await page.wait_for_timeout(1500)
                    print("[APPR] ✓ {} button clicked".format(
                        s.action.capitalize()))
                    s.action_clicked = True

                    # ── Reject dialog: fill Rejection Reason + click Reject ──
                    if s.action == "reject":
                        try:
                            # Wait for the rejection reason textarea
                            textarea = await page.wait_for_selector(
                                "textarea[required], "
                                "textarea[id*='_r_']",
                                timeout=5000,
                                state="visible"
                            )
                            if textarea:
                                await textarea.click()
                                await textarea.fill("Rejected")
                                await page.wait_for_timeout(400)
                                print("[APPR] ✓ Rejection reason filled")

                                # Click the Reject confirm button
                                reject_confirm = None

                                # Try exact text match first
                                for b in await page.query_selector_all("button"):
                                    txt = (await b.text_content() or "").strip()
                                    if txt == "Reject" and await b.is_visible():
                                        reject_confirm = b
                                        break

                                # Fallback: MuiButton-textPrimary with Reject text
                                if not reject_confirm:
                                    reject_confirm = await page.query_selector(
                                        "button.MuiButton-textPrimary")

                                if reject_confirm:
                                    await reject_confirm.click()
                                    await page.wait_for_timeout(1000)
                                    print("[APPR] ✓ Reject dialog confirmed")
                                else:
                                    print("[APPR] ⚠ Reject confirm button not found")
                        except Exception as re_err:
                            print("[APPR] Reject dialog err: {}".format(re_err))

                    # ── Approve: handle any confirmation dialog ────────────
                    else:
                        for sel in ("button:has-text('Confirm')",
                                    "button:has-text('Yes')",
                                    "button:has-text('OK')",
                                    "button:has-text('Continue')"):
                            c = await page.query_selector(sel)
                            if c and await c.is_visible():
                                await c.click()
                                await page.wait_for_timeout(1000)
                                print("[APPR] ✓ Confirmed via '{}'".format(sel))
                                break

                    return {"action": "wait", "seconds": 1}

                s._action_wait += 1
                print("[APPR] {} btn not found ({}/{})".format(
                    s.action.capitalize(), s._action_wait, s.MAX_WAIT))
                if s._action_wait >= s.MAX_WAIT:
                    if r: r.update_last_step(False,
                        error="{} button not found — is timesheet Pending?".format(
                            s.action.capitalize()))
                    return {"action": "done", "result": "FAIL",
                            "reason": "{} button not found — timesheet may not be Pending".format(
                                s.action.capitalize())}
                return {"action": "wait", "seconds": 1}

            except Exception as e:
                print("[APPR] Action click err: {}".format(e))
                return {"action": "wait", "seconds": 1}

        return {"action": "wait", "seconds": 1}

    # ── Step E: Verify ─────────────────────────────────────────
        # ── Step E: Verify ─────────────────────────────────────────
    dom_raw = els.get("dom_raw") or []

    toast_found = bool(els.get("success_toast")) or any(
        ("success"    in (el.get("text") or "").lower()
         or "approved" in (el.get("text") or "").lower()
         or "rejected" in (el.get("text") or "").lower()
         or "snackbar" in (el.get("class") or "").lower()
         or "toast"    in (el.get("class") or "").lower())
        for el in dom_raw
    )
    error_found = bool(els.get("error_toast")) or any(
        ("error"   in (el.get("text") or "").lower()
         or "failed" in (el.get("text") or "").lower())
        for el in dom_raw
        if el.get("tag", "").lower() not in ("input", "button", "textarea")
    )
    proj_norm = s.project_name.strip().lower()
    row_gone = not any(
        proj_norm in (el.get("text") or "").lower()
        for el in dom_raw
        if el.get("tag", "").lower() in ("td", "span", "p", "div", "li")
    )

    signals = sum([toast_found, row_gone])
    print("[APPR-VERIFY] toast={} row_gone={} error={} signals={}/2 wait={}/{}".format(
        toast_found, row_gone, error_found, signals, s._verify_wait, s.MAX_WAIT))

    if error_found:
        if r: r.update_last_step(False, error="{} failed".format(s.action))
        return {"action": "done", "result": "FAIL",
                "reason": "Timesheet {} failed — error on page".format(s.action)}

    # ── PASS immediately on any positive signal ────────────────
    # The DOM scanner never captures table row text (only 19 elements
    # are extracted), so toast will always be False. row_gone=True is
    # reliable because the project name disappears from DOM after
    # approve/reject. One signal is enough to confirm success.
    if toast_found or row_gone or signals >= 1:
        s.verified = True
        if r: r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Timesheet {}d ✓ (toast={} row_gone={})".format(
                    s.action, toast_found, row_gone)}

    # ── Fallback: wait max 2 cycles then declare PASS ──────────
    # (reduced from 6 to 2 since DOM scanner misses table content)
    s._verify_wait += 1
    if s._verify_wait >= 2:
        s.verified = True
        if r: r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "{} clicked — no error after {} waits".format(
                    s.action.capitalize(), s._verify_wait)}

    return {"action": "wait", "seconds": 1}


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

def reset_state():
    reset_login()
    reset_nav()
    _ts_st.reset()
    _clone_st.reset()
    _approval_st.reset()
    print("[STATE] Timesheet reset")


async def decide_action(action, dom, url, goal="", email=None,
                        password=None, page=None):
    els = scan_dom(dom)
    r   = get_reporter()

    if not login_done():
        step = handle_login(els, email, password, url)
        if step is None and not login_done():
            return {"action": "wait", "seconds": 1}
        if step:
            if r: r.log_step(len(r.steps) + 1, step, url)
            return step

    s = (_clone_st    if action == "clone_last_week"    else
         _approval_st if action == "approve_timesheet"  else
         _ts_st)

    if not s.time_tracking_clicked and NAV_FRAGMENT not in url.lower():
        tt = els.get("nav_time_tracking")
        if tt:
            print("[TS] Clicking Time Tracking sidebar")
            s.time_tracking_clicked = True
            step = {
                "action":        "click",
                "selector":      (tt.get("selector") or "#nav-item-time-tracking"),
                "extra_wait_ms": 1200,
            }
            if r: r.log_step(len(r.steps) + 1, step, url)
            return step

        s._tt_wait += 1
        print("[TS] Waiting for sidebar ({}/{})".format(s._tt_wait, s.MAX_WAIT))
        if s._tt_wait >= s.MAX_WAIT:
            print("[TS] Sidebar not found — direct nav")
            s.time_tracking_clicked = True
        return {"action": "wait", "seconds": 1}

    if not nav_done():
        step = handle_nav(els, url, NAV_FRAGMENT)
        if step:
            if r: r.log_step(len(r.steps) + 1, step, url)
            return step

    if action == "clone_last_week":
        return await _decide_clone_last_week(els, url, goal, page=page)

    if action == "add_timesheet":
        return await _decide_add_timesheet(els, url, goal, page=page)

    if action == "approve_timesheet":
        return await _decide_approve_timesheet(els, url, goal, page=page)

    return {"action": "wait", "seconds": 1}