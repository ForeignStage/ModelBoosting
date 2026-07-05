#!/usr/bin/env python3
"""Auto Mode Executor --full autonomous task cycle.
Auto:        poll ->pre-enhance ->invoke CLI ->apply writes ->verify ->delegate
Interactive: write TASK_PROMPT_*.md ->exit (user pastes into agent)
Fuse blown = ONLY permitted stop.
"""
import sys, os, re, subprocess
from datetime import datetime
from paths import PYTHONW_EXE, safe_print

_wd = os.path.dirname(os.path.abspath(__file__))
_sk = os.path.join(_wd, '..', 'skills', 'SKILL_DEEPSEEK_DISCIPLINE.md')
SECTION = {'claude_code': 'QUEUED --Claude Code', 'codex': 'QUEUED --Codex'}
CLI     = {'claude_code': ['claude', '--dangerously-skip-permissions', '-p'],
           'codex':       ['codex', '-q']}

def find_queue(root):
    for p in [os.path.join(root,'docs','TASK_QUEUE.md'),
              os.path.join(root,'..','docs','TASK_QUEUE.md')]:
        if os.path.exists(p): return os.path.abspath(p)
    return None

def fuse_ok(root):
    try:
        r = subprocess.run(
            [PYTHONW_EXE, os.path.join(_wd,'enforce.py'),'fuse','--check'],
            creationflags=0x08000000, capture_output=True, text=True, cwd=root, timeout=10)
        return 'blown' not in r.stdout.lower()
    except: return True

def current_mode(root):
    try:
        r = subprocess.run(
            [PYTHONW_EXE, os.path.join(_wd,'enforce.py'),'mode','--check'],
            creationflags=0x08000000, capture_output=True, text=True, cwd=root, timeout=10)
        return 'auto' if 'auto' in r.stdout.lower() else 'interactive'
    except: return 'interactive'

def next_task(queue, agent):
    with open(queue, encoding='utf-8') as f: lines = f.readlines()
    in_sec = False
    for i, ln in enumerate(lines):
        if SECTION[agent] in ln:   in_sec = True
        elif ln.startswith('## '): in_sec = False
        if in_sec and re.match(r'\s*- \[ \]', ln) and '[IN PROGRESS' not in ln:
            return ln.strip()[5:].strip(), i
    return None, None

def claim(queue, idx, agent):
    with open(queue, encoding='utf-8') as f: lines = f.readlines()
    lines[idx] = lines[idx].replace('- [ ]', f'- [ ] [IN PROGRESS --{agent}]', 1)
    with open(queue, 'w', encoding='utf-8') as f: f.writelines(lines)

def mark_done(queue, task, agent):
    with open(queue, encoding='utf-8') as f: c = f.read()
    c = re.sub(r'- \[ \] \[IN PROGRESS --' + re.escape(agent) + r'\] ' + re.escape(task) + r'[^\n]*',
               f'- [x] {task}  <!-- done {datetime.now().isoformat()} -->', c)
    with open(queue, 'w', encoding='utf-8') as f: f.write(c)

def _pre(script, args, root):
    try: subprocess.run([
            PYTHONW_EXE, os.path.join(_wd, script)] + args,
                        cwd=root, creationflags=0x08000000, capture_output=True, timeout=60)
    except Exception: pass

def _doc(root, name):
    p = os.path.join(root, 'docs', name)
    return open(p, encoding='utf-8').read() if os.path.exists(p) else ''

def parse_and_apply(output, root):
    written = []
    for m in re.finditer(r'```[a-zA-Z]*(?::([^\n]+))?\n(?:#\s*([^\n]+)\n)?(.*?)```',
                         output, re.DOTALL):
        path = (m.group(1) or m.group(2) or '').strip()
        code = m.group(3)
        if not path or not any(path.endswith(e) for e in
                               ('.py','.js','.ts','.html','.css','.json','.md','.txt')): continue
        full = path if os.path.isabs(path) else os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w', encoding='utf-8') as f: f.write(code)
        written.append(full)
    if written: print(f'[EXECUTOR] Wrote {len(written)} file(s) from output')
    return written

