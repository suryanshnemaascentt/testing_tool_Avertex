
# # import asyncio
# # from playwright.async_api import async_playwright

# # from config.settings    import (
# #     DEFAULT_URL, DEFAULT_EMAIL,
# #     MAX_STEPS, DOM_SETTLE_MS, SSO_SETTLE_MS, POST_RUN_S,
# #     VIEWPORT, HEADLESS,
# # )
# # from dom.dom_builder    import extract_live_dom
# # from executor.executor  import execute_step
# # from report.test_report import TestReporter
# # from modules            import MODULES, MODULE_KEYS

# # # ============================================================
# # # main.py — Entry point only.
# # # Login, nav, DOM, timing — all defined in separate files.
# # # This file only:
# # #   1. Shows the CLI menu
# # #   2. Launches the browser
# # #   3. Runs the per-step loop
# # # ============================================================


# # def _load_module_handler(module_key):
# #     """
# #     Load decide_action and reset_state for the given module key.

# #     To add a new module:
# #       1. Create modules/<name>.py
# #       2. Register it in modules/__init__.py
# #       3. Add one if-line here
# #     """
# #     if module_key == "project":
# #         from modules.project import decide_action, reset_state, ACTIONS, ACTION_KEYS
# #         return decide_action, reset_state, ACTIONS, ACTION_KEYS

# #     # ── Add new modules here ───────────────────────────────────
# #     if module_key == "job":
# #         from modules.job import decide_action, reset_state, ACTIONS, ACTION_KEYS
# #         return decide_action, reset_state, ACTIONS, ACTION_KEYS
# #     if module_key == "activities":
# #             from modules.activities import decide_action, reset_state, ACTIONS, ACTION_KEYS
# #             return decide_action, reset_state, ACTIONS, ACTION_KEYS
    
# #     if module_key == "timesheet":
# #         from modules.timesheet import decide_action, reset_state, ACTIONS, ACTION_KEYS
# #         return decide_action, reset_state, ACTIONS, ACTION_KEYS

# #     raise ValueError("Unknown module: '{}'. Add it to _load_module_handler.".format(module_key))


# # # ============================================================
# # # PAGE ALIVE CHECK
# # # ============================================================

# # async def is_page_alive(page):
# #     """Returns True if the browser page is still open and responsive."""
# #     try:
# #         await page.evaluate("1")
# #         return True
# #     except Exception:
# #         return False


# # # ============================================================
# # # CORE RUN LOOP
# # # ============================================================

# # async def run(url, module_key, action_key, goal,
# #               email=None, password=None, test_mode=False):
# #     """
# #     Main automation loop.
# #     Launches the browser, loads the page, then repeatedly:
# #       1. Extracts the live DOM
# #       2. Asks the module what to do next (decide_action)
# #       3. Executes that action via execute_step
# #     Stops when action == 'done' or MAX_STEPS is reached.
# #     """
# #     reporter = TestReporter(goal=goal, url=url, email=email, password=password) if test_mode else None
# #     decide_action, reset_state, _, _ = _load_module_handler(module_key)
# #     reset_state()

# #     async with async_playwright() as p:
# #         browser = await p.chromium.launch(
# #             headless=HEADLESS,
# #             args=["--disable-blink-features=AutomationControlled"],
# #         )
# #         context = await browser.new_context(
# #             viewport=VIEWPORT,
# #             ignore_https_errors=True,
# #         )
# #         page = await context.new_page()
        
# #         # Auto-accept browser native dialogs (window.confirm, window.alert).
# #         # The delete confirmation on this app uses window.confirm() —
# #         # without this handler Playwright would dismiss it automatically
# #         # and the delete would never go through.
# #         async def handle_dialog(dialog):
# #             print("[DIALOG] '{}' -> accepting".format(dialog.message))
# #             await dialog.accept()
 
# #         page.on("dialog", handle_dialog)

# #         # Navigate with exponential back-off (up to 3 attempts)
# #         loaded = False
# #         for attempt in range(3):
# #             try:
# #                 print("[NAV] Loading {}  (attempt {})".format(url, attempt + 1))
# #                 await page.goto(url, wait_until="domcontentloaded", timeout=30000)
# #                 print("[OK] Page loaded")
# #                 loaded = True
# #                 break
# #             except Exception as e:
# #                 print("[WARN] Navigation failed: {}".format(e))
# #                 if attempt < 2:
# #                     await asyncio.sleep(0.5 * (2 ** attempt))

