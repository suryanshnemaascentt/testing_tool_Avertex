# ============================================================
# modules/__init__.py
#
# Auto-discovers all active modules. To add a new module:
#   1. Create modules/<name>.py
#        (must define: MODULE_META, decide_action, reset_state,
#                      ACTIONS, ACTION_KEYS)
#   2. Create executor/form_filler/<name>.py
#        (must define: FORM_ACTION_NAME, FORM_SUB_STEPS,
#                      fill_<name>_form)
#   No other shared files need to change.
# ============================================================
import importlib
import pkgutil
import pathlib

MODULES = {}
for _mi in pkgutil.iter_modules([str(pathlib.Path(__file__).parent)]):
    if _mi.name.startswith("_"):
        continue
    try:
        _m = importlib.import_module("modules.{}".format(_mi.name))
        if hasattr(_m, "MODULE_META"):
            MODULES[_mi.name] = _m.MODULE_META
    except Exception:
        pass

MODULE_KEYS = list(MODULES)
try:
    del _mi, _m
except NameError:
    pass


def get_module_info(key):
    """Return the metadata dict for the given module key."""
    if key not in MODULES:
        raise KeyError("Unknown module: '{}'. Available: {}".format(key, list(MODULES)))
    return MODULES[key]