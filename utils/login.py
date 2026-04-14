from config.settings import BASE_URL

# ============================================================
# utils/login.py
# SSO login logic — defined once, imported by every module.
# New module usage:
#   from utils.login import login_done, handle_login, reset_login
# ============================================================


class _LoginState:
    """Tracks all login progress across steps."""

    def __init__(self):
        self.done             = False   # True once login is complete
        self.yes_clicked      = False   # True after clicking "Stay signed in"
        self._empty_dom_count = 0       # counts consecutive empty DOMs on app page
        self.MAX_EMPTY_DOM    = 5       # after this many empty DOMs, treat as logged in

    def reset(self):
        self.__init__()

_login = _LoginState()


def reset_login():
    """Reset login state. Call this at the start of every new run."""
    _login.reset()
    print("[LOGIN] State reset")


def login_done():
    """Returns True once SSO login is fully complete."""
    return _login.done


def handle_login(els, email, password, url):
    """
    Determine the next login action based on the current DOM and URL.

    Returns:
        dict  — next action to execute (type email, click Next, etc.)
        None  — login is already complete, no action needed
    """
    if _login.done:
        return None

    is_sso = "microsoftonline.com" in url.lower()
    is_app = BASE_URL.replace("https://", "") in url.lower()

    # SSO redirect is finished when we land back on the app
    if _login.yes_clicked and not is_sso:
        print("[LOGIN] SSO redirect complete — login done")
        _login.done = True
        return None

    # On the app page with an empty DOM — page is still loading
    # Do NOT mark login done yet; wait for DOM to populate first
    if is_app and not is_sso:
        dom_count = len(els.get("dom_raw") or [])
        if dom_count == 0:
            _login._empty_dom_count += 1
            print("[LOGIN] DOM empty ({}/{}) — waiting for page".format(
                _login._empty_dom_count, _login.MAX_EMPTY_DOM))
            if _login._empty_dom_count >= _login.MAX_EMPTY_DOM:
                print("[LOGIN] No login form after {} waits — treating as logged in".format(
                    _login.MAX_EMPTY_DOM))
                _login.done = True
                return None
            return {"action": "wait", "seconds": 1}
        else:
            _login._empty_dom_count = 0  # DOM has content — reset counter

    e  = els.get("email_input")
    pw = els.get("password_input")
    nb = els.get("next_btn")
    sb = els.get("signin_btn")
    yb = els.get("yes_btn")

    print("[LOGIN] email={} pw={} next={} signin={} yes={}  url={}".format(
        "Y" if e else "N", "Y" if pw else "N",
        "Y" if nb else "N", "Y" if sb else "N",
        "Y" if yb else "N", "SSO" if is_sso else "APP",
    ))

    # "Stay signed in?" / "Yes" button
    if yb:
        _login.yes_clicked = True
        print("[LOGIN] Clicking Yes / Stay signed in")
        return {"action": "click", "selector": yb["selector"],
                "sso_yes": True, "soft_fail": True}

    # DOM has elements but no login form — already logged in
    if not e and not pw and len(els.get("dom_raw") or []) > 0:
        print("[LOGIN] No credentials form visible — treating as logged in")
        _login.done = True
        return None

    # Password step
    if pw:
        if not (pw.get("value") or "").strip() and password:
            return {"action": "type", "selector": pw["selector"], "text": password}
        if (pw.get("value") or "").strip() and sb:
            return {"action": "click", "selector": sb["selector"]}
        return {"action": "wait", "seconds": 1}

    # Email step
    if e:
        if not (e.get("value") or "").strip() and email:
            return {"action": "type", "selector": e["selector"], "text": email}
        if (e.get("value") or "").strip() and nb:
            return {"action": "click", "selector": nb["selector"]}

    return {"action": "wait", "seconds": 1}