# #         if not loaded:
# #             print("[ERR] Could not load page after 3 attempts")
# #             if reporter:
# #                 reporter.start()
# #                 reporter.finish(result="FAIL", reason="Navigation failed")
# #                 reporter.save_report()
# #                 reporter.print_summary()
# #             await browser.close()
# #             return

# #         if reporter:
# #             reporter.start()

# #         last_was_wait = False

# #         for step_num in range(MAX_STEPS):
# #             print("\n{} STEP {} {}".format("=" * 12, step_num + 1, "=" * 12))

# #             if not await is_page_alive(page):
# #                 print("[ERR] Browser closed — stopping")
# #                 if reporter:
# #                     reporter.finish(result="FAIL", reason="Browser closed")
# #                     reporter.save_report()
# #                     reporter.print_summary()
# #                 break

# #             current_url = page.url
# #             print("URL: {}".format(current_url))

# #             # Wait for DOM to settle
# #             try:
# #                 await page.wait_for_load_state("domcontentloaded", timeout=DOM_SETTLE_MS)
# #             except Exception:
# #                 pass

# #             # Extra wait on SSO pages so login inputs fully render
# #             if "microsoftonline.com" in current_url:
# #                 try:
# #                     await page.wait_for_selector("input", timeout=5000)
# #                 except Exception:
# #                     pass
# #                 await page.wait_for_timeout(SSO_SETTLE_MS)

# #             raw_dom = await extract_live_dom(page)
# #             print("dom is :",raw_dom)
# #             if not last_was_wait:
# #                 print("[DOM] {} elements".format(len(raw_dom)))

# #             action = await decide_action(
# #                 action   = action_key,
# #                 dom      = raw_dom,
# #                 url      = current_url,
# #                 goal     = goal,
# #                 email    = email,
# #                 password = password,
# #                 page     = page,
# #             )
# #             print("[ACTION] {}".format(action))

# #             if reporter:
# #                 reporter.log_step(step_num + 1, action, current_url)

# #             # Stop when the module signals completion
# #             if action.get("action") == "done":
# #                 result = action.get("result", "UNKNOWN")
# #                 reason = action.get("reason", "")
# #                 icon   = "[PASS]" if result == "PASS" else ("[FAIL]" if result == "FAIL" else "[?]")
# #                 print("\n{}  {}  —  {}".format(icon, result, reason))
# #                 if reporter:
# #                     reporter.finish(result=result, reason=reason)
# #                     reporter.save_report()
# #                     reporter.print_summary()
# #                 break

# #             last_was_wait = action.get("action") == "wait"
# #             success = await execute_step(page, raw_dom, action)
# #             if reporter:
# #                 reporter.update_last_step(success=success)

# #         else:
# #             print("\n[FAIL] Max steps reached")
# #             if reporter:
# #                 reporter.finish(result="FAIL", reason="Max steps reached")
# #                 reporter.save_report()
# #                 reporter.print_summary()

# #         await asyncio.sleep(POST_RUN_S)
# #         try:
# #             await browser.close()
# #         except Exception:
# #             pass

# # def _build_timesheet_goal(extra_parts):
# #     """
# #     Build the goal string for add_timesheet from CLI inputs.
 
# #     extra_parts order (matches needs_target list):
# #       [0] start_date      e.g. "2026-03-23"
# #       [1] project_name    e.g. "Alpha Project"   (first row)
# #       [2] job_name        e.g. "Planning & Requirements"
 
# #     Produces:
# #       "add_timesheet start 2026-03-23 | project Alpha Project | job Planning & Requirements"
 
# #     Then asks if the user wants to add more project rows.
# #     """
# #     if len(extra_parts) < 3:
# #         return "add_timesheet start {}".format(" | ".join(extra_parts))
 
# #     start_date   = extra_parts[0]
# #     project_name = extra_parts[1]
# #     job_name     = extra_parts[2]
 
# #     goal = "add_timesheet start {} | project {} | job {}".format(
# #         start_date, project_name, job_name)
 
# #     # Ask for optional per-row extras
# #     hours = input("  Hours per day [8]: ").strip()
# #     if hours:
# #         goal += " | logging hours {}".format(hours)
 
