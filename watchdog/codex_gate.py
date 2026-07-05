"""
Codex Gate -- Pre/post file-edit enforcement for Codex agent.
Codex has no settings.json hook system, so this script serves as the
mechanical gate that Codex AGENTS.MD instructs it to call.

Usage (from Codex AGENTS.md):
  pre-edit:  python codex_gate.py pre  <filepath>
  post-edit: python codex_gate.py post <filepath>
"""
import subprocess, sys, os, json, hashlib
from datetime import datetime

from paths import PYTHON_EXE as PYTHON
WD = os.path.dirname(os.path.abspath(__file__))
LOCK_DIR = os.path.join(WD, "locks")
ENFORCE = os.path.join(WD, "enforce.py")
GATE = os.path.join(WD, "deepseek_gate.py")
AUDIT = os.path.join(WD, "self_audit.py")
VERIFY = os.path.join(WD, "verify_task.py")
QUALITY = os.path.join(WD, "code_quality_gate.py")
DELEGATION = os.path.join(WD, "delegation_check.py")
HALLUCINATION = os.path.join(WD, "hallucination_check.py")
HALCHECK_LIVE = os.path.join(WD, "halcheck_live.py")
SELF_REVIEW = os.path.join(WD, "self_review_injector.py")
CONTRACT = os.path.join(WD, "contract_check.py")

def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=True)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return 1, "", str(e)

def pre_gate(filepath):
    """Audit + CLARIFY gate + backup + spiral + locks before Codex writes a file."""
    print(f"[CODEX PRE-GATE] {filepath} @ {datetime.now().isoformat()}")
    results = {}

    # 0. Codex session lock -- proves Codex is alive (for dead agent detection)
    session_lock = os.path.join(LOCK_DIR, 'codex_session_active.lock')
    with open(session_lock, 'w', encoding='utf-8') as f:
        json.dump({'time': datetime.now().isoformat(), 'agent': 'codex'}, f)

    # 1. Gate marker lock -- mechanical proof that Codex called pre_gate
    os.makedirs(LOCK_DIR, exist_ok=True)
    marker_path = os.path.join(LOCK_DIR, f'codex_gate_{hashlib.md5(filepath.encode()).hexdigest()[:12]}.lock')
    if os.path.exists(marker_path):
        try:
            with open(marker_path, 'r', encoding='utf-8') as f:
                old_marker = json.load(f)
            old_time = datetime.fromisoformat(old_marker.get('time', '2000-01-01'))
            age_sec = (datetime.now() - old_time).total_seconds()
            if age_sec < 300:
                print(f"[CODEX PRE-GATE] WARNING: stale marker for {os.path.basename(filepath)} ({age_sec:.0f}s old). Possible missing post gate.")
        except Exception:
            pass
    with open(marker_path, 'w', encoding='utf-8') as f:
        json.dump({'file': filepath, 'time': datetime.now().isoformat(), 'action': 'pre'}, f)

    # 1. H3 Self-Audit Q1-Q5
    rc, _, _ = run(f'"{PYTHON}" "{AUDIT}"')
    results['audit'] = 'PASS' if rc == 0 else f'FAIL (rc={rc})'

    # 1. CLARIFY gate
    rc, out, err = run(f'"{PYTHON}" "{GATE}" "Codex editing {os.path.basename(filepath)}" watchdog/')
    results['gate'] = 'PASS' if rc == 0 else f'CLARIFY (rc={rc})'

    # 2. Backup
    rc, _, _ = run(f'"{PYTHON}" "{ENFORCE}" backup --target "{filepath}"')
    results['backup'] = 'OK' if rc == 0 else 'FAIL'

    # 3. Spiral
    rc, _, _ = run(f'"{PYTHON}" "{ENFORCE}" spiral --touch "{filepath}"')
    results['spiral'] = 'OK' if rc == 0 else 'FAIL'

    # 4. Locks cleanup
    run(f'"{PYTHON}" "{ENFORCE}" locks --expire')

    return results

