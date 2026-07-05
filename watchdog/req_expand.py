#!/usr/bin/env python3
"""Requirement Expander --makes implicit requirements explicit before implementation.
Usage: python req_expand.py "[task]" --agent codex|claude_code [--mode auto|interactive] [root]
Writes: docs/REQUIREMENTS_EXPANDED.md
"""
import sys, os, subprocess
from datetime import datetime

_wd = os.path.dirname(os.path.abspath(__file__))
CLI = {'claude_code': ['claude','--dangerously-skip-permissions','-p'], 'codex': ['codex','-q']}

PROMPT = ("Task: {task}\n\nList ALL requirements before any code.\n\n"
          "## Explicit Requirements\n- [stated in task]\n\n"
          "## Implicit Requirements\n- [error handling, validation, backward compat, logging, tests]\n\n"
          "## Constraints\n- [must not break: API contracts, performance, encoding]\n\n"
          "## Definition of Done\n- [verifiable: each checkable by command or file inspection]\n")

def main():
    task, agent, mode, root = '', 'codex', None, os.getcwd()
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == '--agent' and i+1 < len(args): agent = args[i+1]
        if a == '--mode'  and i+1 < len(args): mode  = args[i+1]
        elif os.path.isdir(a): root = a
        elif not a.startswith('--') and a not in ('codex','claude_code','auto','interactive'): task = a
    if not task: print('[REQ] Usage: req_expand.py "[task]" [opts]'); sys.exit(1)
    if mode is None:
        try:
            r = subprocess.run(
                [PYTHONW_EXE, os.path.join(_wd,'enforce.py'),'mode','--check'],
                creationflags=0x08000000, capture_output=True, text=True, cwd=root, timeout=10)
            mode = 'auto' if 'auto' in r.stdout.lower() else 'interactive'
        except: mode = 'interactive'
    docs = os.path.join(root, 'docs'); os.makedirs(docs, exist_ok=True)
    out  = os.path.join(docs, 'REQUIREMENTS_EXPANDED.md')
    prompt = PROMPT.format(task=task)
    if mode == 'auto':
        cmd = CLI.get(agent, [])
        try:
            r = subprocess.run(cmd + [prompt], capture_output=True, text=True, cwd=root, timeout=120)
            content = r.stdout if r.returncode == 0 else prompt
        except Exception: content = prompt
        open(out, 'w', encoding='utf-8').write(
            f'# Requirements --{datetime.now().isoformat()}\n\n{content}')
    else:
        open(out, 'w', encoding='utf-8').write(prompt)
        print(f'[REQ] interactive --paste {out} into {agent}, save response, then proceed.')
    print(f'[REQ] wrote {out}')

if __name__ == '__main__':
    main()

