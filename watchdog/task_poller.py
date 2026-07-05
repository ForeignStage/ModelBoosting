#!/usr/bin/env python3
"""Task Poller -- claim pending tasks at agent session start.
Usage: python task_poller.py --agent codex|claude_code [project_root]
Exit 0 = no pending tasks. Exit 2 = task claimed (agent must execute it).
Add to STEP 1 of every session: run before check-all.
"""
import sys, os, re
from datetime import datetime

WAKEUP  = {'claude_code': 'CC_WAKEUP.md', 'codex': 'CODEX_WAKEUP.md'}
SECTION = {'claude_code': 'QUEUED -- Claude Code', 'codex': 'QUEUED -- Codex'}

def find_queue(root):
    for p in [os.path.join(root, 'docs', 'TASK_QUEUE.md'),
              os.path.join(root, '..', 'docs', 'TASK_QUEUE.md')]:
        if os.path.exists(p): return os.path.abspath(p)
    return None

def claim(queue_path, agent):
    with open(queue_path, encoding='utf-8') as f: lines = f.readlines()
    section, claimed, in_sec = SECTION[agent], None, False
    out = []
    for line in lines:
        if section in line:            in_sec = True
        elif line.startswith('## '):   in_sec = False
        if in_sec and not claimed and re.match(r'\s*- \[ \]', line) \
                and '[IN PROGRESS' not in line:
            claimed = line.strip()[5:].strip()
            line = line.replace('- [ ]', f'- [ ] [IN PROGRESS -- {agent}]', 1)
        out.append(line)
    if claimed:
        with open(queue_path, 'w', encoding='utf-8') as f: f.writelines(out)
    return claimed

def main():
    agent, root = 'codex', os.getcwd()
    for a in sys.argv[1:]:
        if a in ('codex', 'claude_code'): agent = a
        elif os.path.isdir(a):           root  = a

    wakeup = os.path.join(root, 'docs', WAKEUP[agent])
    if not os.path.exists(wakeup):
        print(f'[POLLER] No pending tasks for {agent}.')
        sys.exit(0)

    queue = find_queue(root)
    if not queue:
        print('[POLLER] TASK_QUEUE.md not found.'); sys.exit(0)

    task = claim(queue, agent)
    os.remove(wakeup)
    if task:
        print(f'[POLLER] CLAIMED: {task}')
        print(f'[POLLER] Marked IN PROGRESS in {queue}')
        sys.exit(2)
    print('[POLLER] Wakeup stale -- no unclaimed tasks.')
    sys.exit(0)

if __name__ == '__main__':
    main()