# #     location = input(" location Location [ascentt office] (wfh/client office/ascentt office/travel/remote): ").strip()
# #     if location:
# #         goal += " | location {}".format(location)
 
# #     remarks = input("  with Remarks (optional, press Enter to skip): ").strip()
# #     if remarks:
# #         goal += " | remarks {}".format(remarks)
 
# #     # Additional project rows
# #     # while True:
# #     #     more = input("\n  Add another project row? (y/n) [n]: ").strip().lower()
# #     #     if more != "y":
# #     #         break
# #     #     proj2 = input("  Project name: ").strip()
# #     #     job2  = input("  Job name: ").strip()
# #     #     if proj2 and job2:
# #     #         goal += " | project {} | job {}".format(proj2, job2)
# #     #         hrs2 = input("  Hours per day [8]: ").strip()
# #     #         if hrs2:
# #     #             goal += " | hours {}".format(hrs2)
# #     #         loc2 = input("  Location [ascentt office]: ").strip()
# #     #         if loc2:
# #     #             goal += " | location {}".format(loc2)
 
# #     return goal

# # def _build_clone_goal(extra_parts):
# #     """
# #     Build goal string for clone_last_week.
# #     extra_parts: [start_date]  — the week to clone INTO.
# #     Start date is optional; if blank, current week is used.
# #     """
# #     start_date = extra_parts[0].strip() if extra_parts else ""
# #     if start_date:
# #         return "clone_last_week start {}".format(start_date)
# #     else:
# #         # No date given — module will default to current week
# #         return "clone_last_week"


# # # ── NEW ───────────────────────────────────────────────────────
# # def _build_approval_goal(extra_parts):
# #     """
# #     Build goal string for approve_timesheet.
# #     extra_parts order (matches needs_target list):
# #       [0] start_date    e.g. "2026-03-23"
# #       [1] project_name  e.g. "Alpha Corp"
# #       [2] requested_by  e.g. "John Doe"
# #       [3] action        e.g. "approve" or "reject"
# #     """
# #     start_date   = extra_parts[0].strip() if len(extra_parts) > 0 else datetime.now().strftime("%Y-%m-%d")
# #     project_name = extra_parts[1].strip() if len(extra_parts) > 1 else ""
# #     requested_by = extra_parts[2].strip() if len(extra_parts) > 2 else ""
# #     action       = extra_parts[3].strip().lower() if len(extra_parts) > 3 else "approve"

# #     if not start_date:
# #         from datetime import datetime
# #         start_date = datetime.now().strftime("%Y-%m-%d")

# #     parts = ["approve_timesheet",
# #              "start {}".format(start_date),
# #              "project {}".format(project_name)]
# #     if requested_by:
# #         parts.append("requested_by {}".format(requested_by))
# #     parts.append("action {}".format(action if action in ("approve", "reject") else "approve"))

# #     return " | ".join(parts)
# # # ── END NEW ───────────────────────────────────────────────────


# # # ============================================================
# # # CLI — Step 1: Module  →  Step 2: Action
# # # ============================================================

# # def _select_module():
# #     """Prompt the user to select a module from the registry."""
# #     print("\n" + "-" * 45)
# #     print("  MODULE SELECT")
# #     print("-" * 45)
# #     for i, key in enumerate(MODULE_KEYS, start=1):
# #         print("  {}  ->  {}".format(i, MODULES[key]["name"]))
# #     print("-" * 45)

# #     while True:
# #         choice = input("  Select module (number or name): ").strip()
# #         if choice.isdigit():
# #             idx = int(choice) - 1
# #             if 0 <= idx < len(MODULE_KEYS):
# #                 key = MODULE_KEYS[idx]
# #                 return key, MODULES[key]
# #         elif choice.lower() in MODULES:
# #             return choice.lower(), MODULES[choice.lower()]
# #         print("  [WARN] Invalid choice, please try again")


# # def _select_action(module_key, module_info):
# #     """Prompt the user to select an action for the chosen module."""
# #     _, _, ACTIONS, ACTION_KEYS = _load_module_handler(module_key)
 
# #     print("\n" + "-" * 45)
# #     print("  {} — ACTION SELECT".format(module_info["name"].upper()))
# #     print("-" * 45)
# #     for i, key in enumerate(ACTION_KEYS, start=1):
# #         print("  {}  ->  {}".format(i, ACTIONS[key]["label"]))
# #     print("-" * 45)
 
