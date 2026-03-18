from __future__ import annotations
import json
import os
from datetime import datetime


class TestReporter:
    """
    Lightweight test reporter.

    Usage:
        reporter = TestReporter(goal="login and create project", url="https://...")
        reporter.start()
        reporter.log_step(1, {"action": "click", ...}, current_url)
        reporter.update_last_step(success=True)
        reporter.finish(result="PASS", reason="Project created")
        reporter.save_report()
        reporter.print_summary()
    """

    def __init__(self, goal: str, url: str):
        self.goal       = goal
        self.url        = url
        self.steps:  list[dict] = []
        self.result: str        = "UNKNOWN"
        self.reason: str        = ""
        self._start_time: datetime | None = None
        self._end_time:   datetime | None = None

    # ── Lifecycle ──────────────────────────────────────────

    def start(self):
        self._start_time = datetime.now()
        print(f"[REPORT] Test started: {self._start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"[REPORT] Goal : {self.goal}")
        print(f"[REPORT] URL  : {self.url}")

    def finish(self, result: str, reason: str = ""):
        self._end_time = datetime.now()
        self.result    = result
        self.reason    = reason

    # ── Step logging ───────────────────────────────────────

    def log_step(self, step_num: int, action: dict, current_url: str):
        self.steps.append({
            "step":    step_num,
            "action":  action,
            "url":     current_url,
            "success": None,           # filled by update_last_step
        })

    def update_last_step(self, success: bool):
        if self.steps:
            self.steps[-1]["success"] = success

    # ── Output ─────────────────────────────────────────────

    def _duration(self) -> str:
        if self._start_time and self._end_time:
            secs = (self._end_time - self._start_time).total_seconds()
            return f"{secs:.1f}s"
        return "N/A"

    def print_summary(self):
        icon = "[PASS]" if self.result == "PASS" else ("[FAIL]" if self.result == "FAIL" else "[?]")
        print("\n" + "=" * 55)
        print(f"  TEST SUMMARY")
        print("=" * 55)
        print(f"  Result   : {icon} {self.result}")
        print(f"  Reason   : {self.reason or 'N/A'}")
        print(f"  Steps    : {len(self.steps)}")
        print(f"  Duration : {self._duration()}")
        print(f"  Goal     : {self.goal}")
        print("=" * 55 + "\n")

    def save_report(self, output_dir: str = "reports"):
        os.makedirs(output_dir, exist_ok=True)
        timestamp = (self._start_time or datetime.now()).strftime("%Y%m%d_%H%M%S")
        filename  = os.path.join(output_dir, f"report_{timestamp}.json")

        report = {
            "goal":       self.goal,
            "url":        self.url,
            "result":     self.result,
            "reason":     self.reason,
            "duration":   self._duration(),
            "started_at": self._start_time.isoformat() if self._start_time else None,
            "ended_at":   self._end_time.isoformat()   if self._end_time   else None,
            "steps":      self.steps,
        }

        with open(filename, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=str)

        print(f"[REPORT] Saved -> {filename}")
        return filename