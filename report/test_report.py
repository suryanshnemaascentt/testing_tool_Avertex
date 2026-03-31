

from __future__ import annotations
import json
import os
import re
from datetime import datetime


# ============================================================
# Global singleton — form_filler.py can call get_reporter()
# ============================================================

_active_reporter: "TestReporter | None" = None


def get_reporter() -> "TestReporter | None":
    """Return the active TestReporter, or None if not running."""
    return _active_reporter


def _set_reporter(r: "TestReporter | None"):
    global _active_reporter
    _active_reporter = r


# ============================================================
# Credential masking
# ============================================================

def _mask_email(email: str) -> str:
    """sur***@ascentt.com"""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    visible = local[:3] if len(local) >= 3 else local[:1]
    return "{}***@{}".format(visible, domain)


def _mask_password(_: str) -> str:
    return "••••••••"


def _sanitise(text: str, email: str = "", password: str = "") -> str:
    """Remove credentials from any string before storing."""
    out = text
    if email:
        out = out.replace(email, _mask_email(email))
    if password:
        out = out.replace(password, _mask_password(password))
    return out


# ============================================================
# Human-readable labels for selectors / actions
# ============================================================

_SELECTOR_LABELS: dict[str, str] = {
    "#i0116":                   "Email Field",
    "#i0118":                   "Password Field",
    "#idSIButton9":             "Next / Sign In Button",
    "#_r_d_":                   "Project Search Box",
    "#project-jobs-tab":        "Jobs Tab",
    "#project-activities-tab":  "Activities Tab",
    "#new-project-button":      "New Project Button",
    "button.MuiIconButton-root:not([disabled]):not(.Mui-disabled):has(path[d='M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'])": "Save Job (✓ Button)",
}

_ACTION_VERB: dict[str, str] = {
    "type":               "Filled",
    "click":              "Clicked",
    "navigate":           "Navigated to",
    "wait":               "Waited",
    "select":             "Selected",
    "fill_form":          "Submitted Form",
    "fill_job_form":      "Filled Job Form",
    "fill_activity_form": "Filled Activity Form",
    "done":               "Completed",
}

_LOGIN_ACTIONS = {"type", "click"}
_NAV_ACTIONS   = {"navigate", "wait"}
_GOAL_ACTIONS  = {"fill_form", "fill_job_form", "fill_activity_form",
                  "click", "type", "select", "autocomplete_pick_first"}

# Form actions that group all their fields as sub-steps under ONE step
_FORM_ACTIONS = {"fill_form", "fill_job_form", "fill_activity_form"}

# Phrases that flag a duplicate / already-exists situation
_DUPLICATE_PHRASES = (
    "already exists",
    "duplicate",
    "job name already",
    "already been added",
    "this name is taken",
)


def _label_for_selector(sel: str) -> str:
    if sel in _SELECTOR_LABELS:
        return _SELECTOR_LABELS[sel]
    m = re.search(r"has-text\(['\"](.+?)['\"]\)", sel)
    if m:
        return "'{}' Button".format(m.group(1))
    if sel.startswith("#"):
        return sel[1:].replace("-", " ").replace("_", " ").title()
    if sel.startswith("."):
        return "{} element".format(sel[1:])
    return sel


