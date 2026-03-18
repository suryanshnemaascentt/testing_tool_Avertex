# A-Vertex Automation Tool — Environment Setup Guide

---

## Zaroori Cheezein (Prerequisites)

| Cheez | Minimum Version | Check karne ka command |
|-------|----------------|----------------------|
| Python | 3.10+ (3.11/3.12 recommended) | `python --version` |
| pip | 22+ | `pip --version` |
| Git (optional) | any | `git --version` |

---

## Step-by-Step Setup

---

### Step 1 — Python Install karo

#### Windows
1. https://python.org/downloads par jao
2. Latest Python 3.12.x download karo
3. Installer chalao — **"Add Python to PATH"** checkbox zaroor tick karo
4. Verify karo:
   ```
   python --version
   ```

#### macOS
```bash
# Homebrew se (recommended)
brew install python@3.12

# Verify
python3 --version
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip -y

# Verify
python3 --version
```

---

### Step 2 — Project Folder 
A_Vertex/
├── main.py
├── requirements.txt
├── dom/
├── executor/
├── module/
└── report/


### Step 3 — Virtual Environment(Recommended)

> Virtual environment 

#### Windows
```cmd
python -m venv venv
venv\Scripts\activate
```



### Step 4 — Dependencies Install 


pip install -r requirements.txt

### Step 5 — Playwright Browsers Install

playwright install chromium
```


### Step 6 — Tool run


python main.py

## Complete Setup —

#### Windows (Command Prompt)
```cmd
cd A_Vertex
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
python main.py