def post_gate(filepath):
    """Verify + quality + delegation + fuse after Codex writes a .py file."""
    if not filepath.endswith('.py'):
        return {'skipped': 'not .py'}
    print(f"[CODEX POST-GATE] {filepath} @ {datetime.now().isoformat()}")
    results = {}

    # 1. verify_task (includes import resolution + hallucination pass now)
    rc, out, err = run(f'"{PYTHON}" "{VERIFY}" "{filepath}"', timeout=60)
    results['verify'] = 'PASS' if rc == 0 else f'FAIL: {err[:100]}'

    # 1b. Dedicated hallucination check
    if os.path.exists(HALLUCINATION):
        rc, out, _ = run(f'"{PYTHON}" "{HALLUCINATION}" "{filepath}"', timeout=30)
        if rc == 0:
            results['hallucination'] = 'PASS'
        else:
            try:
                issues = json.loads(out).get('issues', [])
                results['hallucination'] = f'WARN: {issues[:3]}'
            except Exception:
                results['hallucination'] = 'WARN: parse error'

    # 1c. Live hallucination check (import-based, deeper verification)
    if os.path.exists(HALCHECK_LIVE):
        rc, out, _ = run(f'"{PYTHON}" "{HALCHECK_LIVE}" "{filepath}"', timeout=30)
        if rc == 0:
            results['halcheck_live'] = 'PASS'
        else:
            try:
                hs = json.loads(out).get('hallucinations', [])
                results['halcheck_live'] = f'FAIL: {[h.get("chain") for h in hs[:3]]}'
            except Exception:
                results['halcheck_live'] = 'FAIL: parse error'

    # 2. code_quality_gate
    proj_root = os.path.dirname(filepath)
    rc, _, _ = run(f'"{PYTHON}" "{QUALITY}" --scope "{proj_root}"', timeout=45)
    results['quality'] = 'PASS' if rc == 0 else 'WARN'

    # 3. delegation_check
    rc, _, _ = run(f'"{PYTHON}" "{DELEGATION}" --agent codex "{proj_root}"', timeout=15)
    results['delegation'] = 'cross-domain-queued' if rc == 2 else 'ok'

    # 3b. API contract check -- Codex modifies backend, check frontend calls match
    if os.path.exists(CONTRACT):
        rc, out, _ = run(f'"{PYTHON}" "{CONTRACT}" --agent codex "{proj_root}"', timeout=15)
        if rc != 0:
            results['contract'] = 'FAIL'
            try:
                r = json.loads(out)
                results['contract_issues'] = [i.get('message', '') for i in r.get('issues', [])]
            except Exception:
                results['contract_issues'] = ['parse error']
        else:
            results['contract'] = 'PASS'

    # 4. fuse graduated
    rc, out, _ = run(f'"{PYTHON}" "{ENFORCE}" fuse --graduated')
    if rc == 0 and out:
        try:
            pct = json.loads(out).get('pct', 0)
            results['fuse'] = f'{pct}%'
            if pct >= 95:
                print(f"[CODEX POST-GATE] FUSE CRITICAL: {pct}%")
        except Exception:
            results['fuse'] = 'unknown'

    # 5. fuse --actual (sqlite token count)
    rc, out, _ = run(f'"{PYTHON}" "{ENFORCE}" fuse --actual')
    if rc == 0 and out:
        try:
            r = json.loads(out)
            total = sum(t.get("tokens_used", 0) for t in r.get("threads", []))
            if total > 0:
                results['fuse_actual'] = total
        except Exception:
            pass

    # 6. Auto-track tokens into shared pool
    rc, out, _ = run(f'"{PYTHON}" "{ENFORCE}" fuse --auto-track codex')
    if rc == 0 and out:
        try:
            r = json.loads(out)
            pool_used = r.get('pct_used', 0)
            if pool_used > 0:
                results['pool_pct'] = round(pool_used, 1)
        except Exception:
            pass

    # 7. Self-review injection (Opus-4.8 compensation)
    if os.path.exists(SELF_REVIEW):
        run(f'"{PYTHON}" "{SELF_REVIEW}" "{filepath}" --agent codex', timeout=15)

    return results

def main():
    if len(sys.argv) < 3:
        print("Usage: codex_gate.py pre|post <filepath>")
        sys.exit(1)

    action = sys.argv[1]
    filepath = sys.argv[2]

    if not os.path.exists(filepath) and action == 'post':
        print(f"[CODEX GATE] File not found: {filepath}")
        sys.exit(0)

    if action == 'pre':
        results = pre_gate(filepath)
    elif action == 'post':
        results = post_gate(filepath)
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

    print(json.dumps(results, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