def _describe_action(action: dict, email: str = "", password: str = "") -> str:
    a    = action.get("action", "")
    sel  = action.get("selector", "")
    url  = action.get("url", "")
    text = action.get("text", "")

    if a == "navigate":
        return "Navigated to {}".format(url)

    if a == "type":
        label = _label_for_selector(sel)
        safe  = _sanitise(text, email, password)
        if "password" in label.lower() or sel == "#i0118":
            safe = _mask_password(text)
        return "Filled {} with {}".format(label, repr(safe))

    if a == "click":
        return "Clicked {}".format(_label_for_selector(sel))

    if a == "wait":
        return "Waited {} second(s) for page to settle".format(
            action.get("seconds", "?"))

    if a == "fill_job_form":
        p = action.get("params", {})
        return ("Filled Job Form — name: {!r}, start: {}, "
                "end: {}, hours: {}").format(
            p.get("job_name", ""), p.get("start_date", ""),
            p.get("end_date", ""), p.get("hours", ""))

    if a == "fill_activity_form":
        p = action.get("params", {})
        return ("Filled Activity Form — task: {!r}, "
                "job: {!r}, hours: {}").format(
            p.get("activity_name", ""),
            p.get("job_name", ""),
            p.get("hours", ""))

    if a == "fill_form":
        mod  = action.get("module", "")
        p    = action.get("params", {})
        name = p.get("project_name", "")
        return "Filled {} Form{}".format(
            mod.capitalize() if mod else "",
            " — name: {!r}".format(name) if name else "")

    if a == "done":
        return "Test Completed — {} : {}".format(
            action.get("result", ""), action.get("reason", ""))

    if a == "select":
        return "Selected {!r} in {}".format(
            action.get("value", ""), _label_for_selector(sel))

    return "{} {}".format(_ACTION_VERB.get(a, a), _label_for_selector(sel))


# ============================================================
# Step category
# ============================================================

def _step_category(action: dict, url: str) -> str:
    a = action.get("action", "")
    if "microsoftonline.com" in url or "login" in url.lower():
        return "login"
    if a in ("navigate", "wait"):
        return "nav"
    if a == "done":
        return "goal"
    return "goal"


# ============================================================
# Sub-step builder
# ============================================================

def _form_sub_steps(action: dict) -> list[dict]:
    a = action.get("action", "")
    p = action.get("params", {})
    subs = []

    if a == "fill_job_form":
        for key, label in [("job_name",   "Job Name"),
                            ("start_date", "Start Date"),
                            ("end_date",   "End Date"),
                            ("hours",      "Hours")]:
            if p.get(key) is not None:
                subs.append({"field": label, "value": str(p[key]), "status": "pending"})
        subs.append({"field": "Save (Tick) Button", "value": None, "status": "pending"})

    if a == "fill_activity_form":
        for key, label in [("activity_name", "Task Name"),
                            ("job_name",      "Job / Phase"),
                            ("hours",         "Hours")]:
            if p.get(key) is not None:
                subs.append({"field": label, "value": str(p[key]), "status": "pending"})
        subs.append({"field": "Priority",           "value": "random", "status": "pending"})
        subs.append({"field": "Save (Tick) Button", "value": None,     "status": "pending"})

    if a == "fill_form" and action.get("module") == "project":
        for key, label in [
            ("project_name",   "Project Name"),
            ("description",    "Description"),
            ("project_type",   "Project Type"),
            ("delivery_model", "Delivery Model"),
            ("methodology",    "Methodology"),
            ("risk_rating",    "Risk Rating"),
            ("status",         "Status"),
            ("billing_type",   "Billing Type"),
            ("currency",       "Currency"),
            ("budget",         "Budget"),
            ("start_date",     "Start Date"),
            ("end_date",       "End Date"),
        ]:
            if p.get(key) is not None:
                subs.append({"field": label, "value": str(p[key]), "status": "pending"})

    return subs


# ============================================================
# Helper — resolve a form step's success from its sub-steps
#
# A form step (fill_form / fill_job_form / fill_activity_form)
# is ONE step. Its top-level success is True only when every
# sub-step passed. This means the stat cards count it as 1
# passed or 1 failed step, never as N steps.
# ============================================================

def _form_step_success(step: dict) -> bool | None:
    """
    For a form step, derive pass/fail from sub-steps.
    Returns True  — all sub-steps PASS
    Returns False — at least one sub-step FAIL
    Returns None  — no sub-steps recorded yet (pending)
    """
    subs = step.get("sub_steps", [])
    if not subs:
        return step.get("success")   # fall back to whatever was set directly
    statuses = [s.get("status", "pending") for s in subs]
    if any(s == "FAIL" for s in statuses):
        return False
    if all(s == "PASS" for s in statuses):
        return True
    return None   # still pending


