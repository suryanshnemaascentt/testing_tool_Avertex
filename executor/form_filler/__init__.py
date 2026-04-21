# ============================================================
# executor/form_filler/__init__.py
#
# Auto-discovers all fill_*_form functions from sibling modules.
# To add a new form filler:
#   1. Create executor/form_filler/<name>.py
#   2. Define fill_<name>_form(page, params) inside it
#   No changes needed here.
# ============================================================
import importlib
import pkgutil
import pathlib

for _ff_info in pkgutil.iter_modules([str(pathlib.Path(__file__).parent)]):
    if _ff_info.name.startswith("_"):
        continue
    _ff_mod = importlib.import_module(".{}".format(_ff_info.name), package=__name__)
    for _ff_attr in dir(_ff_mod):
        if _ff_attr.startswith("fill_") and _ff_attr.endswith("_form"):
            globals()[_ff_attr] = getattr(_ff_mod, _ff_attr)

del importlib, pkgutil, pathlib, _ff_info, _ff_mod, _ff_attr
