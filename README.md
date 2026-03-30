# A-Vertex Automation Tool

A modular browser automation tool for [vertex-dev.savetime.com](https://vertex-dev.savetime.com) built with Python and Playwright. Automates Project module actions (Create, Update, Delete) via Microsoft SSO login. Designed to scale cleanly to new modules (Estimates, Timesheet, Clients, etc.) without touching existing code.

---

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Project Structure](#project-structure)
- [Running the Tool](#running-the-tool)
- [Configuration](#configuration)
- [How It Works](#how-it-works)
- [Adding a New Module](#adding-a-new-module)
- [Test Reports](#test-reports)
- [Troubleshooting](#troubleshooting)

---

## Requirements

- Python **3.10** or higher
- pip
- Internet access to reach `vertex-dev.savetime.com`
- Microsoft SSO credentials for the app

---

## Installation

### 1. Clone or download the project

```
A_vertex_testing_tool/
├── main.py
├── requirements.txt
├── config/
├── utils/
├── modules/
├── executor/
├── dom/
└── report/
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Install the Chromium browser used by Playwright

```bash
playwright install chromium
```

### 5. (Optional) Set environment variables

You can override defaults using environment variables instead of typing them each run:

```bash
# Windows
set AVERTEX_EMAIL=your.email@company.com
set AVERTEX_BASE_URL=https://vertex-dev.savetime.com

# macOS / Linux
export AVERTEX_EMAIL=your.email@company.com
export AVERTEX_BASE_URL=https://vertex-dev.savetime.com
```

---

## Project Structure

```
A_vertex_testing_tool/
│
├── main.py                      # Entry point — CLI menu + run loop
│
├── requirements.txt             # Python dependencies
│
├── config/
│   ├── __init__.py
│   └── settings.py              # All constants: URL, timings, browser settings
│
├── utils/                       # Shared utilities used by every module
│   ├── __init__.py
│   ├── login.py                 # Microsoft SSO login flow
│   ├── nav.py                   # Page navigation logic
│   └── dom_scanner.py           # Common DOM element scanner
│
├── modules/                     # One file per app module
│   ├── __init__.py              # Module registry (add new modules here)
│   └── project.py               # Project module: create / update / delete
│
├── executor/                    # Browser action execution layer
│   ├── __init__.py
│   ├── executor.py              # Step dispatcher — routes actions to handlers
│   ├── actions.py               # Generic browser actions (click, type, MUI)
│   └── form_filler.py           # Per-module form fill logic
│
├── dom/
│   └── dom_builder.py           # Live DOM extraction from Playwright page
│
└── report/
    └── test_report.py           # JSON test report generator
```

### Responsibility of each layer

| Layer | File(s) | Responsibility |
|---|---|---|
| Entry point | `main.py` | CLI, browser launch, step loop |
| Config | `config/settings.py` | All constants in one place |
| Utils | `utils/login.py`, `nav.py`, `dom_scanner.py` | Login + nav shared across all modules |
| Modules | `modules/project.py` | Action logic for one module only |
| Executor | `executor/executor.py` | Routes action dicts to the right function |
| Actions | `executor/actions.py` | Generic click/type/MUI helpers |
| Forms | `executor/form_filler.py` | Form fill logic per module |
| DOM | `dom/dom_builder.py` | Raw DOM extraction |
| Report | `report/test_report.py` | JSON test reports |

---

## Running the Tool

```bash
python main.py
```

The CLI will guide you through three prompts:

```
==========================================
  A-Vertex Automation Tool
==========================================

  Login Details  (press Enter to use defaults)
  App URL  [https://vertex-dev.savetime.com/]:
  Email    [suryansh.nema@ascentt.com]:
  Password:

  --------------------------------------
  MODULE SELECT
  --------------------------------------
  1  ->  Project
  --------------------------------------
  Select module (number or name): 1

  --------------------------------------
  PROJECT — ACTION SELECT
  --------------------------------------
  1  ->  Create Project  (auto name + dates)
  2  ->  Update Project  (search by name)
  3  ->  Delete Project  (search by name)
  --------------------------------------
  Select action (number or name): 3
  Enter Project name: AutoProject_123456
```

A Chromium browser window opens and the automation runs. When done, a JSON report is saved to the `reports/` folder.

---

## Configuration

All settings live in `config/settings.py`. You never need to edit any other file to change these values.

| Setting | Default | Description |
|---|---|---|
| `BASE_URL` | `https://vertex-dev.savetime.com` | App base URL |
| `MAX_STEPS` | `60` | Maximum automation steps before stopping |
| `DEFAULT_EMAIL` | `suryansh.nema@ascentt.com` | Default login email |
| `HEADLESS` | `False` | Set `True` to run without a visible browser |
| `DOM_SETTLE_MS` | `5000` | ms to wait for DOM to settle each step |
| `T_SAVE` | `1500` | ms to wait after clicking Save |
| `T_OPTION_LOAD` | `800` | ms to wait for MUI dropdown options |

All timing constants can also be overridden via environment variables:

```bash
AVERTEX_MAX_STEPS=30 python main.py
```

---

## How It Works

Each run follows a fixed three-phase loop repeated up to `MAX_STEPS` times:

```
Phase 1 — Login
  utils/login.py detects which SSO step is visible
  (email → Next → password → Sign in → Stay signed in)
  and returns the next action to execute.

Phase 2 — Navigate
  utils/nav.py checks if the browser is on the correct page.
  If not, it clicks the sidebar link or falls back to a hard navigate.

Phase 3 — Action
  The module's decide_action() runs the requested action
  (create / update / delete) as a step-by-step state machine.
  Each call returns exactly one action dict, e.g.:
    {"action": "click", "selector": "button:has-text('Delete')"}
  executor/executor.py executes it and the loop continues.
```

The loop stops when the module returns `{"action": "done", "result": "PASS/FAIL"}`.

---

## Adding a New Module

To add support for a new app section (e.g. Estimates) — **only 4 files need to change**:

### Step 1 — Create `modules/estimates.py`

```python
from utils.login       import login_done, handle_login, reset_login
from utils.nav         import nav_done,   handle_nav,   reset_nav
from utils.dom_scanner import scan_common_dom
from config.settings   import BASE_URL

NAV_FRAGMENT = "estimates"

ACTIONS = {
    "create": {"label": "Create Estimate", "needs_target": False},
}
ACTION_KEYS = list(ACTIONS.keys())

def scan_dom(dom):
    result = scan_common_dom(dom)
    # add estimates-specific elements here
    return result

def reset_state():
    reset_login()
    reset_nav()
    # reset your state classes here

async def decide_action(action, dom, url, goal="", email=None, password=None):
    els = scan_dom(dom)
    if not login_done():
        step = handle_login(els, email, password, url)
        if step: return step
    if not nav_done():
        step = handle_nav(els, url, NAV_FRAGMENT)
        if step: return step
    # your action logic here
```

### Step 2 — Register in `modules/__init__.py`

```python
MODULES = {
    "project":   {"name": "Project",   "fragment": "projects"},
    "estimates": {"name": "Estimates", "fragment": "estimates"},  # add this
}
```

### Step 3 — Add form filler in `executor/form_filler.py`

```python
async def fill_estimate_form(page, p):
    # your form fill logic here
    await _set_text_input(page, p.get("name"))
    return await _save_form(page)
```

### Step 4 — Register in `main.py` and `executor/executor.py`

In `main.py` `_load_module_handler()`:
```python
if module_key == "estimates":
    from modules.estimates import decide_action, reset_state, ACTIONS, ACTION_KEYS
    return decide_action, reset_state, ACTIONS, ACTION_KEYS
```

In `executor/executor.py` fill_form block:
```python
if module_name == "estimates":
    return await fill_estimate_form(page, params)
```

**Nothing else needs to change.** Login, nav, DOM extraction, reporting — all reused automatically.

---

## Test Reports

After every run a JSON report is saved to `reports/report_<timestamp>.json`:

```json
{
  "goal": "delete project AutoProject_123456",
  "url": "https://vertex-dev.savetime.com/",
  "result": "PASS",
  "reason": "Project 'AutoProject_123456' deleted — not found in search results",
  "duration": "34.2s",
  "started_at": "2026-03-19T14:22:10",
  "ended_at": "2026-03-19T14:22:44",
  "steps": [
    {"step": 1, "action": {"action": "wait"}, "url": "...", "success": true},
    ...
  ]
}
```

---

## Troubleshooting

### Browser does not open
Make sure Chromium is installed:
```bash
playwright install chromium
```

### Login gets stuck
- Check that your email and password are correct.
- The tool handles the full SSO flow automatically (email → Next → password → Sign in → Stay signed in). If the SSO page changes, update `utils/login.py`.

### "New Project" button not found
The tool waits up to `MAX_WAIT = 4` steps for each element. If the app is slow, increase `DOM_SETTLE_MS` in `config/settings.py`.

### Delete succeeds but returns FAIL
The tool verifies deletion using three methods:
1. Success toast detection (strict phrase matching)
2. Re-searching the project name after deletion
3. Checking the DOM for the project name (count == 0 = PASS)

If all three fail within `MAX_WAIT` steps, it returns FAIL. Try increasing `MAX_WAIT` in `_DeleteState` inside `modules/project.py`.

### MUI dropdown does not open
The tool uses `force=True` for delete buttons and falls back to JS click if normal click fails. For other dropdowns, check that the label text in `fill_project_form()` exactly matches the label visible on the page.

### Running headless
Set `HEADLESS = True` in `config/settings.py` to run without a visible browser window. Useful for CI/CD environments.

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `AVERTEX_BASE_URL` | `https://vertex-dev.savetime.com` | Override the target URL |
| `AVERTEX_EMAIL` | `suryansh.nema@ascentt.com` | Default login email |
| `AVERTEX_MAX_STEPS` | `60` | Override the step limit |



<!-- _____________________________ -->

project:- AutoProject_174314
job :- Planning & Requirements
Date:- 2026-03-23

A063-FY26-Ascentt Internal-Testing Environment   


