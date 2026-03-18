MODULES = {
    "project": {
        "name": "Project",
        "fragment": "projects",
    },
}

MODULE_KEYS = list(MODULES.keys())


def get_module_info(key):
    if key not in MODULES:
        raise KeyError("Unknown module: " + key)
    return MODULES[key]