# #     while True:
# #         choice = input("  Select action (number or name): ").strip()
# #         action_key = None
# #         if choice.isdigit():
# #             idx = int(choice) - 1
# #             if 0 <= idx < len(ACTION_KEYS):
# #                 action_key = ACTION_KEYS[idx]
# #         elif choice.lower() in ACTIONS:
# #             action_key = choice.lower()
 
# #         if action_key:
# #             break
# #         print("  [WARN] Invalid choice, please try again")
 
# #     # If the action needs one or more target inputs, prompt for each.
# #     # needs_target can be:
# #     #   True        — single prompt: "Enter <Module> name:"
# #     #   ["a","b"]   — multiple prompts, one per label in the list
# #     # The collected values are joined with " | " and appended to the goal.
# #     extra_parts = []
# #     nt = ACTIONS[action_key]["needs_target"]
# #     if nt is True:
# #         val = input("  Enter {} name: ".format(module_info["name"])).strip()
# #         if val:
# #             extra_parts.append(val)
# #     elif isinstance(nt, list):
# #         for prompt_label in nt:
# #             val = input("  Enter {}: ".format(prompt_label)).strip()
# #             extra_parts.append(val)
 
# #     if action_key == "add_job" and len(extra_parts) == 2:
# #         goal = "add_job job {} | {}".format(extra_parts[0], extra_parts[1])
# #     elif action_key == "add_activities" and len(extra_parts) == 3:
# #         goal = "add_activities project {} | job {} | activities {}".format(
# #             extra_parts[0], extra_parts[1], extra_parts[2])
# #     elif action_key == "add_timesheet":
# #         goal = _build_timesheet_goal(extra_parts)
# #     elif action_key == "clone_last_week":
# #         goal = _build_clone_goal(extra_parts)
# #     elif action_key == "approve_timesheet":  # NEW
# #         goal = _build_approval_goal(extra_parts)  # NEW
# #     else:
# #         goal = "{} {}".format(action_key, module_key)
# #         if extra_parts:
# #             goal += " " + " | ".join(extra_parts)
    
# #     return action_key, goal

# # def get_inputs():
# #     """Collect all inputs from the user via CLI and return them."""
# #     print("\n" + "=" * 45)
# #     print("  A-Vertex Automation Tool")
# #     print("=" * 45)

# #     print("\n  Login Details  (press Enter to use defaults)")
# #     url = input("  App URL  [{}]: ".format(DEFAULT_URL)).strip()
# #     if not url:
# #         url = DEFAULT_URL

# #     email = input("  Email    [{}]: ".format(DEFAULT_EMAIL)).strip()
# #     if not email:
# #         email = DEFAULT_EMAIL

# #     password = input("  Password: ").strip()
# #     if not password:
# #         password = "Sn94948988@"

# #     module_key, module_info = _select_module()
# #     action_key, goal        = _select_action(module_key, module_info)

# #     print("\n" + "=" * 45)
# #     print("  URL      : {}".format(url))
# #     print("  Email    : {}".format(email))
# #     print("  Module   : {}".format(module_info["name"]))
# #     print("  Goal     : {}".format(goal))
# #     print("=" * 45 + "\n")

# #     return url, email, password, module_key, action_key, goal


# # # ============================================================
# # # ENTRY POINT
# # # ============================================================

# # if __name__ == "__main__":
# #     url, email, password, module_key, action_key, goal = get_inputs()
# #     asyncio.run(
# #         run(
# #             url        = url,
# #             module_key = module_key,
# #             action_key = action_key,
# #             goal       = goal,
# #             email      = email,
# #             password   = password,
# #             test_mode  = True,
# #         )
# #     )
# import asyncio
# from playwright.async_api import async_playwright

# from config.settings import (
#     BASE_URL, LOGIN_EMAIL, LOGIN_PASSWORD,
#     MAX_STEPS, DOM_SETTLE_MS, SSO_SETTLE_MS, POST_RUN_S,
#     VIEWPORT, HEADLESS,
# )
# from dom.dom_builder    import extract_live_dom
# from executor.executor  import execute_step
# from report.test_report import TestReporter
# from modules            import MODULES, MODULE_KEYS

