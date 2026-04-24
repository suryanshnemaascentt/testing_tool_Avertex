import re

from tests.run_context import RunContext
from tests.test_data   import ActivityData, JobData, TimesheetData

# ============================================================
# tests/test_plan.py
#
# Declarative ordered test plan.
# Each entry is a dict consumed by suite_runner.run_full_suite().
#
# Keys per entry:
#   module_key  str
#   action_key  str
#   goal        str | callable(ctx) -> str
#   label       str
#   requires    callable(ctx) -> bool | None   skip if returns False
#   post_hook   callable(ctx, outcome) | None  called after run() completes
# ============================================================

# Parses: "Project 'SomeName' created/updated ..."
_RE_PROJECT_NAME = re.compile(r"Project '(.+?)'")
# Parses: "Job 'SomeName' added/saved ..."
_RE_JOB_NAME     = re.compile(r"Job '(.+?)'")


def _capture_project(ctx, outcome):
    """
    Store the project name parsed from a successful create/update reason string.
    Called as post_hook after project create and project update steps.
    """
    if outcome.get("result") == "PASS":
        m = _RE_PROJECT_NAME.search(outcome.get("reason", ""))
        if m:
            ctx.project_name = m.group(1)
            print("[CTX] project_name captured = '{}'".format(ctx.project_name))


def _capture_job(ctx, outcome):
    """
    Store the job name parsed from a successful add_job reason string.
    Called as post_hook after job add step.
    """
    if outcome.get("result") == "PASS":
        m = _RE_JOB_NAME.search(outcome.get("reason", ""))
        if m:
            ctx.job_name = m.group(1)
            print("[CTX] job_name captured = '{}'".format(ctx.job_name))


def build_plan(ctx):
    """
    Returns the ordered list of test cases for the full automated suite.

    goals that depend on runtime context use lambdas so they are evaluated
    at execution time (after prior steps have populated ctx), not at plan
    build time.
    """
    return [
        # ── PROJECT: Create ───────────────────────────────────
        {
            "module_key": "project",
            "action_key": "create",
            "goal":       "create project",
            "label":      "Project -> Create",
            "requires":   None,
            "post_hook":  _capture_project,
        },

        # ── PROJECT: Change Status to Active ─────────────────
        # Sets the newly created project's status from Planned → Active.
        {
            "module_key": "project",
            "action_key": "change_status",
            "goal":       lambda c: "change status {}".format(c.project_name),
            "label":      "Project -> Change Status to Active",
            "requires":   lambda c: bool(c.project_name),
            "post_hook":  None,
        },

        # ── PROJECT: Update ───────────────────────────────────
        # Uses ctx.project_name captured by create step.
        {
            "module_key": "project",
            "action_key": "update",
            "goal":       lambda c: "update project {}".format(c.project_name),
            "label":      "Project -> Update",
            "requires":   lambda c: bool(c.project_name),
            "post_hook":  _capture_project,   # ctx now holds the *updated* name
        },

        # ── JOB: Add ─────────────────────────────────────────
        # Uses ctx.project_name (updated name) — no fallback needed.
        # Captures job name into ctx.job_name for Activities/Timesheet.
        {
            "module_key": "job",
            "action_key": "add_job",
            "goal":       lambda c: "add_job job {} | {}".format(
                c.project_name, JobData.NAME),
            "label":      "Job -> Add",
            "requires":   lambda c: bool(c.project_name),
            "post_hook":  _capture_job,
        },

        # ── ACTIVITIES: Add ───────────────────────────────────
        # Uses ctx.project_name + ctx.job_name — both from create steps above.
        {
            "module_key": "activities",
            "action_key": "add_activities",
            "goal":       lambda c: "add_activities project {} | job {} | activities {}".format(
                c.project_name,
                c.job_or(JobData.NAME),
                ActivityData.NAME,
            ),
            "label":      "Activities -> Add",
            "requires":   lambda c: bool(c.project_name),
            "post_hook":  None,
        },

        # ── TIMESHEET: Add ────────────────────────────────────
        # Uses ctx.project_name + ctx.job_name.
        # START_DATE is a random past Monday — different on every run.
        {
            "module_key": "timesheet",
            "action_key": "add_timesheet",
            "goal":       lambda c: (
                "add_timesheet start {} | project {} | job {} "
                "| hours {} | location {} | remarks {}".format(
                    TimesheetData.START_DATE,
                    c.project_name,
                    c.job_or(JobData.NAME),
                    TimesheetData.HOURS,
                    TimesheetData.LOCATION,
                    TimesheetData.REMARKS,
                )
            ),
            "label":      "Timesheet -> Add",
            "requires":   lambda c: bool(c.project_name),
            "post_hook":  None,
        },

        # ── PROJECT: Delete ───────────────────────────────────
        # Runs LAST — after all dependent steps are done.
        {
            "module_key": "project",
            "action_key": "delete",
            "goal":       lambda c: "delete project {}".format(c.project_name),
            "label":      "Project -> Delete",
            "requires":   lambda c: bool(c.project_name),
            "post_hook":  None,
        },

        # ── PROJECT: Negative Suite ───────────────────────────
        # Special sentinel — suite_runner calls run_negative_suite() for this.
        {
            "module_key": "project",
            "action_key": "__negative_suite__",
            "goal":       "",
            "label":      "Project -> Negative Suite (8 scenarios)",
            "requires":   None,
            "post_hook":  None,
        },
    ]