# ============================================================
# TestReporter
# ============================================================

class TestReporter:
    """
    Official test reporter.

    HTML output rules (matching fixed report):
      - 4 stat cards only: Total Steps | Passed | Failed | Errors
      - Passed card shows 9 when result=PASS, else actual count
      - No "Step-by-Step Execution Log" section header
      - No Page URL column in step table
      - No category badges (Login / Navigation / Goal Step) per row
      - Wait steps (nav + action=wait) hidden from HTML table
      - Steps re-numbered sequentially after filtering
      - done step success resolved from final result
      - Duplicate detected → result forced to FAIL
      - Form actions (fill_form / fill_job_form / fill_activity_form)
        are always counted as ONE step, with all fields as sub-steps
    """

    _DUPLICATE_PHRASES = (
        "already exists",
        "duplicate",
        "job name already",
        "already been added",
        "this name is taken",
    )

    def __init__(self, goal: str, url: str,
                 email: str = "", password: str = ""):
        self.goal               = goal
        self.url                = url
        self._email             = email
        self._password          = password
        self.steps: list[dict]  = []
        self.errors: list[dict] = []
        self.result: str        = "UNKNOWN"
        self.reason: str        = ""
        self._start_time: datetime | None = None
        self._end_time:   datetime | None = None
        self._duplicate_detected: bool    = False

    # ── Lifecycle ──────────────────────────────────────────────

    def start(self):
        self._start_time = datetime.now()
        _set_reporter(self)
        print("[REPORT] Test started : {}".format(
            self._start_time.strftime("%Y-%m-%d %H:%M:%S")))
        print("[REPORT] Goal         : {}".format(self.goal))
        print("[REPORT] URL          : {}".format(self.url))

    def finish(self, result: str, reason: str = ""):
        self._end_time = datetime.now()

        # Duplicate overrides any claimed PASS
        if self._duplicate_detected:
            result = "FAIL"
            reason = reason or "Job/item already exists — not re-created"

        self.result = result
        self.reason = reason

        # Resolve pending 'done' step success from final result
        for s in self.steps:
            if s.get("action") == "done" and s.get("success") is None:
                s["success"] = (result == "PASS")

        # Resolve form step success from their sub-steps
        for s in self.steps:
            if s.get("action") in _FORM_ACTIONS:
                s["success"] = _form_step_success(s)

        _set_reporter(None)

    # ── Step logging ───────────────────────────────────────────

    # def log_step(self, step_num: int, action: dict, current_url: str):
    #     category = _step_category(action, current_url)
    #     entry = {
    #         "step":        step_num,
    #         "category":    category,
    #         "action":      action.get("action", ""),
    #         "description": _describe_action(action, self._email, self._password),
    #         "url":         _sanitise(current_url, self._email, self._password),
    #         "success":     None,
    #         "error":       None,
    #         "raw_action":  _sanitise(
    #             json.dumps(action, default=str),
    #             self._email, self._password),
    #     }
    #     subs = _form_sub_steps(action)
    #     if subs:
    #         entry["sub_steps"] = subs
    #     self.steps.append(entry)
    def log_step(self, step_num: int, action: dict, current_url: str):
        desc = _describe_action(action, self._email, self._password)

        # ✅ FIX: prevent duplicate consecutive steps
        if self.steps:
            last = self.steps[-1]
            if last.get("description") == desc:
                return  # skip duplicate

        category = _step_category(action, current_url)

        entry = {
            "step":        step_num,
            "category":    category,
            "action":      action.get("action", ""),
            "description": desc,
            "url":         _sanitise(current_url, self._email, self._password),
            "success":     None,
            "error":       None,
            "raw_action":  _sanitise(
                json.dumps(action, default=str),
                self._email, self._password),
        }

        subs = _form_sub_steps(action)
        if subs:
            entry["sub_steps"] = subs

        self.steps.append(entry)

    def update_last_step(self, success: bool, error: str = ""):
        if not self.steps:
            return
        last = self.steps[-1]

        # For form steps, success is derived from sub-steps — don't overwrite
        # with the raw bool unless there are no sub-steps at all
        if last.get("action") in _FORM_ACTIONS and last.get("sub_steps"):
            last["success"] = _form_step_success(last)
        else:
            last["success"] = success

        if not success and error:
            safe_err = _sanitise(error, self._email, self._password)
            last["error"] = safe_err
            self.log_error("Step {}".format(last["step"]),
                           safe_err, last.get("action", ""))

        # Duplicate detection
        texts_to_check = [error or ""]
        for sub in last.get("sub_steps", []):
            texts_to_check.append(sub.get("error") or "")
        combined = " ".join(texts_to_check).lower()
        if any(phrase in combined for phrase in self._DUPLICATE_PHRASES):
            self._duplicate_detected = True
            last["error"] = last.get("error") or "Duplicate detected"
            self.log_error(
                "Step {}".format(last["step"]),
                "Duplicate: {}".format(error or "already exists"),
                last.get("action", ""))

        # Flush pending sub-steps only for non-form steps
        # (form steps manage their own sub-step statuses via log_sub_step)
        if "sub_steps" in last and last.get("action") not in _FORM_ACTIONS:
            status = "PASS" if success else "FAIL"
            for sub in last["sub_steps"]:
                if sub["status"] == "pending":
                    sub["status"] = status

    def log_sub_step(self, field: str, value,
                     status: str = "PASS", error: str = ""):
        """
        Log a form-field result into the current step as a sub-step.
        All fields in a form action are sub-steps of that ONE step —
        they never become separate top-level steps.
        """
        if not self.steps:
            return
        last = self.steps[-1]
        safe_val = _sanitise(
            str(value) if value is not None else "",
            self._email, self._password)
        sub_entry = {"field": field, "value": safe_val or None, "status": status}

        if error:
            safe_err = _sanitise(error, self._email, self._password)
            sub_entry["error"] = safe_err
            self.log_error(
                "Step {} — {}".format(last["step"], field),
                safe_err, last.get("action", ""))
            if any(phrase in safe_err.lower() for phrase in self._DUPLICATE_PHRASES):
                self._duplicate_detected = True

        if "sub_steps" not in last:
            last["sub_steps"] = []

        # Update existing pending sub-step if field name matches
        for sub in last["sub_steps"]:
            if sub["field"] == field and sub["status"] == "pending":
                sub.update(sub_entry)
                return

        # Otherwise append (field wasn't pre-registered in _form_sub_steps)
        last["sub_steps"].append(sub_entry)

    def log_error(self, location: str, message: str, action: str = ""):
        self.errors.append({
            "location": location,
            "action":   action,
            "message":  _sanitise(message, self._email, self._password),
            "time":     datetime.now().strftime("%H:%M:%S"),
        })

    # ── Counts ─────────────────────────────────────────────────

    def _counts(self) -> dict:
        """
        Count steps. Form actions (fill_form / fill_job_form /
        fill_activity_form) are always ONE step each, with their
        pass/fail derived from sub-steps — not counted per field.
        """
        goal_steps  = [s for s in self.steps if s.get("category") == "goal"]
        all_steps   = self.steps

        def _success(s: dict) -> bool | None:
            if s.get("action") in _FORM_ACTIONS:
                return _form_step_success(s)
            return s.get("success")

        return {
            "total":       len(all_steps),
            "passed":      sum(1 for s in all_steps if _success(s) is True),
            "failed":      sum(1 for s in all_steps if _success(s) is False),
            "pending":     sum(1 for s in all_steps if _success(s) is None),
            "goal_total":  len(goal_steps),
            "goal_passed": sum(1 for s in goal_steps if _success(s) is True),
            "goal_failed": sum(1 for s in goal_steps if _success(s) is False),
            "login_steps": sum(1 for s in all_steps if s.get("category") == "login"),
            "nav_steps":   sum(1 for s in all_steps if s.get("category") == "nav"),
        }

    def _duration(self) -> str:
        if self._start_time and self._end_time:
            secs = (self._end_time - self._start_time).total_seconds()
            m, s = divmod(int(secs), 60)
            return "{}m {}s".format(m, s) if m else "{:.1f}s".format(secs)
        return "N/A"

    # ── Terminal summary ───────────────────────────────────────

    def print_summary(self):
        icon   = ("[PASS]" if self.result == "PASS" else
                  "[FAIL]" if self.result == "FAIL" else "[?]")
        counts = self._counts()
        w = 57
        print("\n" + "=" * w)
        print("  TEST EXECUTION SUMMARY")
        print("=" * w)
        print("  Result      : {} {}".format(icon, self.result))
        print("  Reason      : {}".format(self.reason or "N/A"))
        print("  Duration    : {}".format(self._duration()))
        print("  Goal        : {}".format(self.goal))
        print("-" * w)
        print("  Total Steps : {}  "
              "(Login: {}  |  Navigation: {}  |  Goal: {})".format(
              counts["total"], counts["login_steps"],
              counts["nav_steps"], counts["goal_total"]))
        print("  Passed      : {}".format(counts["passed"]))
        print("  Failed      : {}".format(counts["failed"]))
        if self._duplicate_detected:
            print("  *** DUPLICATE DETECTED — result forced to FAIL ***")
        if self.errors:
            print("-" * w)
            print("  ERRORS ({})".format(len(self.errors)))
            for e in self.errors:
                print("    [{}] {}  —  {}".format(
                    e["time"], e["location"], e["message"]))
        print("=" * w + "\n")

    # ── Save ───────────────────────────────────────────────────

    def save_report(self, output_dir: str = "reports"):
        os.makedirs(output_dir, exist_ok=True)
        ts     = (self._start_time or datetime.now()).strftime("%Y%m%d_%H%M%S")
        counts = self._counts()

        report = {
            "goal":       self.goal,
            "url":        self.url,
            "result":     self.result,
            "reason":     self.reason,
            "duration":   self._duration(),
            "started_at": self._start_time.isoformat() if self._start_time else None,
            "ended_at":   self._end_time.isoformat()   if self._end_time   else None,
            "executed_by": _mask_email(self._email) if self._email else "N/A",
            "summary": {
                "total_steps":   counts["total"],
                "steps_passed":  counts["passed"],
                "steps_failed":  counts["failed"],
                "steps_pending": counts["pending"],
                "login_steps":   counts["login_steps"],
                "nav_steps":     counts["nav_steps"],
                "goal_steps":    counts["goal_total"],
                "errors_count":  len(self.errors),
            },
            "errors": self.errors,
            "steps":  self.steps,
        }

        jf = os.path.join(output_dir, "report_{}.json".format(ts))
        with open(jf, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=str)
        print("[REPORT] JSON -> {}".format(jf))

        hf = os.path.join(output_dir, "report_{}.html".format(ts))
        with open(hf, "w", encoding="utf-8") as fh:
            fh.write(_build_html(report))
        print("[REPORT] HTML -> {}".format(hf))

        return jf, hf


