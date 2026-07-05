#!/usr/bin/env python3
"""Global FS Watchdog -- violation enforcer + cross-agent wakeup notifier.
Runs as background daemon. Two jobs:
  1. Scope gate: file write without SCOPE_active.md -> violation log / EMERGENCY_STOP
  2. Queue watch: TASK_QUEUE.md change -> write CC_WAKEUP.md / CODEX_WAKEUP.md
"""
import os, time, json
from datetime import datetime
from paths import safe_print

_here = os.path.dirname(os.path.abspath(__file__))
CFG  = os.path.join(_here, "..", "config", "watch_dirs.json")
LOG  = os.path.join(_here, "..", "logs", "VIOLATION.log")
EXTS = ('.py', '.md', '.json', '.toml', '.txt')
POLL = 2
TRIP = 5

WAKEUP = {'claude_code': 'CC_WAKEUP.md', 'codex': 'CODEX_WAKEUP.md'}
SECTION = {'claude_code': 'QUEUED -- Claude Code', 'codex': 'QUEUED -- Codex'}

def load_dirs():
    try:    return json.load(open(CFG, encoding="utf-8"))["watch"]
    except: return [r"E:\AgentHub"]

def scope_exists(path):
    d = os.path.dirname(path)
    for _ in range(4):
        if os.path.exists(os.path.join(d, "docs", "SCOPE_active.md")): return True
        parent = os.path.dirname(d)
        if parent == d: break
        d = parent
    return False

def log_v(path):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    open(LOG, "a", encoding="utf-8").write(f"[{datetime.now().isoformat()}] NO_SCOPE: {path}\n")

def emergency_stop(dirs, count):
    msg = f"FSWatcher: {count} violations -- {datetime.now().isoformat()}\n"
    for d in dirs:
        doc = os.path.join(d, "docs"); os.makedirs(doc, exist_ok=True)
        open(os.path.join(doc, "EMERGENCY_STOP"), "w", encoding="utf-8").write(msg)
    print(f"[WATCHER] EMERGENCY_STOP ({count} violations)", flush=True)

def snapshot(dirs):
    s = {}
    for d in dirs:
        if not os.path.isdir(d): continue
        for root, _, files in os.walk(d):
            for fn in files:
                if fn.endswith(EXTS):
                    p = os.path.join(root, fn)
                    try: s[p] = os.stat(p).st_mtime
                    except OSError: pass
    return s

# --- Queue monitoring (structural fix) ---

def parse_pending(queue_path):
    """Return {agent: [task, ...]} for unclaimed tasks."""
    try: text = open(queue_path, encoding="utf-8").read()
    except: return {}
    pending = {a: [] for a in WAKEUP}
    cur = None
    for line in text.splitlines():
        for agent, sec in SECTION.items():
            if sec in line: cur = agent; break
        else:
            if line.startswith("## "): cur = None
        if cur and line.strip().startswith("- [ ]") and "[IN PROGRESS" not in line:
            pending[cur].append(line.strip()[5:].strip())
    return pending

def write_wakeup(queue_path, agent, tasks):
    docs = os.path.dirname(queue_path)
    wp = os.path.join(docs, WAKEUP[agent])
    with open(wp, "w", encoding="utf-8") as f:
        f.write(f"# WAKEUP {agent.upper()} -- {datetime.now().isoformat()}\n")
        f.write(f"Pending: {len(tasks)}\n\n")
        for t in tasks: f.write(f"- {t}\n")
    return wp

def clear_wakeup(queue_path, agent):
    wp = os.path.join(os.path.dirname(queue_path), WAKEUP[agent])
    if os.path.exists(wp): os.remove(wp)

def check_queues(dirs, prev_snap, curr_snap):
    for p, mt in curr_snap.items():
        if os.path.basename(p) != "TASK_QUEUE.md": continue
        if prev_snap.get(p) == mt: continue
        # Queue changed -- parse and write wakeups
        pending = parse_pending(p)
        for agent, tasks in pending.items():
            if tasks:
                wp = write_wakeup(p, agent, tasks)
                print(f"[WATCHER] WAKEUP: {len(tasks)} task(s) -> {agent} ({wp})", flush=True)
            else:
                clear_wakeup(p, agent)

# --- Main loop ---

def main():
    dirs = load_dirs()
    prev = snapshot(dirs)
    count = 0
    print(f"[WATCHER] Active -- {datetime.now().isoformat()}", flush=True)
    while True:
        time.sleep(POLL)
        curr = snapshot(dirs)
        for p, mt in curr.items():
            if prev.get(p) is not None and prev[p] != mt:
                if not scope_exists(p) and os.path.basename(p) != "TASK_QUEUE.md":
                    log_v(p); count += 1
                    print(f"[WATCHER] VIOLATION #{count}: {p}", flush=True)
                    if count >= TRIP:
                        emergency_stop(dirs, count); count = 0
        check_queues(dirs, prev, curr)
        prev = curr

if __name__ == "__main__":
    main()
