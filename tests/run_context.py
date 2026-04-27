# ============================================================
# tests/run_context.py
#
# Shared context object that flows through the suite in order.
# Each step deposits what it created; the next step withdraws
# what it needs — eliminating all cross-module manual inputs.
# ============================================================


class RunContext:
    """
    Carries entity names created during the suite run to dependent steps.

    Lifecycle:
        - project create    → post_hook stores ctx.project_name
        - project update    → post_hook overwrites ctx.project_name with new name
        - job add           → post_hook stores ctx.job_name
        - activities        → reads ctx.project_name + ctx.job_name
        - timesheet         → reads ctx.project_name + ctx.job_name
        - project delete    → reads ctx.project_name, no write
    """

    def __init__(self):
        self.project_name       = ""   # populated after project create / update succeeds
        self.job_name           = ""   # populated after job add succeeds
        self.project_start_date = ""   # ISO YYYY-MM-DD — set after project create
        self.project_end_date   = ""   # ISO YYYY-MM-DD — set after project create

    def project_or(self, fallback):
        """Return project_name if set, otherwise return fallback."""
        return self.project_name if self.project_name else fallback

    def job_or(self, fallback):
        """Return job_name if set, otherwise return fallback."""
        return self.job_name if self.job_name else fallback