def build_prompt(task, agent, root):
    skill = open(_sk, encoding='utf-8').read() if os.path.exists(_sk) else ''
    _pre('req_expand.py',       [task, '--agent', agent, '--mode', 'auto', root], root)
    _pre('context_injector.py', [task, root], root)
    reqs = _doc(root, 'REQUIREMENTS_EXPANDED.md')
    ctx  = _doc(root, 'CONTEXT_INJECTION.md')
    parts = [f"[AUTO-EXECUTOR] agent={agent} ts={datetime.now().isoformat()}\n\n",
             f"## TASK\n{task}\n\n",
             "## MANDATORY\n1. deepseek_gate.py  2. SCOPE_active.md  "
             "3. Execute ->code_quality_gate ->verify ->delegation_check\n\n"]
    if reqs: parts.append(f"## REQUIREMENTS\n{reqs[:2000]}\n\n")
    if ctx:  parts.append(f"## REFERENCE CODE\n{ctx[:3000]}\n\n")
    parts.append(f"## DISCIPLINE SKILL\n{skill}")
    return ''.join(parts)

def write_prompt(root, agent, content):
    docs = os.path.join(root, 'docs'); os.makedirs(docs, exist_ok=True)
    p = os.path.join(docs, f'TASK_PROMPT_{agent.upper()}.md')
    with open(p, 'w', encoding='utf-8') as f: f.write(content)
    return p

def pre_gate(root, agent):
    """Mechanical pre-execution gate. Auto-fixes, only hard-stops on fuse blown.
    Returns (proceed: bool, reason: str)"""
    enforce = os.path.join(_wd, 'enforce.py')

    # 1. Boot check + auto-renew
    try:
        r = subprocess.run([
            PYTHONW_EXE, enforce, 'boot', '--check'],
                           creationflags=0x08000000, capture_output=True, text=True, cwd=root, timeout=10)
        out = r.stdout.lower()
        if 'expired' in out or 'missing' in out:
            print(f'[EXECUTOR] Boot expired/missing, auto-renewing...', flush=True)
            subprocess.run([
            PYTHONW_EXE, enforce, 'boot', '--renew'],
                          creationflags=0x08000000, capture_output=True, cwd=root, timeout=10)
    except Exception as e:
        print(f'[EXECUTOR] Boot check failed: {e}', flush=True)

    # 2. Lock cleanup
    try:
        subprocess.run([
            PYTHONW_EXE, enforce, 'locks', '--expire'],
                       creationflags=0x08000000, capture_output=True, cwd=root, timeout=10)
    except:
        pass

    # 3. Integrity check + auto-restore
    try:
        r = subprocess.run([
            PYTHONW_EXE, enforce, 'integrity', '--check'],
                           creationflags=0x08000000, capture_output=True, text=True, cwd=root, timeout=10)
        if 'corrupt' in r.stdout.lower() or 'mismatch' in r.stdout.lower():
            print(f'[EXECUTOR] Integrity mismatch, restoring from backup...', flush=True)
            backup_dir = os.path.join(root, 'backups')
            if os.path.exists(backup_dir):
                backups = sorted([f for f in os.listdir(backup_dir) if f.startswith('AGENTS.md.bak')],
                                reverse=True)
                if backups:
                    import shutil
                    src = os.path.join(backup_dir, backups[0])
                    dst = os.path.join(root, 'AGENTS.md')
                    shutil.copy2(src, dst)
                    print(f'[EXECUTOR] Restored AGENTS.md from {backups[0]}', flush=True)
    except:
        pass

    # 4. Fuse check (HARD STOP ONLY HERE)
    try:
        r = subprocess.run([
            PYTHONW_EXE, enforce, 'fuse', '--check'],
                           creationflags=0x08000000, capture_output=True, text=True, cwd=root, timeout=10)
        if 'blown' in r.stdout.lower():
            return False, 'FUSE BLOWN'
    except:
        pass

    # 5. Spiral check for files in scope
    try:
        scope_path = os.path.join(root, 'docs', 'SCOPE_active.md')
        if os.path.exists(scope_path):
            with open(scope_path, encoding='utf-8') as f:
                scope = f.read()
            will_write_match = re.search(r'Will write:\s*\[(.+?)\]', scope, re.DOTALL)
            if will_write_match:
                files = [f.strip() for f in will_write_match.group(1).split(',') if f.strip()]
                for fpath in files:
                    full = fpath if os.path.isabs(fpath) else os.path.join(root, fpath)
                    if os.path.exists(full):
                        r = subprocess.run([
            PYTHONW_EXE, enforce, 'spiral', '--check', full],
                                          creationflags=0x08000000, capture_output=True, text=True, cwd=root, timeout=10)
                        if 'blocked' in r.stdout.lower():
                            print(f'[EXECUTOR] SPIRAL BLOCKED: {fpath}, re-queuing task', flush=True)
                            return False, f'SPIRAL BLOCKED: {fpath}'
    except:
        pass

    return True, 'GO'

