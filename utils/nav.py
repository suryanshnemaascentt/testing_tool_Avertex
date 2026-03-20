# from config.settings import BASE_URL

# # ============================================================
# # utils/nav.py
# # Navigation logic — defined once, imported by every module.
# # Pass the target fragment; this file handles the rest.
# # New module usage:
# #   from utils.nav import nav_done, handle_nav, reset_nav
# # ============================================================


# class _NavState:
#     """Tracks navigation progress across steps."""

#     def __init__(self):
#         self.done           = False   # True once the target page is reached
#         self.fallback_fired = False   # True after a hard navigate was triggered
#         self.interacted     = set()   # selectors already clicked to avoid repeats

#     def reset(self):
#         self.__init__()

# _nav = _NavState()


# def reset_nav():
#     """Reset navigation state. Call this at the start of every new run."""
#     _nav.reset()
#     print("[NAV] State reset")


# def nav_done():
#     """Returns True once the browser is on the correct target page."""
#     return _nav.done


# def handle_nav(els, url, target_fragment):
#     """
#     Navigate to the page matching target_fragment.

#     Examples:
#         handle_nav(els, url, "projects")   -> navigates to /projects
#         handle_nav(els, url, "timesheets") -> navigates to /timesheets

#     Returns:
#         dict  — next navigation action
#         None  — already on the correct page
#     """
#     # Already on the target page
#     if target_fragment in url.lower() and "microsoftonline.com" not in url.lower():
#         _nav.done = True
#         print("[NAV] Already on /{} page".format(target_fragment))
#         return None

#     # Still on SSO — wait for login to complete first
#     if "microsoftonline.com" in url.lower():
#         return {"action": "wait", "seconds": 1}

#     # Try clicking the sidebar/nav link
#     nav_el = els.get("projects_nav")
#     if nav_el and nav_el["selector"] not in _nav.interacted:
#         _nav.interacted.add(nav_el["selector"])
#         print("[NAV] Clicking nav link: {}".format(nav_el["selector"]))
#         return {"action": "click", "selector": nav_el["selector"]}

#     # Fallback: hard-navigate directly to the URL
#     if not _nav.fallback_fired:
#         _nav.fallback_fired = True
#         target = "{}/{}".format(BASE_URL, target_fragment)
#         print("[NAV] Fallback navigate -> " + target)
#         return {"action": "navigate", "url": target}

#     return {"action": "wait", "seconds": 1}

from config.settings import BASE_URL

# ============================================================
# utils/nav.py
# Navigation logic — defined once, imported by every module.
# Pass the target fragment; this file handles the rest.
# New module usage:
#   from utils.nav import nav_done, handle_nav, reset_nav
# ============================================================


class _NavState:
    """Tracks navigation progress across steps."""

    def __init__(self):
        self.done           = False   # True once the target page is reached
        self.fallback_fired = False   # True after a hard navigate was triggered
        self.interacted     = set()   # selectors already clicked to avoid repeats

    def reset(self):
        self.__init__()

_nav = _NavState()


def reset_nav():
    """Reset navigation state. Call this at the start of every new run."""
    _nav.reset()
    print("[NAV] State reset")


def nav_done():
    """Returns True once the browser is on the correct target page."""
    return _nav.done


def handle_nav(els, url, target_fragment):
    """
    Navigate to the page matching target_fragment.

    Examples:
        handle_nav(els, url, "projects")   -> navigates to /projects
        handle_nav(els, url, "timesheets") -> navigates to /timesheets
        handle_nav(els, url, "estimates")  -> navigates to /estimates

    The nav element is looked up dynamically using target_fragment,
    so this function works for ANY module without any changes here.

    Returns:
        dict  — next navigation action
        None  — already on the correct page
    """
    # Already on the target page
    if target_fragment in url.lower() and "microsoftonline.com" not in url.lower():
        _nav.done = True
        print("[NAV] Already on /{} page".format(target_fragment))
        return None

    # Still on SSO — wait for login to complete first
    if "microsoftonline.com" in url.lower():
        return {"action": "wait", "seconds": 1}

    # Look up nav element dynamically using target_fragment.
    # Each module's scan_dom() stores its nav link under "nav_<fragment>".
    # e.g. projects  -> els["nav_projects"]
    #      estimates -> els["nav_estimates"]
    #      timesheets-> els["nav_timesheets"]
    nav_key = "nav_" + target_fragment
    nav_el  = els.get(nav_key)
    if nav_el and nav_el["selector"] not in _nav.interacted:
        _nav.interacted.add(nav_el["selector"])
        print("[NAV] Clicking nav link [{}]: {}".format(nav_key, nav_el["selector"]))
        return {"action": "click", "selector": nav_el["selector"]}

    # Fallback: hard-navigate directly to the URL
    if not _nav.fallback_fired:
        _nav.fallback_fired = True
        target = "{}/{}".format(BASE_URL, target_fragment)
        print("[NAV] Fallback navigate -> " + target)
        return {"action": "navigate", "url": target}

    return {"action": "wait", "seconds": 1}