# from utils.session_manager import (
#     session_exists,
#     create_session,
#     load_session,
#     is_redirected_to_sso,
#     delete_session,
#     # session_age_str,
# )

# # ============================================================
# # main.py — Entry point.
# #
# # LOGIN FLOW:
# #   1. Email/password are read from config/settings.py — no prompts.
# #   2. If session.json missing/expired → auto-login via create_session().
# #   3. If session.json fresh → browser loads with session, login skipped.
# #   4. Session expires mid-run → detected, deleted, run stops cleanly.
# # ============================================================


# def _load_module_handler(module_key):
#     if module_key == "project":
#         from modules.project import decide_action, reset_state, ACTIONS, ACTION_KEYS
#         return decide_action, reset_state, ACTIONS, ACTION_KEYS
#     if module_key == "job":
#         from modules.job import decide_action, reset_state, ACTIONS, ACTION_KEYS
#         return decide_action, reset_state, ACTIONS, ACTION_KEYS
#     if module_key == "activities":
#         from modules.activities import decide_action, reset_state, ACTIONS, ACTION_KEYS
#         return decide_action, reset_state, ACTIONS, ACTION_KEYS
#     if module_key == "timesheet":
#         from modules.timesheet import decide_action, reset_state, ACTIONS, ACTION_KEYS
#         return decide_action, reset_state, ACTIONS, ACTION_KEYS

#     raise ValueError("Unknown module: '{}'. Add it to _load_module_handler.".format(module_key))


# async def is_page_alive(page):
#     try:
#         await page.evaluate("1")
#         return True
#     except Exception:
#         return False


# # ============================================================
# # CORE RUN LOOP
# # ============================================================

# async def run(url, module_key, action_key, goal, test_mode=False):

#     # ── STEP 0: Ensure session exists ──────────────────────────
#     if not session_exists():
#         print("[MAIN] No valid session — starting auto-login...")
#         await create_session(base_url=url, viewport=VIEWPORT, headless=HEADLESS)
#         print("[MAIN] Session created.\n")

#     async with async_playwright() as p:

#         # 🔁 LOOP for auto-retry on session expiry
#         while True:

#             browser, context, page = await load_session(
#                 playwright=p,
#                 headless=HEADLESS,
#                 viewport=VIEWPORT,
#             )

#             try:
#                 print(f"[NAV] Opening {url}")
#                 await page.goto(url, wait_until="domcontentloaded")

#                 # ✅ CHECK SESSION VALID
#                 if is_redirected_to_sso(page.url):
#                     print("[AUTH] Session expired → Re-login triggered")

#                     await context.close()
#                     delete_session()

#                     await create_session(
#                         base_url=url,
#                         viewport=VIEWPORT,
#                         headless=HEADLESS
#                     )

#                     print("[MAIN] Restarting with fresh session...\n")
#                     continue  # 🔁 restart loop

#                 print("[MAIN] Logged in via session ✓\n")

#                 # ================================
#                 # 🚀 YOUR EXISTING LOGIC CONTINUES
#                 # ================================

#                 for step_num in range(MAX_STEPS):

#                     print(f"\n============ STEP {step_num + 1} ============")

#                     if is_redirected_to_sso(page.url):
#                         print("[AUTH] Session expired mid-run → recovering")

#                         await context.close()
#                         delete_session()

#                         await create_session(
#                             base_url=url,
#                             viewport=VIEWPORT,
#                             headless=HEADLESS
#                         )

#                         print("[MAIN] Restarting run...\n")
#                         break  # break loop → restart

#                     raw_dom = await extract_live_dom(page)

#                     action = await decide_action(
#                         action   = action_key,
#                         dom      = raw_dom,
#                         url      = page.url,
#                         goal     = goal,
#                         email    = LOGIN_EMAIL,
#                         password = LOGIN_PASSWORD,
#                         page     = page,
#                     )

#                     print("[ACTION]", action)

#                     if action.get("action") == "done":
#                         print("[SUCCESS]", action.get("result"))
#                         await context.close()
#                         return

#                     await execute_step(page, raw_dom, action)

#                 # loop restart if break happens
#                 continue

#             except Exception as e:
#                 print("[ERROR]", e)
#                 try:
#                     await context.close()
#                 except:
#                     pass
#                 raise e