def auto_backup_files(root):
    """Pre-edit backup: backup all files listed in SCOPE_active.md Will-write section."""
    enforce = os.path.join(_wd, 'enforce.py')
    scope_path = os.path.join(root, 'docs', 'SCOPE_active.md')
    if not os.path.exists(scope_path):
        return
    try:
        with open(scope_path, encoding='utf-8') as f:
            scope = f.read()
        will_write_match = re.search(r'Will write:\s*\[(.+?)\]', scope, re.DOTALL)
        if will_write_match:
            files = [f.strip() for f in will_write_match.group(1).split(',') if f.strip()]
            for fpath in files:
                full = fpath if os.path.isabs(fpath) else os.path.join(root, fpath)
                if os.path.exists(full) and os.path.getsize(full) > 0:
                    subprocess.run([
            PYTHONW_EXE, enforce, 'backup', '--target', full],
                                  creationflags=0x08000000, capture_output=True, cwd=root, timeout=15)
                    print(f'[EXECUTOR] Backed up: {os.path.basename(fpath)}', flush=True)
    except Exception as e:
        print(f'[EXECUTOR] Backup warning: {e}', flush=True)

def post_gate(root, agent):
    """Post-execution verification gate. Runs verify_task.py on changed files.
    Returns (passed: bool, details: str)"""
    enforce = os.path.join(_wd, 'enforce.py')
    verify_script = os.path.join(_wd, 'verify_task.py')
    scope_path = os.path.join(root, 'docs', 'SCOPE_active.md')
    changed_files = []

    if os.path.exists(scope_path):
        try:
            with open(scope_path, encoding='utf-8') as f:
                scope = f.read()
            will_write_match = re.search(r'Will write:\s*\[(.+?)\]', scope, re.DOTALL)
            if will_write_match:
                files = [f.strip() for f in will_write_match.group(1).split(',') if f.strip()]
                changed_files = [f if os.path.isabs(f) else os.path.join(root, f)
                               for f in files if os.path.exists(f if os.path.isabs(f) else os.path.join(root, f))]
        except:
            pass

    py_files = [f for f in changed_files if f.endswith('.py')]
    if py_files and os.path.exists(verify_script):
        try:
            r = subprocess.run([
            PYTHONW_EXE, verify_script] + py_files,
                              creationflags=0x08000000, capture_output=True, text=True, cwd=root, timeout=60)
            passed = 'PASS' in r.stdout[:50]
            if not passed:
                return False, f'VERIFY FAILED:\n{r.stdout[:500]}'
        except Exception as e:
            return False, f'VERIFY ERROR: {e}'

    # Also run enforce.py verify --check
    try:
        r = subprocess.run([
            PYTHONW_EXE, enforce, 'verify', '--check'],
                          creationflags=0x08000000, capture_output=True, text=True, cwd=root, timeout=10)
        if 'fail' in r.stdout.lower() or 'stale' in r.stdout.lower():
            return False, f'VERIFY --check failed'
    except:
        pass

    return True, 'ALL PASSED'


def run_agent(agent, prompt, root):
    cmd = CLI.get(agent)
    if not cmd: return False, 'unknown agent'
    try:
        r = subprocess.run(cmd + [prompt], capture_output=True, text=True, cwd=root, timeout=300)
        return r.returncode == 0, r.stdout[-2000:] + r.stderr[-500:]
    except FileNotFoundError: return False, f'{cmd[0]} not in PATH'
    except subprocess.TimeoutExpired: return False, 'TIMEOUT 300s'

