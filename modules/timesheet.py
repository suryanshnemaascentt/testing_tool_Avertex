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
        "nav_timesheets":     None,
        "nav_time_tracking":  None,
        "prev_week_btn":      None,
        "next_week_btn":      None,
        "week_label":         None,
        "add_row_btn":        None,
        "select_project_btn": None,
        "submit_btn":         None,
        "success_toast":      None,
        "dom_raw":            dom,
    })

    _SUCCESS = ("submitted successfully", "timesheet submitted",
                "saved successfully", "success")

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

        if eid == "timesheet-submit-button" and not result["submit_btn"]:
            result["submit_btn"] = el
        elif not result["submit_btn"] and tag == "button" \
                and "submit timesheet" in comb:
            result["submit_btn"] = el

        if tag not in ("input", "button", "textarea"):
            if any(p in comb for p in _SUCCESS) and not result["success_toast"]:
                result["success_toast"] = el

    return result


# ============================================================
# STATE
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
        self.MAX_WAIT              = 5

    def reset(self):
        self.__init__()


_ts_st = _TimesheetState()


# ============================================================
# WEEK NAVIGATION HELPER
# ============================================================

async def _navigate_to_week(page, target_monday):
    """
    Navigate the timesheet calendar to the week containing target_monday.
    Uses #timesheet-week-nav div buttons directly via JS.
    Returns when correct week is shown or gives up after MAX_NAV clicks.
    """
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

    MAX_NAV = 26
    for _ in range(MAX_NAV):
        label = await _get_label()
        print("[TS-NAV] Label: '{}'  Target: {}".format(
            label, target_monday.strftime("%Y-%m-%d")))

        if not label:
            print("[TS-NAV] ⚠ No label found — proceeding anyway")
            return

        if _week_label_matches(label, target_monday):
            print("[TS-NAV] ✓ Correct week reached")
            return

        # Determine direction
        parts = re.findall(r"([a-z]{3})\s+(\d+)", label.lower())
        direction = "next"
        if parts:
            try:
                mn, ds = parts[0]
                cur = datetime(target_monday.year, months[mn], int(ds))
                direction = "next" if target_monday > cur else "prev"
            except Exception:
                direction = "next"

        print("[TS-NAV] → {}".format(direction))
        ok = await _click_nav(direction)
        if not ok:
            print("[TS-NAV] ⚠ Nav click failed — proceeding anyway")
            return

    print("[TS-NAV] ⚠ Max navigations reached — proceeding anyway")


# ============================================================
# MAIN DECIDE
# ============================================================