# # ============================================================
# # GOAL BUILDERS
# # ============================================================

# def _build_timesheet_goal(extra_parts):
#     if len(extra_parts) < 3:
#         return "add_timesheet start {}".format(" | ".join(extra_parts))

#     goal = "add_timesheet start {} | project {} | job {}".format(
#         extra_parts[0], extra_parts[1], extra_parts[2])

#     hours = input("  Hours per day [8]: ").strip()
#     if hours:
#         goal += " | logging hours {}".format(hours)

#     location = input("  Location [ascentt office] (wfh/client office/ascentt office/travel/remote): ").strip()
#     if location:
#         goal += " | location {}".format(location)

#     remarks = input("  Remarks (optional, press Enter to skip): ").strip()
#     if remarks:
#         goal += " | remarks {}".format(remarks)

#     return goal


# def _build_clone_goal(extra_parts):
#     start_date = extra_parts[0].strip() if extra_parts else ""
#     return "clone_last_week start {}".format(start_date) if start_date else "clone_last_week"


# def _build_approval_goal(extra_parts):
#     from datetime import datetime
#     start_date   = extra_parts[0].strip() if len(extra_parts) > 0 else datetime.now().strftime("%Y-%m-%d")
#     project_name = extra_parts[1].strip() if len(extra_parts) > 1 else ""
#     requested_by = extra_parts[2].strip() if len(extra_parts) > 2 else ""
#     action       = extra_parts[3].strip().lower() if len(extra_parts) > 3 else "approve"

#     if not start_date:
#         start_date = datetime.now().strftime("%Y-%m-%d")

#     parts = [
#         "approve_timesheet",
#         "start {}".format(start_date),
#         "project {}".format(project_name),
#     ]
#     if requested_by:
#         parts.append("requested_by {}".format(requested_by))
#     parts.append("action {}".format(action if action in ("approve", "reject") else "approve"))
#     return " | ".join(parts)


# # ============================================================
# # CLI
# # ============================================================

# def _select_module():
#     print("\n" + "-" * 45)
#     print("  MODULE SELECT")
#     print("-" * 45)
#     for i, key in enumerate(MODULE_KEYS, start=1):
#         print("  {}  ->  {}".format(i, MODULES[key]["name"]))
#     print("-" * 45)

#     while True:
#         choice = input("  Select module (number or name): ").strip()
#         if choice.isdigit():
#             idx = int(choice) - 1
#             if 0 <= idx < len(MODULE_KEYS):
#                 key = MODULE_KEYS[idx]
#                 return key, MODULES[key]
#         elif choice.lower() in MODULES:
#             return choice.lower(), MODULES[choice.lower()]
#         print("  [WARN] Invalid choice, please try again")


# def _select_action(module_key, module_info):
#     _, _, ACTIONS, ACTION_KEYS = _load_module_handler(module_key)

#     print("\n" + "-" * 45)
#     print("  {} — ACTION SELECT".format(module_info["name"].upper()))
#     print("-" * 45)
#     for i, key in enumerate(ACTION_KEYS, start=1):
#         print("  {}  ->  {}".format(i, ACTIONS[key]["label"]))
#     print("-" * 45)

#     while True:
#         choice = input("  Select action (number or name): ").strip()
#         action_key = None
#         if choice.isdigit():
#             idx = int(choice) - 1
#             if 0 <= idx < len(ACTION_KEYS):
#                 action_key = ACTION_KEYS[idx]
#         elif choice.lower() in ACTIONS:
#             action_key = choice.lower()

#         if action_key:
#             break
#         print("  [WARN] Invalid choice, please try again")

#     extra_parts = []
#     nt = ACTIONS[action_key]["needs_target"]
#     if nt is True:
#         val = input("  Enter {} name: ".format(module_info["name"])).strip()
#         if val:
#             extra_parts.append(val)
#     elif isinstance(nt, list):
#         for prompt_label in nt:
#             val = input("  Enter {}: ".format(prompt_label)).strip()
#             extra_parts.append(val)

