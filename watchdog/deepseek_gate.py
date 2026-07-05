#!/usr/bin/env python3
"""DeepSeek Discipline Gate -- Pre-execution clarify/scope enforcer.
Usage: python deepseek_gate.py "<task>" [watchdog_dir]
Returns: 0=GO, 1=STOP
v5.33 -- interactive mode: unconditional pass. Auto mode: original strict behavior.
v5.34 -- model-aware: frontier models (opus/gpt/sonnet/gemini) auto-pass.
v5.35 -- uses canonical get_calibration() from model_detect (calibration.json cache).
Only deepseek or unknown models face the gate in auto mode.
"""
import sys, os
from datetime import datetime

# ── Canonical calibration resolver (v5.35) ──
def _is_frontier(watchdog_dir):
    """Use model_detect.get_calibration() -- cached calibration.json, no per-call sqlite hit."""
    try:
        from model_detect import get_calibration
        cal = get_calibration(watch_dir=watchdog_dir, project_dir=watchdog_dir)
        return cal.get("frontier_active", False)
    except Exception:
        return False  # if detect fails, enforce gate (conservative)

EXECUTE_KW = {
    "写入","执行","开工","干","修","部署","加进去",
    "write","create","edit","delete","run","fix","add",
    "remove","update","install","implement","build","generate","change"
}
EXPLORE_KW = {
    "你觉得","如何","探讨","假如","或许","提问",
    "what","why","how","should","could","would",
    "discuss","explain","analyze","review","check","思路","分析"
}

def read_mode(wd):
    """Read current mode from watchdog/mode file. Defaults to interactive."""
    mode_file = os.path.join(wd, "mode")
    if not os.path.exists(mode_file):
        return "interactive"
    try:
        with open(mode_file, 'r', encoding='utf-8') as f:
            mode = f.read().strip()
        if mode in ('interactive', 'auto'):
            return mode
    except:
        pass
    return "interactive"

def detect_mode(text):
    t = text.lower()
    has_exec = any(k in t for k in EXECUTE_KW)
    has_expl = any(k in t for k in EXPLORE_KW) or text.strip().endswith(("?", "？"))
    if has_exec and not has_expl:
        return "EXECUTE"
    if has_expl and not has_exec:
        return "EXPLORE"
    return "CLARIFY"

def scope_exists(wd):
    p = os.path.normpath(os.path.join(wd, "..", "docs", "SCOPE_active.md"))
    return os.path.exists(p)

def write_clarify(wd, task, mode):
    docs = os.path.normpath(os.path.join(wd, "..", "docs"))
    os.makedirs(docs, exist_ok=True)
    p = os.path.join(docs, "CLARIFY_PENDING.md")
    if mode == "CLARIFY":
        reason = "Input contains both EXECUTE and EXPLORE signals, or is ambiguous."
        action = "State intent explicitly -- EXPLORE (discuss only) or EXECUTE (write code/files)?"
    else:
        reason = "EXECUTE detected but docs/SCOPE_active.md is missing."
        action = "Write docs/SCOPE_active.md (Task / Will write / Done when), then re-run gate."
    with open(p, "w", encoding="utf-8") as f:
        f.write(f"# CLARIFY PENDING -- {datetime.now().isoformat()}\n")
        f.write(f"Task: {task}\nMode detected: {mode}\nReason: {reason}\nAction: {action}\n")
    print(f"[GATE] Written: {p}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python deepseek_gate.py '<task>' [watchdog_dir]")
        sys.exit(1)
    task = sys.argv[1]
    wd = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(__file__))
    mode = detect_mode(task)
    has_scope = scope_exists(wd)
    session_mode = read_mode(wd)

    # v5.34: Frontier model bypass -- gate only exists to compensate DeepSeek weakness
    if _is_frontier(wd):
        print(f"[GATE] Frontier model detected -- gate bypassed. GO. (detected: {mode})")
        sys.exit(0)

    # v5.33: Interactive mode = unconditional pass. Never block the user.
    if session_mode == "interactive":
        print(f"[GATE] Interactive mode -- GO (detected: {mode}, scope={'YES' if has_scope else 'NO'})")
        sys.exit(0)

    # Auto mode: keep original strict behavior
    if mode == "EXPLORE":
        print(f"[GATE] EXPLORE -- discuss only, no execution. GO.")
        sys.exit(0)
    if mode == "EXECUTE" and has_scope:
        print(f"[GATE] EXECUTE + SCOPE found. GO.")
        sys.exit(0)

    print(f"[GATE] STOP -- mode={mode}, scope={'YES' if has_scope else 'NO'}")
    write_clarify(wd, task, mode)
    sys.exit(1)

if __name__ == "__main__":
    main()
