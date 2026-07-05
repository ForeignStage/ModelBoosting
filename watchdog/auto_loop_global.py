#!/usr/bin/env python3
"""Global auto loop -- iterates all watched projects, runs auto_executor for each.
Project-agnostic: reads watch_dirs.json, no manual root needed.
Runs until fuse blown on ALL projects simultaneously.
v5.32: Mode persistence via last_mode.json. Survives reboot.
"""
import sys, os, subprocess, json, time
from datetime import datetime

_wd  = os.path.dirname(os.path.abspath(__file__))
_cfg = os.path.join(_wd, '..', 'config', 'watch_dirs.json')
from paths import PYTHONW_EXE as PYTHONW

def load_projects():
    try:    return json.load(open(_cfg, encoding='utf-8')).get('watch', [])
    except: return []

def has_queue(root):
    return os.path.exists(os.path.join(root, 'docs', 'TASK_QUEUE.md'))

def fuse_ok(root):
    try:
        r = subprocess.run([PYTHONW, os.path.join(_wd,'enforce.py'),'fuse','--check'],
                           capture_output=True, text=True, cwd=root, timeout=10)
        return 'blown' not in r.stdout.lower()
    except: return True

def run_once(root, agent):
    r = subprocess.run(
        [PYTHONW, os.path.join(_wd,'auto_executor.py'),
         '--agent', agent, '--mode', 'auto', root],
        cwd=root, timeout=360)
    return r.returncode

def boot_all_projects():
    """Run boot --renew on all watched projects on startup."""
    projects = load_projects()
    results = []
    for root in projects:
        if not os.path.isdir(root):
            continue
        wd = os.path.join(root, 'watchdog')
        if not os.path.exists(os.path.join(wd, 'enforce.py')):
            continue
        try:
            r = subprocess.run(
                [PYTHONW, os.path.join(_wd, 'enforce.py'), 'boot', '--renew'],
                capture_output=True, text=True, cwd=root, timeout=15)
            results.append((root, r.returncode == 0))
        except:
            results.append((root, False))
    ok = sum(1 for _, success in results if success)
    print(f'[GLOBAL-LOOP] Boot renewed: {ok}/{len(results)} projects', flush=True)
    return results

def check_global_fuse():
    """Global fuse check across all projects. Returns true if ANY project still has budget."""
    projects = load_projects()
    for root in projects:
        if not os.path.isdir(root):
            continue
        if fuse_ok(root):
            return True
    return False

MODE_STATE_FILE = os.path.join(_wd, '..', 'config', 'last_mode.json')

def persist_mode(mode):
    try:
        os.makedirs(os.path.dirname(MODE_STATE_FILE), exist_ok=True)
        with open(MODE_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'mode': mode, 'timestamp': datetime.now().isoformat()}, f)
    except:
        pass

def restore_mode():
    """Restore last known mode. Defaults to interactive."""
    try:
        if os.path.exists(MODE_STATE_FILE):
            data = json.load(open(MODE_STATE_FILE, "r", encoding="utf-8"))
            return data.get('mode', 'interactive')
    except:
        pass
    return 'interactive'

def main():
    agents = sys.argv[1:] if sys.argv[1:] else ['codex', 'claude_code']
    print(f'[GLOBAL-LOOP] Started {datetime.now().isoformat()} agents={agents}', flush=True)

    # STEP 0: Restore mode (survives reboot)
    saved_mode = restore_mode()
    print(f'[GLOBAL-LOOP] Restored mode: {saved_mode}', flush=True)

    # STEP 1: Boot --renew all projects
    boot_all_projects()

    # STEP 2: If was in auto mode, resume. Otherwise idle-monitor only.
    if saved_mode != 'auto':
        print('[GLOBAL-LOOP] Mode is interactive. Idle-monitoring only (no auto-exec).', flush=True)
    while True:
        # Check if we should stay in auto mode
        current_mode = restore_mode()
        if current_mode != 'auto':
            if not check_global_fuse():
                print('[GLOBAL-LOOP] All fuses blown. Exiting.', flush=True)
                persist_mode('interactive')
                sys.exit(0)
            time.sleep(30)
            continue

        projects = [p for p in load_projects() if os.path.isdir(p) and has_queue(p)]
        if not projects:
            time.sleep(30); continue
        did_work = False
        for root in projects:
            if not fuse_ok(root):
                print(f'[GLOBAL-LOOP] FUSE BLOWN: {root}'); continue
            for agent in agents:
                rc = run_once(root, agent)
                if rc == 3:  # fuse
                    print(f'[GLOBAL-LOOP] FUSE BLOWN -- stopping all.')
                    persist_mode('interactive'); sys.exit(3)
                if rc == 0: did_work = True
        time.sleep(5 if did_work else 30)

if __name__ == '__main__':
    main()