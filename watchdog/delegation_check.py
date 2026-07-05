#!/usr/bin/env python3
"""Delegation Check -- scans SCOPE_active.md for cross-domain work and auto-queues it.
Usage: python delegation_check.py --agent codex|claude_code [project_root]
Returns: 0=no delegation needed, 2=delegated (check TASK_QUEUE.md), 1=error
Must be called before verify --check PASS.
"""
import sys, os, re
from datetime import datetime

CODEX_PATTERNS   = ('.py', 'backend/', 'api/', '.db', '.toml', 'config', 'watchdog/')
CC_PATTERNS      = ('.html', '.css', '.js', '.ts', 'static/', 'frontend/', '.vue', '.jsx')

def classify(path):
    p = path.replace('\\', '/').lower()
    if any(x in p for x in CC_PATTERNS):   return 'claude_code'
    if any(p.endswith(x) or x in p for x in CODEX_PATTERNS): return 'codex'
    return None

def read_scope(root):
    scope = os.path.join(root, 'docs', 'SCOPE_active.md')
    if not os.path.exists(scope):
        return None, []
    text = open(scope, encoding='utf-8').read()
    task_m = re.search(r'Task:\s*(.+)', text)
    files  = re.findall(r'[-•]\s*(.+)', text.split('Will write', 1)[-1].split('Done when')[0]) \
             if 'Will write' in text else []
    return (task_m.group(1).strip() if task_m else 'unknown task'), [f.strip() for f in files if f.strip()]

def append_queue(root, task, files, target_agent):
    q = os.path.join(root, 'docs', 'TASK_QUEUE.md')
    header = f'\n## QUEUED -- {"Claude Code" if target_agent == "claude_code" else "Codex"}\n'
    entry  = f'- [ ] [AUTO-DELEGATED from {task}] Handle: {", ".join(files)}\n'
    os.makedirs(os.path.dirname(q), exist_ok=True)
    if os.path.exists(q):
        content = open(q, encoding='utf-8').read()
        section = "## QUEUED -- Claude Code" if target_agent == "claude_code" else "## QUEUED -- Codex"
        if section in content:
            content = content.replace(section, section + '\n' + entry.rstrip(), 1)
        else:
            content += header + entry
        open(q, 'w', encoding='utf-8').write(content)
    else:
        open(q, 'w', encoding='utf-8').write(
            f'# TASK QUEUE -- Updated {datetime.now().isoformat()}\n{header}{entry}')

def main():
    agent = 'codex'
    root  = os.getcwd()
    for a in sys.argv[1:]:
        if a in ('codex', 'claude_code'): agent = a
        elif os.path.isdir(a):            root  = a

    task, files = read_scope(root)
    if task is None:
        print('[DELEG] No SCOPE_active.md -- skip.')
        sys.exit(0)

    other = 'claude_code' if agent == 'codex' else 'codex'
    cross = [f for f in files if classify(f) == other]

    if not cross:
        print(f'[DELEG] No cross-domain work detected. OK.')
        sys.exit(0)

    append_queue(root, task, cross, other)
    print(f'[DELEG] Delegated {len(cross)} file(s) to {other}: {cross}')
    print(f'[DELEG] Written to docs/TASK_QUEUE.md')
    sys.exit(2)

if __name__ == '__main__':
    main()