def post_task(agent, root):
    for cmd in [
        [PYTHONW_EXE, os.path.join(_wd,'code_quality_gate.py'), '--scope', root],
        [PYTHONW_EXE, os.path.join(_wd,'delegation_check.py'), '--agent', agent, root],
        [PYTHONW_EXE, os.path.join(_wd,'enforce.py'), 'heartbeat', '--touch'],
    ]:
        subprocess.run(cmd, cwd=root, capture_output=True, timeout=30)

def log_fail(root, agent, task, out):
    docs = os.path.join(root, 'docs'); os.makedirs(docs, exist_ok=True)
    with open(os.path.join(docs,'EXECUTOR_FAIL.log'),'a',encoding='utf-8') as f:
        f.write(f"[{datetime.now().isoformat()}] {agent}: {task}\n{out[:500]}\n---\n")

def main():
    agent, mode, root = 'codex', None, os.getcwd()
    for a in sys.argv[1:]:
        if a in ('codex','claude_code'):  agent = a
        elif a in ('auto','interactive'): mode  = a
        elif os.path.isdir(a):           root  = a
    if mode is None: mode = current_mode(root)

    if not fuse_ok(root):
        print('[EXECUTOR] FUSE BLOWN --only permitted stop.'); sys.exit(3)

    queue = find_queue(root)
    if not queue: print('[EXECUTOR] No TASK_QUEUE.md'); sys.exit(0)

    task, idx = next_task(queue, agent)
    if task is None: print(f'[EXECUTOR] No tasks for {agent}.'); sys.exit(0)

    print(f'[EXECUTOR] mode={mode} | {agent} | {task[:70]}')
    claim(queue, idx, agent)
    prompt = build_prompt(task, agent, root)
    pfile  = write_prompt(root, agent, prompt)

    if mode == 'interactive':
        print(f'[EXECUTOR] Prompt: {pfile}')
        print(f'[EXECUTOR] Paste into {agent} session to execute.')
        sys.exit(2)

    # === GATE 1: Pre-execution check-all ===
    proceed, reason = pre_gate(root, agent)
    if not proceed:
        print(f'[EXECUTOR] PRE-GATE STOP: {reason}')
        if 'FUSE' in reason:
            sys.exit(3)
        if 'SPIRAL' in reason:
            mark_done(queue, task, agent)
            log_fail(root, agent, task, reason)
            sys.exit(0)
        # Unknown block, re-queue and exit
        sys.exit(0)

    # === GATE 2: Auto-backup target files ===
    auto_backup_files(root)

    # === Invoke LLM ===
    ok, out = run_agent(agent, prompt, root)
    if not ok:
        print('[EXECUTOR] Attempt 1 failed --self-correcting...')
        ok, out = run_agent(agent, prompt + f'\n\n## PREVIOUS FAILURE\n{out[:600]}\nFix.', root)

    if ok:
        written = parse_and_apply(out, root)

        # === GATE 3: Post-execution verification ===
        v_ok, v_detail = post_gate(root, agent)
        if v_ok:
            mark_done(queue, task, agent)
            post_task(agent, root)
            print(f'[EXECUTOR] COMPLETED: {task[:70]}')
        else:
            print(f'[EXECUTOR] VERIFY FAILED: {v_detail[:200]}')
            log_fail(root, agent, task, v_detail)
            # Re-queue with [NEEDS-VERIFY] prefix for next attempt
            with open(queue, encoding='utf-8') as f:
                qlines = f.readlines()
            for i, ln in enumerate(qlines):
                if task in ln and '[IN PROGRESS' in ln:
                    qlines[i] = ln.replace('[IN PROGRESS --' + agent + '] ',
                                          '[IN PROGRESS --' + agent + '] [VERIFY_FAILED] ')
            with open(queue, 'w', encoding='utf-8') as f:
                f.writelines(qlines)
            print(f'[EXECUTOR] Task re-queued with [VERIFY_FAILED]')
            sys.exit(0)
    else:
        log_fail(root, agent, task, out)
        print('[EXECUTOR] FAILED. See docs/EXECUTOR_FAIL.log')
        sys.exit(1)

if __name__ == '__main__':
    main()

