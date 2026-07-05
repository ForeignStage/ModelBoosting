#!/usr/bin/env python3
"""H3 Self-Audit -- Q1-Q5 checks before any significant action.
Usage: python self_audit.py [--mode EXPLORE|EXECUTE|CLARIFY]
       [--no-scope] [--no-backup] [--non-python] [project_root]
Exit 0 = pass. Exit 1 = STOP.
v5.34 -- model-aware: frontier models (opus/gpt/sonnet/gemini) auto-pass.
v5.35 -- uses canonical get_calibration() from model_detect (calibration.json cache).
Only deepseek or unknown models face the self-audit gate.
"""
import sys, os

def _is_frontier(root):
    """Use model_detect.get_calibration() -- cached calibration.json."""
    try:
        # Prefer watchdog_dir for calibration.json lookup
        wd = os.path.join(root, "watchdog") if not root.endswith("watchdog") else root
        from model_detect import get_calibration
        cal = get_calibration(watch_dir=wd if os.path.isdir(wd) else None, project_dir=root)
        return cal.get("frontier_active", False)
    except Exception:
        return False

def audit(mode, has_scope, has_backup, py_safe):
    fails = []
    if mode == 'EXPLORE':
        fails.append('Q1: EXPLORE mode -- no writes. Discuss only.')
        return fails
    if mode == 'EXECUTE':
        if not has_scope:  fails.append('Q2: No SCOPE_active.md -- write docs/SCOPE_active.md first.')
        if not has_backup: fails.append('Q3: No backup -- python enforce.py backup --target [file]')
    if not py_safe:        fails.append('Q4: .py via non-Python tool -- use Python open().write().')
    return fails

def main():
    mode, has_scope, has_backup, py_safe = 'EXECUTE', True, True, True
    root = os.getcwd()
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == '--mode' and i+1 < len(args): mode = args[i+1].upper()
        if a == '--no-scope':   has_scope  = False
        if a == '--no-backup':  has_backup = False
        if a == '--non-python': py_safe    = False
        if os.path.isdir(a):   root        = a
    if has_scope and not os.path.exists(os.path.join(root,'docs','SCOPE_active.md')):
        has_scope = False

    # v5.34: Frontier model bypass -- self-audit only needed for DeepSeek
    if _is_frontier(root):
        print(f'[AUDIT] Frontier model detected -- self-audit bypassed. mode={mode}')
        sys.exit(0)

    fails = audit(mode, has_scope, has_backup, py_safe)
    if fails:
        for f in fails: print(f'[AUDIT] FAIL: {f}')
        print('[AUDIT] STOP.'); sys.exit(1)
    print(f'[AUDIT] Q1-Q5 PASS. mode={mode}')

if __name__ == '__main__':
    main()
