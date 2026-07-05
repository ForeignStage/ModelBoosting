#!/usr/bin/env python3
"""Multi-Pass Reasoning --solve ->critique ->revise cycle.
Simulates Opus extended thinking via 3 sequential agent calls.
Auto mode: 3 CLI invocations. Interactive mode: single enriched prompt.

Usage: python multi_pass_reason.py "[task]" --agent codex|claude_code [--mode auto|interactive] [root]
Writes: docs/MULTI_PASS_SOLUTION.md
"""
import sys, os, subprocess
from datetime import datetime

_wd = os.path.dirname(os.path.abspath(__file__))
_sk = os.path.join(_wd, '..', 'skills', 'SKILL_DEEPSEEK_DISCIPLINE.md')
CLI = {'claude_code': ['claude','--dangerously-skip-permissions','-p'],
       'codex':       ['codex', '-q']}

def invoke(agent, prompt, root):
    cmd = CLI.get(agent, [])
    if not cmd: return None
    try:
        r = subprocess.run(cmd + [prompt], capture_output=True, text=True, cwd=root, timeout=300)
        return r.stdout if r.returncode == 0 else None
    except Exception: return None

def auto_three_pass(task, agent, root):
    """3 independent CLI calls: solve ->critique ->revise."""
    p1 = f"TASK: {task}\n\nPASS 1 --SOLVE: Produce a complete solution. Be thorough."
    sol = invoke(agent, p1, root)
    if not sol: return None, "Pass 1 failed"

    p2 = (f"TASK: {task}\n\nSOLUTION TO REVIEW:\n{sol}\n\n"
          f"PASS 2 --CRITIQUE: List every flaw, missing edge case, and improvement. Be harsh.")
    crit = invoke(agent, p2, root) or "(no critique)"

    p3 = (f"TASK: {task}\n\nORIGINAL SOLUTION:\n{sol}\n\n"
          f"CRITIQUE:\n{crit}\n\n"
          f"PASS 3 --REVISE: Produce the final, corrected solution addressing all critique points.")
    final = invoke(agent, p3, root)
    return final, None

def interactive_prompt(task):
    """Single enriched prompt that forces 3-pass reasoning in one invocation."""
    skill = open(_sk, encoding='utf-8').read() if os.path.exists(_sk) else ''
    return (
        f"{skill}\n\n"
        f"## TASK\n{task}\n\n"
        f"## MANDATORY 3-PASS REASONING (do not skip any pass)\n\n"
        f"### PASS 1 --SOLVE\nProduce a complete solution. Think through all requirements.\n\n"
        f"### PASS 2 --CRITIQUE\nCritique your own solution above. List every flaw, "
        f"missing edge case, incorrect assumption, and suboptimal choice.\n\n"
        f"### PASS 3 --REVISE\nProduce the final corrected solution that addresses all "
        f"critique points from Pass 2. This is what gets implemented."
    )

def main():
    agent, mode, root, task = 'codex', None, os.getcwd(), None
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == '--agent' and i+1 < len(args):  agent = args[i+1]
        if a == '--mode'  and i+1 < len(args):  mode  = args[i+1]
        elif os.path.isdir(a):                  root  = a
        elif not a.startswith('--') and a not in ('codex','claude_code','auto','interactive'):
            task = a

    if not task: print('[MPR] Usage: multi_pass_reason.py "[task]" [opts]'); sys.exit(1)

    if mode is None:
        try:
            r = subprocess.run(
                [PYTHONW_EXE, os.path.join(_wd,'enforce.py'),'mode','--check'],
                creationflags=0x08000000, capture_output=True, text=True, cwd=root, timeout=10)
            mode = 'auto' if 'auto' in r.stdout.lower() else 'interactive'
        except: mode = 'interactive'

    docs = os.path.join(root, 'docs'); os.makedirs(docs, exist_ok=True)
    out_file = os.path.join(docs, 'MULTI_PASS_SOLUTION.md')

    if mode == 'auto':
        print(f'[MPR] auto --3-pass for: {task[:60]}')
        final, err = auto_three_pass(task, agent, root)
        if err: print(f'[MPR] FAILED: {err}'); sys.exit(1)
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(f'# Multi-Pass Solution --{datetime.now().isoformat()}\n\n{final}')
    else:
        prompt = interactive_prompt(task)
        with open(out_file, 'w', encoding='utf-8') as f: f.write(prompt)
        print(f'[MPR] interactive --paste {out_file} into {agent} session.')

    print(f'[MPR] Output: {out_file}')

if __name__ == '__main__':
    main()

