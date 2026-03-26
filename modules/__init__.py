# ============================================================
# modules/__init__.py
# Module registry — the only file to touch when adding a new module.
#
# To add a module:
#   1. Create modules/<name>.py
#   2. Uncomment (or add) its entry in MODULES below
#   3. Add one if-line in main.py _load_module_handler()
#   4. Add fill_<name>_form() in executor/form_filler.py
# ============================================================

MODULES = {
    "project": {
        "name":     "Project",
        "fragment": "projects",
    },
    "job": {
        "name":     "Jobs",
        "fragment": "jobs",
    },
    "activities":{
        "name":"Activities",
        "fragments":"activities",
    }
    # "timesheet": {
    #     "name":     "Timesheet",
    #     "fragment": "timesheets",
    # },
    # "clients": {
    #     "name":     "Clients",
    #     "fragment": "clients",
    # },
}

MODULE_KEYS = list(MODULES.keys())


def get_module_info(key):
    """Return the metadata dict for the given module key."""
    if key not in MODULES:
        raise KeyError("Unknown module: '{}'. Available: {}".format(key, MODULE_KEYS))
    return MODULES[key]