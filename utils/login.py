from config.settings import BASE_URL
from utils.session_manager import session_exists, delete_session, is_redirected_to_sso

# ============================================================
# utils/login.py
#
# Session-aware login handler.
#
# When a valid session.json exists:
#   → login_done() returns True immediately on first call
#   → handle_login() returns None (skip all SSO steps)
#
# When session is missing / expired:
#   → session is re-created by main.py BEFORE automation starts
#   → by the time handle_login() is called, session is always valid
#
# Mid-run expiry (rare):
#   → is_redirected_to_sso() detects SSO redirect
#   → session deleted, run ends with FAIL so next run re-creates session
#
# Module usage (unchanged from before):
#   from utils.login import login_done, handle_login, reset_login
# ============================================================


class _LoginState:
    def __init__(self):
        self.done             = False
        self.session_checked  = False
        self.yes_clicked      = False
        self._empty_dom_count = 0
        self.MAX_EMPTY_DOM    = 5

    def reset(self):
        self.__init__()

_login = _LoginState()


def reset_login():
    """Reset login state. Called at the start of every run."""
    _login.reset()
    print("[LOGIN] State reset")


def login_done() -> bool:
    """Returns True once login is confirmed for this run."""
    return _login.done


def handle_login(els, email, password, url):
    """
    Determine the next login action.

    With a valid session pre-loaded into the browser context,
    this function marks login as done immediately and returns None,
    so the module skips straight to Phase 2 (navigation).

    Args:
        els      — scanned DOM dict from scan_common_dom()
        email    — kept for compatibility; unused when session is valid
        password — kept for compatibility; unused when session is valid
        url      — current page URL

    Returns:
        dict  — next action to execute (only if SSO fallback is needed)
        None  — login already complete
    """
    if _login.done:
        return None

    # ── First call: check session ────────────────────────────
    if not _login.session_checked:
        _login.session_checked = True

        if session_exists():
            # Session was pre-loaded into context by main.py.
            # If we are on the app (not SSO), we are already logged in.
            if not is_redirected_to_sso(url):
                print("[LOGIN] Session valid — login skipped ✓")
                _login.done = True
                return None
            else:
                # Session file exists but browser still landed on SSO.
                # Session is stale — delete it so next run re-creates it.
                print("[LOGIN] Session stale (redirected to SSO) — deleting")
                delete_session()
                # Fall through to SSO flow below (rare edge case)

    # ── Mid-run SSO redirect = session expired ───────────────
    if is_redirected_to_sso(url) and _login.session_checked:
        print("[LOGIN] Unexpected SSO redirect — session expired mid-run")
        delete_session()
        # Signal failure; main.py will re-create session on next run
        return {"action": "done", "result": "FAIL",
                "reason": "Session expired mid-run — re-run to re-login"}

    # ── SSO fallback (only if session was stale/missing) ─────
    is_sso = "microsoftonline.com" in url.lower()
    is_app = BASE_URL.replace("https://", "") in url.lower()

    if _login.yes_clicked and not is_sso:
        print("[LOGIN] SSO redirect complete — login done")
        _login.done = True
        return None

    if is_app and not is_sso:
        dom_count = len(els.get("dom_raw") or [])
        if dom_count == 0:
            _login._empty_dom_count += 1
            print("[LOGIN] DOM empty ({}/{}) — waiting".format(
                _login._empty_dom_count, _login.MAX_EMPTY_DOM))
            if _login._empty_dom_count >= _login.MAX_EMPTY_DOM:
                print("[LOGIN] No login form — treating as logged in")
                _login.done = True
                return None
            return {"action": "wait", "seconds": 1}
        else:
            _login._empty_dom_count = 0

    e  = els.get("email_input")
    pw = els.get("password_input")
    nb = els.get("next_btn")
    sb = els.get("signin_btn")
    yb = els.get("yes_btn")

    print("[LOGIN] email={} pw={} next={} signin={} yes={}  sso={}".format(
        "Y" if e else "N", "Y" if pw else "N",
        "Y" if nb else "N", "Y" if sb else "N",
        "Y" if yb else "N", "Y" if is_sso else "N",
    ))

    if yb:
        _login.yes_clicked = True
        print("[LOGIN] Clicking Yes / Stay signed in")
        return {"action": "click", "selector": yb["selector"],
                "sso_yes": True, "soft_fail": True}

    if not e and not pw and len(els.get("dom_raw") or []) > 0:
        print("[LOGIN] No credentials form — treating as logged in")
        _login.done = True
        return None

    if pw:
        if not (pw.get("value") or "").strip() and password:
            return {"action": "type", "selector": pw["selector"], "text": password}
        if (pw.get("value") or "").strip() and sb:
            return {"action": "click", "selector": sb["selector"]}
        return {"action": "wait", "seconds": 1}

    if e:
        if not (e.get("value") or "").strip() and email:
            return {"action": "type", "selector": e["selector"], "text": email}
        if (e.get("value") or "").strip() and nb:
            return {"action": "click", "selector": nb["selector"]}

    return {"action": "wait", "seconds": 1}