#     if action_key == "add_job" and len(extra_parts) == 2:
#         goal = "add_job job {} | {}".format(extra_parts[0], extra_parts[1])
#     elif action_key == "add_activities" and len(extra_parts) == 3:
#         goal = "add_activities project {} | job {} | activities {}".format(
#             extra_parts[0], extra_parts[1], extra_parts[2])
#     elif action_key == "add_timesheet":
#         goal = _build_timesheet_goal(extra_parts)
#     elif action_key == "clone_last_week":
#         goal = _build_clone_goal(extra_parts)
#     elif action_key == "approve_timesheet":
#         goal = _build_approval_goal(extra_parts)
#     else:
#         goal = "{} {}".format(action_key, module_key)
#         if extra_parts:
#             goal += " " + " | ".join(extra_parts)

#     return action_key, goal


# def get_inputs():
#     """
#     Collect only module/action inputs from CLI.
#     Email, password, and URL are read from config — no prompts for those.
#     """
#     print("\n" + "=" * 45)
#     print("  A-Vertex Automation Tool")
#     print("=" * 45)
#     print("  Email : {}".format(LOGIN_EMAIL))
#     print("  URL   : {}".format(BASE_URL))

#     if session_exists():
#         print("  [SESSION] Valid session — login will be skipped ✓")
#     else:
#         print("  [SESSION] No session — auto-login will run once")

#     module_key, module_info = _select_module()
#     action_key, goal        = _select_action(module_key, module_info)

#     print("\n" + "=" * 45)
#     print("  URL    : {}".format(BASE_URL))
#     print("  Email  : {}".format(LOGIN_EMAIL))
#     print("  Module : {}".format(module_info["name"]))
#     print("  Goal   : {}".format(goal))
#     print("=" * 45 + "\n")

#     return module_key, action_key, goal


# # ============================================================
# # ENTRY POINT
# # ============================================================

# if __name__ == "__main__":
#     module_key, action_key, goal = get_inputs()
#     asyncio.run(
#         run(
#             url        = BASE_URL,
#             module_key = module_key,
#             action_key = action_key,
#             goal       = goal,
#             test_mode  = True,
#         )
#     )
import asyncio
from playwright.async_api import async_playwright

from config.settings import BASE_URL, VIEWPORT, HEADLESS
from utils.session_manager import (
    session_exists,
    create_session,
    load_session,
    delete_session,
    is_redirected_to_sso,
)

from dom.dom_builder import extract_live_dom
from executor.executor import execute_step
from modules.project import decide_action, reset_state


MAX_STEPS = 10


# ============================================================
# MAIN RUNNER (FIXED)
# ============================================================

async def run():

    # Step 1: Ensure session exists
    if not session_exists():
        await create_session(BASE_URL, VIEWPORT, HEADLESS)

    async with async_playwright() as p:

        while True:  # 🔁 auto recovery loop

            _, context, page = await load_session(
                p, HEADLESS, VIEWPORT
            )

            try:
                print("[NAV] Opening app...")
                await page.goto(BASE_URL)

                # ✅ FIX: Session check (FULL RESET)
                if is_redirected_to_sso(page.url):
                    print("[AUTH] Session expired → FULL RESET")

                    await context.close()
                    delete_session()

                    await create_session(BASE_URL, VIEWPORT, HEADLESS)

                    print("[MAIN] Restarting...\n")
                    continue  # restart loop

                print("[MAIN] Logged in ✓")

                reset_state()

                # ===============================
                # 🚀 MAIN AUTOMATION LOOP
                # ===============================
                for step in range(MAX_STEPS):

                    print(f"\n--- STEP {step+1} ---")

                    # ✅ FIX: Mid-run expiry handling
                    if is_redirected_to_sso(page.url):
                        print("[AUTH] Session expired mid-run → FULL RESET")

                        await context.close()
                        delete_session()

                        await create_session(BASE_URL, VIEWPORT, HEADLESS)

                        print("[MAIN] Restarting run...\n")
                        break  # break loop → restart

                    dom = await extract_live_dom(page)

                    action = await decide_action(
                        action="create_project",
                        dom=dom,
                        url=page.url,
                        goal="create project",
                        email="",
                        password="",
                        page=page,
                    )

                    print("[ACTION]", action)

                    if action.get("action") == "done":
                        print("[SUCCESS] Completed ✓")
                        await context.close()
                        return

                    await execute_step(page, dom, action)

                continue  # restart if needed

            except Exception as e:
                print("[ERROR]", e)
                try:
                    await context.close()
                except:
                    pass
                raise


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    asyncio.run(run())