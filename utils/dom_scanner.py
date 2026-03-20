# # ============================================================
# # utils/dom_scanner.py
# # Scans common DOM elements needed by every module:
# # login inputs, nav links, and toast notifications.
# #
# # Each module calls scan_common_dom() first, then adds its
# # own module-specific elements on top of the result.
# # ============================================================

# _NON_TOAST = ("input", "button")          # tags that are never toasts
# _SIGNIN    = ("sign in", "signin", "log in", "login")
# _YES       = ("yes", "stay signed in", "kmsi")
# _NAV_TAGS  = ("a", "li", "span")
# _BTN_TAGS  = ("button", "input")
# _BTN_TYPES = ("button", "submit", "")


# def scan_common_dom(dom):
#     """
#     Scan the raw DOM list and return a dict of common elements.

#     Keys returned:
#         dom_raw        — original list (passed through for later use)
#         email_input    — email field on SSO login page
#         password_input — password field on SSO login page
#         next_btn       — "Next" button on email step
#         signin_btn     — "Sign in" button on password step
#         yes_btn        — "Yes" / "Stay signed in" button
#         projects_nav   — sidebar link to navigate to /projects
#         success_toast  — success notification element
#         error_toast    — error notification element
#     """
#     result = {
#         "dom_raw":        dom,
#         "email_input":    None,
#         "password_input": None,
#         "next_btn":       None,
#         "signin_btn":     None,
#         "yes_btn":        None,
#         "projects_nav":   None,
#         "success_toast":  None,
#         "error_toast":    None,
#     }

#     has_password = False

#     for el in dom:
#         tag   = (el.get("tag")         or "").lower()
#         etype = (el.get("type")        or "").lower()
#         eid   = (el.get("id")          or "").lower()
#         label = (el.get("label")       or "").lower().strip()
#         text  = (el.get("text")        or "").lower().strip()
#         val   = (el.get("value")       or "").lower().strip()
#         ph    = (el.get("placeholder") or "").lower()
#         cls   = (el.get("class")       or "").lower()
#         lv    = label + " " + text + " " + val
#         comb  = lv + " " + eid + " " + ph + " " + cls

#         # ── Login inputs ──────────────────────────────────────
#         if etype == "email" or eid == "i0116":
#             result["email_input"] = el
#             continue
#         if etype == "password" or eid == "i0118":
#             result["password_input"] = el
#             has_password = True
#             continue

#         # ── Auth buttons ──────────────────────────────────────
#         if tag in _BTN_TAGS and etype in _BTN_TYPES:
#             if "next" in lv and not result["next_btn"]:
#                 result["next_btn"] = el
#             elif any(w in lv for w in _SIGNIN) and not result["signin_btn"]:
#                 result["signin_btn"] = el
#             elif any(w in lv for w in _YES) and not result["yes_btn"]:
#                 result["yes_btn"] = el

#         # ── Navigation link ───────────────────────────────────
#         if tag in _NAV_TAGS and "project" in comb and not result["projects_nav"]:
#             result["projects_nav"] = el

#         # ── Toast notifications ───────────────────────────────
#         if tag not in _NON_TOAST:
#             if (any(x in comb for x in ("success", "saved", "created", "updated", "deleted"))
#                     and not result["success_toast"]):
#                 result["success_toast"] = el
#             if (any(x in comb for x in ("error", "failed", "invalid"))
#                     and not result["error_toast"]):
#                 result["error_toast"] = el

#     # Fix: the "Next" button doubles as "Sign in" or "Yes" depending on context
#     nb = result["next_btn"]
#     if nb:
#         if has_password:
#             # Password is visible — this "Next" is actually "Sign in"
#             result["signin_btn"] = nb
#             result["next_btn"]   = None
#         elif not result["email_input"] and not result["password_input"]:
#             # No login form visible — this "Next" is the "Stay signed in" prompt
#             result["yes_btn"]  = nb
#             result["next_btn"] = None

#     return result

# ============================================================
# utils/dom_scanner.py
# Scans common DOM elements needed by every module:
# login inputs and toast notifications.
#
# NAV ELEMENTS are NOT scanned here anymore.
# Each module's own scan_dom() scans its nav link and stores
# it under the key "nav_<fragment>", e.g.:
#   "nav_projects"   for the Projects sidebar link
#   "nav_estimates"  for the Estimates sidebar link
#   "nav_timesheets" for the Timesheets sidebar link
#
# This makes utils/nav.py work for ANY module without changes.
# ============================================================

_NON_TOAST = ("input", "button")
_SIGNIN    = ("sign in", "signin", "log in", "login")
_YES       = ("yes", "stay signed in", "kmsi")
_BTN_TAGS  = ("button", "input")
_BTN_TYPES = ("button", "submit", "")


def scan_common_dom(dom):
    """
    Scan the raw DOM list and return a dict of login/toast elements.

    Keys returned:
        dom_raw        — original list (passed through for later use)
        email_input    — email field on SSO login page
        password_input — password field on SSO login page
        next_btn       — "Next" button on email step
        signin_btn     — "Sign in" button on password step
        yes_btn        — "Yes" / "Stay signed in" button
        success_toast  — success notification element
        error_toast    — error notification element

    NOT included (each module scans its own):
        nav_<fragment> — sidebar nav link, scanned by each module's scan_dom()
    """
    result = {
        "dom_raw":        dom,
        "email_input":    None,
        "password_input": None,
        "next_btn":       None,
        "signin_btn":     None,
        "yes_btn":        None,
        "success_toast":  None,
        "error_toast":    None,
    }

    has_password = False

    for el in dom:
        tag   = (el.get("tag")         or "").lower()
        etype = (el.get("type")        or "").lower()
        eid   = (el.get("id")          or "").lower()
        label = (el.get("label")       or "").lower().strip()
        text  = (el.get("text")        or "").lower().strip()
        val   = (el.get("value")       or "").lower().strip()
        ph    = (el.get("placeholder") or "").lower()
        cls   = (el.get("class")       or "").lower()
        lv    = label + " " + text + " " + val
        comb  = lv + " " + eid + " " + ph + " " + cls

        # ── Login inputs ──────────────────────────────────────
        if etype == "email" or eid == "i0116":
            result["email_input"] = el
            continue
        if etype == "password" or eid == "i0118":
            result["password_input"] = el
            has_password = True
            continue

        # ── Auth buttons ──────────────────────────────────────
        if tag in _BTN_TAGS and etype in _BTN_TYPES:
            if "next" in lv and not result["next_btn"]:
                result["next_btn"] = el
            elif any(w in lv for w in _SIGNIN) and not result["signin_btn"]:
                result["signin_btn"] = el
            elif any(w in lv for w in _YES) and not result["yes_btn"]:
                result["yes_btn"] = el

        # ── Toast notifications ───────────────────────────────
        if tag not in _NON_TOAST:
            if (any(x in comb for x in ("success", "saved", "created", "updated", "deleted"))
                    and not result["success_toast"]):
                result["success_toast"] = el
            if (any(x in comb for x in ("error", "failed", "invalid"))
                    and not result["error_toast"]):
                result["error_toast"] = el

    # Fix: the "Next" button doubles as "Sign in" or "Yes" depending on context
    nb = result["next_btn"]
    if nb:
        if has_password:
            result["signin_btn"] = nb
            result["next_btn"]   = None
        elif not result["email_input"] and not result["password_input"]:
            result["yes_btn"]  = nb
            result["next_btn"] = None

    return result