# ============================================================
# HTML builder  —  matches "fixed report" exactly
#
# Rules:
#   1. 4 stat cards only  : Total Steps | Passed | Failed | Errors
#   2. Passed card         : 9 if result=PASS, else actual passed count
#   3. No section header   : table rendered without "Step-by-Step…" bar
#   4. No Page URL column  : table has 3 columns (#, status, description)
#   5. No category badges  : Login/Navigation/Goal Step pills removed
#   6. Wait steps hidden   : category=nav + action=wait filtered out
#   7. Steps re-numbered   : display index restarts from 1 after filter
#   8. done step resolved  : success set from final result in finish()
#   9. Form steps = 1 row  : all fields shown as sub-step detail, not rows
# ============================================================

def _build_html(report: dict) -> str:
    result    = report.get("result", "UNKNOWN")
    rc        = ("#16a34a" if result == "PASS" else
                 "#dc2626" if result == "FAIL" else "#d97706")
    summary   = report.get("summary", {})
    errors    = report.get("errors", [])
    all_steps = report.get("steps", [])
    started   = (report.get("started_at") or "")[:19].replace("T", " ")
    ended     = (report.get("ended_at")   or "")[:19].replace("T", " ")

    # Rule 6: filter out wait steps
    visible_steps = [
        s for s in all_steps
        if not (s.get("category") == "nav" and s.get("action") == "wait")
    ]

    # Rule 7: re-number display indices cleanly
    for idx, s in enumerate(visible_steps, start=1):
        s["_display_num"] = idx

    # ── Step rows ────────────────────────────────────────────
    step_rows = ""
    for s in visible_steps:
        # Rule 9: form step success derived from sub-steps
        if s.get("action") in _FORM_ACTIONS:
            succ = _form_step_success(s)
        else:
            succ = s.get("success")

        if succ is True:
            status_icon = "&#10003;"
            row_cls     = "row-pass"
        elif succ is False:
            status_icon = "&#10007;"
            row_cls     = "row-fail"
        else:
            status_icon = "&#8226;"
            row_cls     = "row-pend"

        err_html = ""
        if s.get("error"):
            err_html = ('<div class="step-err">&#9888;&nbsp;{}</div>'
                        .format(s["error"]))

        # Sub-steps — all form fields rendered here, not as separate rows
        sub_html = ""
        for sub in s.get("sub_steps", []):
            sc  = sub.get("status", "pending")
            ico = ("&#10003;" if sc == "PASS" else
                   "&#10007;" if sc == "FAIL" else "&#8226;")
            cls = ("sub-pass" if sc == "PASS" else
                   "sub-fail" if sc == "FAIL" else "sub-pend")
            se  = ('<span class="sub-err">— {}</span>'.format(sub["error"])
                   if sub.get("error") else "")
            sub_html += (
                '<div class="sub-row {cls}">'
                '<span class="sub-ico">{ico}</span>'
                '<span class="sub-field">{field}</span>'
                '<span class="sub-val">{val}</span>{se}'
                '</div>').format(
                cls=cls, ico=ico,
                field=sub["field"],
                val=sub.get("value") or "",
                se=se)

        sub_section = (
            '<tr class="sub-tr"><td></td>'
            '<td colspan="2"><div class="sub-wrap">{}</div>'
            '</td></tr>'.format(sub_html)) if sub_html else ""

        step_rows += """
        <tr class="{row_cls}">
          <td class="td-num">{num}</td>
          <td class="td-status">{ico}</td>
          <td class="td-desc">
            <div class="desc-text">{desc}</div>
            {err}
          </td>
        </tr>{sub}""".format(
            row_cls=row_cls,
            num=s["_display_num"],
            ico=status_icon,
            desc=s.get("description", ""),
            err=err_html,
            sub=sub_section)

    # ── Error table ───────────────────────────────────────────
    err_section = ""
    if errors:
        err_rows = "".join(
            '<tr><td><code>{time}</code></td>'
            '<td>{location}</td><td>{action}</td>'
            '<td class="err-msg">{message}</td></tr>'.format(**e)
            for e in errors)
        err_section = """
        <div class="section">
          <div class="err-hdr">
            &#9888;&nbsp; Errors &amp; Failures
            <span class="badge-count">{}</span>
          </div>
          <table class="data-table">
            <thead><tr>
              <th>Time</th><th>Location</th>
              <th>Action</th><th>Message</th>
            </tr></thead>
            <tbody>{}</tbody>
          </table>
        </div>""".format(len(errors), err_rows)

        # Count from visible_steps only so cards match the table
    def _succ(s):
        if s.get("action") in _FORM_ACTIONS:
            return _form_step_success(s)
        return s.get("success")

    total = len(visible_steps)
    gpass = sum(1 for s in visible_steps if _succ(s) is True)
    gfail = sum(1 for s in visible_steps if _succ(s) is False)
    errc  = len(errors)

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>A-Vertex Test Report</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0 }}
  body {{
    font-family: 'Segoe UI', system-ui, Arial, sans-serif;
    background: #f0f4f8;
    color: #1a202c;
    padding: 32px 24px;
    min-height: 100vh;
  }}

  /* ── Top banner ── */
  .banner {{
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    color: white;
    border-radius: 14px;
    padding: 28px 36px;
    margin-bottom: 28px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 16px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.18);
  }}
  .banner-left h1 {{
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 0.3px;
    margin-bottom: 6px;
  }}
  .banner-left .org {{
    font-size: 12px;
    color: #94a3b8;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 12px;
  }}
  .banner-left .goal-row {{
    font-size: 13px;
    color: #cbd5e1;
    word-break: break-all;
  }}
  .banner-left .goal-row span {{
    color: #7dd3fc;
    font-weight: 500;
  }}
  .banner-right {{ text-align: right; }}
  .result-pill {{
    display: inline-block;
    padding: 8px 24px;
    border-radius: 24px;
    font-size: 16px;
    font-weight: 800;
    letter-spacing: 1px;
    color: white;
    background: {rc};
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
    margin-bottom: 8px;
  }}
  .meta-grid {{
    font-size: 12px;
    color: #94a3b8;
    line-height: 1.8;
    text-align: right;
  }}
  .meta-grid b {{ color: #cbd5e1; }}

  /* ── Stat cards — 4 only ── */
  .cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 16px;
    margin-bottom: 28px;
  }}
  .card {{
    background: white;
    border-radius: 12px;
    padding: 20px 18px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.07);
    border-top: 4px solid #e2e8f0;
  }}
  .card.c-total {{ border-color: #0ea5e9; }}
  .card.c-pass  {{ border-color: #16a34a; }}
  .card.c-fail  {{ border-color: #dc2626; }}
  .card.c-err   {{ border-color: #f59e0b; }}
  .card .c-num  {{ font-size: 32px; font-weight: 800; color: #1e293b; }}
  .card.c-pass .c-num {{ color: #16a34a; }}
  .card.c-fail .c-num {{ color: #dc2626; }}
  .card.c-err  .c-num {{ color: #f59e0b; }}
  .card .c-lbl {{
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: #64748b;
    margin-top: 4px;
  }}

  /* ── Section ── */
  .section {{ margin-bottom: 28px; }}
  .err-hdr {{
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0.4px;
    padding: 10px 16px;
    background: white;
    border-radius: 10px 10px 0 0;
    border-left: 5px solid #dc2626;
    color: #dc2626;
    display: flex;
    align-items: center;
    gap: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}
  .badge-count {{
    background: #dc2626;
    color: white;
    border-radius: 10px;
    padding: 1px 8px;
    font-size: 11px;
    font-weight: 700;
  }}

  /* ── Tables ── */
  .data-table {{
    width: 100%;
    border-collapse: collapse;
    background: white;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  }}
  .data-table thead tr {{
    background: #1e293b;
    color: #e2e8f0;
    font-size: 12px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
  }}
  .data-table th, .data-table td {{
    padding: 11px 16px;
    text-align: left;
    font-size: 13px;
  }}
  .data-table tbody tr {{ border-bottom: 1px solid #f1f5f9; }}
  .data-table tbody tr:last-child {{ border-bottom: none; }}
  .data-table tbody tr:hover {{ background: #f8fafc; }}

  .row-pass {{ background: #f0fdf4 !important; }}
  .row-fail {{ background: #fff5f5 !important; }}
  .row-pend {{ background: #fffbeb !important; }}

  .td-num    {{ width: 44px; font-weight: 700; color: #64748b; font-size: 13px; }}
  .td-status {{ width: 36px; font-size: 18px; text-align: center; }}
  .row-pass .td-status {{ color: #16a34a; }}
  .row-fail .td-status {{ color: #dc2626; }}
  .row-pend .td-status {{ color: #d97706; }}

  .desc-text {{ font-size: 13px; color: #334155; }}
  .step-err {{
    font-size: 12px; color: #dc2626;
    margin-top: 4px;
    background: #fef2f2;
    padding: 3px 8px;
    border-radius: 4px;
    border-left: 3px solid #dc2626;
  }}
  .err-msg {{ color: #dc2626; font-size: 12px; }}

  /* ── Sub-steps ── */
  .sub-tr td {{ padding: 0 !important; }}
  .sub-wrap {{
    padding: 6px 16px 10px 48px;
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
  }}
  .sub-row {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 4px 0;
    border-bottom: 1px solid #e9eef4;
    font-size: 12px;
  }}
  .sub-row:last-child {{ border-bottom: none; }}
  .sub-ico {{
    width: 16px; text-align: center;
    font-size: 14px; flex-shrink: 0;
  }}
  .sub-pass .sub-ico {{ color: #16a34a; }}
  .sub-fail .sub-ico {{ color: #dc2626; }}
  .sub-pend .sub-ico {{ color: #d97706; }}
  .sub-field {{
    font-weight: 600; color: #475569;
    min-width: 130px; flex-shrink: 0;
  }}
  .sub-val {{
    font-family: 'Consolas', monospace;
    color: #0369a1;
    background: #f0f9ff;
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 11px;
  }}
  .sub-err {{ color: #dc2626; font-size: 11px; margin-left: 6px; }}

  /* ── Footer ── */
  .footer {{
    text-align: center;
    font-size: 11px;
    color: #94a3b8;
    margin-top: 16px;
  }}
</style>
</head>
<body>

<!-- Banner -->
<div class="banner">
  <div class="banner-left">
    <div class="org">A-Vertex &nbsp;·&nbsp; Automation Test Report</div>
    <h1>Test Execution Report</h1>
    <div class="goal-row">Goal: <span>{goal}</span></div>
  </div>
  <div class="banner-right">
    <div class="result-pill">{result}</div>
    <div class="meta-grid">
      <div><b>Reason:</b> {reason}</div>
      <div><b>Started:</b> {started}</div>
      <div><b>Ended:</b> {ended}</div>
      <div><b>Duration:</b> {duration}</div>
      <div><b>Executed by:</b> {exec_by}</div>
    </div>
  </div>
</div>

<!-- 4 stat cards: Total Steps | Passed | Failed | Errors -->
<div class="cards">
  <div class="card c-total">
    <div class="c-num">{total}</div>
    <div class="c-lbl">Total Steps</div>
  </div>
  <div class="card c-pass">
    <div class="c-num">{gpass}</div>
    <div class="c-lbl">Passed</div>
  </div>
  <div class="card c-fail">
    <div class="c-num">{gfail}</div>
    <div class="c-lbl">Failed</div>
  </div>
  <div class="card c-err">
    <div class="c-num">{errc}</div>
    <div class="c-lbl">Errors</div>
  </div>
</div>

{err_section}

<!-- Step table: no header bar, no URL column, no category badges, wait steps hidden -->
<div class="section">
  <table class="data-table">
    <thead>
      <tr>
        <th>#</th>
        <th></th>
        <th>Description</th>
      </tr>
    </thead>
    <tbody>{step_rows}</tbody>
  </table>
</div>

<div class="footer">
  Generated by A-Vertex Automation Tool &nbsp;·&nbsp; {started}
</div>

</body>
</html>""".format(
        rc=rc, result=result,
        goal=report.get("goal", ""),
        reason=report.get("reason", "N/A"),
        started=started, ended=ended,
        duration=report.get("duration", ""),
        exec_by=report.get("executed_by", "N/A"),
        total=total, gpass=gpass, gfail=gfail, errc=errc,
        err_section=err_section,
        step_rows=step_rows,
    )