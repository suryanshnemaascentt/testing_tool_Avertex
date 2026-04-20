MODULES = {
    "project": {
        "name": "Project",
        "fragment": "projects",
    },

    
    "client": {
        "name": "client",
    "fragment": "Clients"
    },

    "add_client": {   # ✅ ADD THIS BLOCK
        "name": "Add Client",
        "fragment": "clients"
    },

    "access_control": {
        "name": "Access Control",
        "fragment": "access",
    },

    "estimate_AI_based": {
        "name": "AI-Based Estimation",
        "fragment": "estimates"
    },

    "edit_estimate": {
        "name": "Edit Estimate",
        "fragment": "estimates"
    },

}

MODULE_KEYS = list(MODULES.keys())


def get_module_info(key):
    if key not in MODULES:
        raise KeyError("Unknown module: " + key)
    return MODULES[key]