import asyncio

from tests.run_context import RunContext
from tests.test_plan   import build_plan

# ============================================================
# tests/suite_runner.py
#
# Zero-prompt automated suite runner.
# Runs every test in build_plan() in order — no user input needed.
#
# Usage:
#   python main.py --auto
# ============================================================


async def run_full_suite(url):
    """
    Execute the full automated test suite end-to-end.

    Args:
        url  — base URL of the application (from config.settings.BASE_URL)

    Returns:
        list of result dicts: {id, name, status, reason}
    """
    # Deferred import to avoid circular imports at module load time
    import main as _main
    from report.test_report import generate_suite_report

    ctx     = RunContext()
    plan    = build_plan(ctx)
    results = []
    total   = len(plan)

    print("\n" + "=" * 60)
    print("  AUTOMATED SUITE — {} test item(s)".format(total))
    print("=" * 60)

    for idx, tc in enumerate(plan):
        module_key = tc["module_key"]
        action_key = tc["action_key"]
        label      = tc["label"]
        requires   = tc.get("requires")
        post_hook  = tc.get("post_hook")

        # ── Dependency guard ──────────────────────────────────
        if requires and not requires(ctx):
            print("\n[SKIP] ({}/{}) {} — dependency not satisfied".format(
                idx + 1, total, label))
            results.append({
                "id":     "{}.{}".format(module_key, action_key),
                "name":   label,
                "status": "SKIP",
                "reason": "Dependency not met — prior required step likely failed",
            })
            continue

        # ── Evaluate goal (may be a lambda) ───────────────────
        raw_goal = tc["goal"]
        goal = raw_goal(ctx) if callable(raw_goal) else raw_goal

        print("\n[SUITE] ({}/{}) {}".format(idx + 1, total, label))
        print("        goal: {}".format(goal or "(negative suite — no goal string)"))

        # ── Negative suite sentinel ───────────────────────────
        if action_key == "__negative_suite__":
            try:
                neg_results = await _main.run_negative_suite(
                    url                = url,
                    module_key         = module_key,
                    action_key         = "create",
                    selected_scenarios = None,
                )
                results.extend(neg_results)
            except Exception as exc:
                print("[SUITE] [ERR] Negative suite raised: {}".format(exc))
                results.append({
                    "id":     "{}.neg_suite".format(module_key),
                    "name":   label,
                    "status": "FAIL",
                    "reason": "Negative suite error: {}".format(exc),
                })
            continue

        # ── Regular test step ─────────────────────────────────
        try:
            outcome = await _main.run(
                url          = url,
                module_key   = module_key,
                action_key   = action_key,
                goal         = goal,
                test_mode    = True,
                keep_session = False,
            )
        except Exception as exc:
            outcome = {"result": "FAIL", "reason": "Unexpected error: {}".format(exc)}

        status = outcome.get("result", "FAIL")
        results.append({
            "id":     "{}.{}".format(module_key, action_key),
            "name":   label,
            "status": status,
            "reason": outcome.get("reason", ""),
        })

        if post_hook:
            post_hook(ctx, outcome)

        icon = "[PASS]" if status == "PASS" else ("[WARN]" if status == "WARN" else "[FAIL]")
        print("[SUITE] {} {} — {}".format(icon, label, outcome.get("reason", "")))

    # ── Consolidated HTML + JSON report ──────────────────────
    generate_suite_report(results, "FULL AUTOMATED SUITE")

    passed  = sum(1 for r in results if r["status"] == "PASS")
    failed  = sum(1 for r in results if r["status"] == "FAIL")
    warned  = sum(1 for r in results if r["status"] == "WARN")
    skipped = sum(1 for r in results if r["status"] == "SKIP")

    print("\n" + "=" * 60)
    print("  SUITE COMPLETE")
    print("  Total: {}  |  Pass: {}  |  Fail: {}  |  Warn: {}  |  Skip: {}".format(
        len(results), passed, failed, warned, skipped))
    print("=" * 60 + "\n")

    return results