async def _decide_add_timesheet(els, url, goal, page=None):
    s = _ts_st
    r = get_reporter()

    # ── Parse goal once ───────────────────────────────────────
    if not s.start_date:
        s.start_date, s.rows = _parse_goal(goal)

        if not s.start_date:
            msg = "No start date. Use: add_timesheet start YYYY-MM-DD | project X | job Y"
            print("[TS] ERROR: " + msg)
            if r: r.update_last_step(False, error=msg)
            return {"action": "done", "result": "FAIL", "reason": msg}

        if not s.rows:
            msg = "No project/job rows found."
            print("[TS] ERROR: " + msg)
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

        # ── Navigate to correct week immediately after parsing ─
        # Do this HERE, before anything else, while page is idle.
        if page is not None:
            print("[TS] Navigating to target week before filling rows...")
            await _navigate_to_week(page, s.monday)
            s.date_navigated = True
        else:
            print("[TS-NAV] ⚠ No page object at parse time — will nav later")

    if s.verified:
        if r: r.update_last_step(True)
        return {"action": "done", "result": "PASS",
                "reason": "Timesheet submitted for week of {}".format(
                    s.monday.strftime("%b %d, %Y"))}

    # ── Verify after submit ───────────────────────────────────
    if s.submitted:
        dom_raw = els.get("dom_raw") or []

        # FIRST: check if Submit dialog open — click Continue
        continue_btn = next(
            (el for el in dom_raw
             if (el.get("text") or "").strip() == "Continue"
             and el.get("tag") == "button"),
            None
        )
        if continue_btn:
            print("[TS] Submit dialog → clicking Continue")
            step = {"action": "click",
                    "selector": "button:has-text('Continue')",
                    "extra_wait_ms": 2000}
            if r: r.log_step(len(r.steps) + 1, step, url)
            return step

        toast_found = bool(els.get("success_toast")) or any(
            ("submitted" in (el.get("text") or "").lower()
             or "success"  in (el.get("text") or "").lower()
             or "snackbar" in (el.get("class") or "").lower()
             or "toast"    in (el.get("class") or "").lower())
            for el in dom_raw
        )
        sb = els.get("submit_btn")
        submit_gone = sb is None or (
            "disabled" in (sb.get("class") or "").lower() and s._submit_wait > 0)
        url_changed = "my-timesheets" in url.lower()
        signals = sum([toast_found, submit_gone, url_changed])
        print("[TS-VERIFY] toast={} gone={} url={} signals={}/3".format(
            toast_found, submit_gone, url_changed, signals))

        # submit_gone alone = confirmed submitted
        if toast_found or submit_gone or signals >= 1:
            s.verified = True
            if r: r.update_last_step(True)
            return {"action": "done", "result": "PASS",
                    "reason": "Submitted (signals={}/3)".format(signals)}

        s._submit_wait += 1
        if s._submit_wait >= s.MAX_WAIT:
            if r: r.update_last_step(False, error="Submit unconfirmed")
            return {"action": "done", "result": "FAIL",
                    "reason": "Submit unconfirmed"}
        return {"action": "wait", "seconds": 1}

    # ── Submit when all rows done ─────────────────────────────
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
                print("[TS] Submit dialog open → clicking Continue")
                s.submitted = True
                step = {"action": "click",
                        "selector": "button:has-text('Continue')",
                        "extra_wait_ms": 2000}
                if r: r.log_step(len(r.steps) + 1, step, url)
                return step

            print("[TS] Clicking Submit Timesheet")
            s.submitted = True
            step = {"action": "click", "selector": "#timesheet-submit-button",
                    "extra_wait_ms": 2000}
            if r: r.log_step(len(r.steps) + 1, step, url)
            return step

        s._submit_wait += 1
        print("[TS] Submit disabled ({}/{})".format(s._submit_wait, s.MAX_WAIT))
        if s._submit_wait >= s.MAX_WAIT:
            if r: r.update_last_step(False, error="Submit stayed disabled")
            return {"action": "done", "result": "FAIL",
                    "reason": "Submit button remained disabled"}
        return {"action": "wait", "seconds": 1}

    # ── Navigate if not done yet (fallback) ──────────────────
    if not s.date_navigated and page is not None:
        print("[TS] Late nav — navigating now...")
        await _navigate_to_week(page, s.monday)
        s.date_navigated = True
        return {"action": "wait", "seconds": 0}

    # ── Fill rows ─────────────────────────────────────────────
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
                print("[TS] Row {}: clicking Add Row".format(idx))
                s.row_states[idx] = "ready"
                step = {"action": "click", "selector": ab["selector"],
                        "extra_wait_ms": 700}
                if r: r.log_step(len(r.steps) + 1, step, url)
                return step

            s._row_wait += 1
            if s._row_wait >= s.MAX_WAIT:
                if r: r.update_last_step(False,
                    error="Add Row not found row {}".format(idx))
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
            print("[TS] Row {}: project='{}' job='{}' week={}…{}".format(
                idx, row["project"], row["job"],
                week_dates["mon"], week_dates["fri"]))

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
# PUBLIC ENTRY POINT
# ============================================================

def reset_state():
    reset_login()
    reset_nav()
    _ts_st.reset()
    print("[STATE] Timesheet reset")


async def decide_action(action, dom, url, goal="", email=None,
                        password=None, page=None):
    els = scan_dom(dom)
    s   = _ts_st
    r   = get_reporter()

    if not login_done():
        step = handle_login(els, email, password, url)
        if step is None and not login_done():
            return {"action": "wait", "seconds": 1}
        if step:
            if r: r.log_step(len(r.steps) + 1, step, url)
            return step

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

    if action == "add_timesheet":
        return await _decide_add_timesheet(els, url, goal, page=page)

    return {"action": "wait", "seconds": 1}