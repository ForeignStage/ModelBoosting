#!/usr/bin/env python3
"""Central path resolution -- all watchdog scripts import from here.
Single source of truth: config.json. Edit that file to change machine-specific paths.
"""
import os, json, sys

_wd = os.path.dirname(os.path.abspath(__file__))
_cfg_path = os.path.join(_wd, "config.json")

with open(_cfg_path, "r", encoding="utf-8") as _f:
    _cfg = json.load(_f)

_p = _cfg["paths"]

PYTHON_EXE = _p["python_exe"]
PYTHONW_EXE = PYTHON_EXE.replace("python.exe", "pythonw.exe")
AGENTS_MD = _p["agents_md"]
AGENT_HUB_ROOT = _p["agent_hub_root"]
GODCREATING_ROOT = _p["godcreating_root"]
USER_HOME = _p["user_home"]
INKSCAPE_PATH = _p["inkscape_path"]
CLAWD_ON_DESK = _p["clawd_on_desk"]
WATCHDOG_DIR = _cfp = os.path.join(GODCREATING_ROOT, "watchdog")


def safe_print(*args, **kwargs):
    """Print that won't crash on cp1252 terminals (Inkscape Python).
    Falls back to ASCII-safe encoding when Unicode fails."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = []
        for a in args:
            if isinstance(a, str):
                safe_args.append(a.encode("ascii", errors="replace").decode("ascii"))
            else:
                safe_args.append(a)
        print(*safe_args, **kwargs)
