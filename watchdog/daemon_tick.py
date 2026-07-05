"""
Constitution Daemon Tick -- runs every 5 minutes via Windows Task Scheduler.
Independent of any agent session. Survives reboots.
Actions: heartbeat, locks-expire, fuse-actual, EMERGENCY_STOP, REANCHOR, codex enforcer, dead agent.
"""
import subprocess, sys, os, json
from datetime import datetime

from paths import PYTHONW_EXE as PYTHON
ENFORCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enforce.py")
FS_WATCHER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fs_watcher.py")
CODEX_ENFORCER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "codex_enforcer_daemon.py")
DEAD_DETECTOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dead_agent_detector.py")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daemon_tick.log")
MAX_LOG_LINES = 300

def log(msg):
    ts = datetime.now().isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        lines = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, encoding='utf-8') as f:
                lines = f.readlines()
        lines.append(line + "\n")
        if len(lines) > MAX_LOG_LINES:
            lines = lines[-MAX_LOG_LINES:]
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    except Exception:
        pass

def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=True,
                           creationflags=0x08000000)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return 1, "", str(e)

def find_projects():
    projects_root = r"E:\AgentHub\AgentProjects"
    projects = []
    if os.path.isdir(projects_root):
        for name in os.listdir(projects_root):
            proj_path = os.path.join(projects_root, name)
            if os.path.isdir(proj_path):
                enf = os.path.join(proj_path, "watchdog", "enforce.py")
                if os.path.exists(enf):
                    projects.append(proj_path)
    return projects

def main():
    log("--- TICK START ---")

    # 1. Heartbeat
    code, out, err = run(f'"{PYTHON}" "{ENFORCE}" heartbeat --touch')
    log(f"heartbeat {'OK' if code==0 else 'FAIL: '+err[:80]}")

    # 2. Locks cleanup
    code, out, err = run(f'"{PYTHON}" "{ENFORCE}" locks --expire')
    try:
        r = json.loads(out)
        if r.get("expired", 0) > 0:
            log(f"locks: {r['expired']} expired cleaned")
    except Exception:
        pass

    # 3. Fuse -- read ACTUAL tokens from sqlite, write graduated status
    code, out, err = run(f'"{PYTHON}" "{ENFORCE}" fuse --actual')
    if code == 0 and out:
        try:
            r = json.loads(out)
            total = sum(t.get("tokens_used", 0) for t in r.get("threads", []))
            if total > 0:
                log(f"fuse-actual: {total} tokens (sqlite)")
        except Exception:
            pass

    # 4. Dead agent detection + fuse graduated per project
    for proj in find_projects():
        enf = os.path.join(proj, "watchdog", "enforce.py")
        if not os.path.exists(enf):
            continue

        # 4a. Dead agent detection
        if os.path.exists(DEAD_DETECTOR):
            code, out, err = run(f'"{PYTHON}" "{DEAD_DETECTOR}" "{proj}"', timeout=20)
            if code == 2 and out:
                try:
                    r = json.loads(out)
                    detections = r.get('detections', [])
                    recoveries = r.get('recoveries', [])
                    if detections:
                        for d in detections:
                            log(f"DEAD AGENT: {d}")
                    if recoveries:
                        log(f"RECOVERED: {len(recoveries)} task(s) from dead agent")
                except Exception:
                    pass

        # 4b. Fuse graduated
        code, out, err = run(f'"{PYTHON}" "{enf}" fuse --graduated')
        if code == 0 and out:
            try:
                r = json.loads(out)
                pct = r.get("pct", 0)
                if pct >= 95:
                    emergency = os.path.join(proj, "docs", "EMERGENCY_STOP")
                    os.makedirs(os.path.dirname(emergency), exist_ok=True)
                    if not os.path.exists(emergency):
                        with open(emergency, 'w', encoding='utf-8') as f:
                            f.write(f"FUSE BLOWN ({pct}%) at {datetime.now().isoformat()}\n")
                        log(f"FUSE CRITICAL {pct}%: EMERGENCY_STOP -> {proj}")
            except Exception:
                pass

    # 5. REANCHOR check -- log only. Mechanical blocking happens in enforce.py check_all()
    try:
        log_path = os.path.join(os.path.dirname(ENFORCE), "action_log.json")
        if os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8') as f:
                actions = json.load(f)
            if isinstance(actions, list):
                since_anchor = 0
                for a in reversed(actions):
                    if isinstance(a, dict) and a.get("action") == "reanchor":
                        break
                    since_anchor += 1
                if since_anchor >= 10:
                    log(f"REANCHOR WARNING: {since_anchor} actions since last reanchor")
    except Exception:
        pass

    # 6. Codex enforcer -- mechanical gate marker scan + SCOPE EMERGENCY_STOP
    for proj in find_projects():
        # 6a. Codex gate enforcement
        if os.path.exists(CODEX_ENFORCER):
            code, out, err = run(f'"{PYTHON}" "{CODEX_ENFORCER}" "{proj}"', timeout=20)
            if code == 2:
                try:
                    r = json.loads(out)
                    log(f"CODEX ENFORCER STOP: {len(r.get('violations',[]))} violations in {proj}")
                except Exception:
                    log(f"CODEX ENFORCER STOP (rc=2)")

        # 6b. SCOPE check -- graduated: 1=log, 3+=EMERGENCY_STOP
        scope_path = os.path.join(proj, "docs", "SCOPE_active.md")
        if os.path.exists(scope_path):
            continue
        violation_count = 0
        for scan_dir in ['backend', 'api']:
            scan_path = os.path.join(proj, scan_dir)
            if not os.path.isdir(scan_path):
                continue
            try:
                for root, _, files in os.walk(scan_path):
                    if any(skip in root for skip in ['__pycache__', '.git', 'venv', '.venv']):
                        continue
                    for fn in files:
                        if not fn.endswith('.py'):
                            continue
                        fp = os.path.join(root, fn)
                        try:
                            mtime = os.path.getmtime(fp)
                        except OSError:
                            continue
                        age_min = (datetime.now().timestamp() - mtime) / 60
                        if age_min < 10:
                            violation_count += 1
                            if violation_count == 1:
                                log(f"SCOPE VIOLATION: {fp} ({age_min:.0f}m ago, no SCOPE_active.md)")
            except Exception:
                pass

        if violation_count >= 5:  # raised from 3 -- single project often has 3+ .py files naturally
            emergency = os.path.join(proj, "docs", "EMERGENCY_STOP")
            os.makedirs(os.path.dirname(emergency), exist_ok=True)
            with open(emergency, 'w', encoding='utf-8') as f:
                f.write(f"SCOPE VIOLATION: {violation_count} .py files modified without SCOPE_active.md\n")
                f.write(f"Time: {datetime.now().isoformat()}\n")
                f.write("Declare scope in docs/SCOPE_active.md before editing.\n")
            log(f"SCOPE EMERGENCY_STOP: {violation_count} violations in {proj}")

    # 7. Heartbeat staleness
    code, out, err = run(f'"{PYTHON}" "{ENFORCE}" heartbeat --check')
    if "stale" in (out + err).lower():
        log("STALE: heartbeat > 60min")

    # 8. HANDOFF cross-verification -- auto-diff new HANDOFFs
    diff_script = os.path.join(os.path.dirname(ENFORCE), "diff_since_handoff.py")
    if os.path.exists(diff_script):
        for proj in find_projects():
            docs = os.path.join(proj, "docs")
            for agent, prefix in [("codex", "CX"), ("claude_code", "CC")]:
                # Check if a new HANDOFF exists that hasn't been verified
                handoff_pattern = f"HANDOFF_{prefix}_"
                for fn in os.listdir(docs) if os.path.isdir(docs) else []:
                    if fn.startswith(handoff_pattern) and fn.endswith(".md"):
                        diff_marker = os.path.join(docs, f".verified_{fn}")
                        if not os.path.exists(diff_marker):
                            code, out, err = run(
                                f'"{PYTHON}" "{diff_script}" --other-agent {agent} --output "{docs}"',
                                timeout=15
                            )
                            if code != 0:
                                mismatch_path = os.path.join(docs, "VERIFICATION_FAIL.md")
                                with open(mismatch_path, 'w', encoding='utf-8') as f:
                                    f.write(f"# CROSS-VERIFICATION FAILED\n")
                                    f.write(f"HANDOFF: {fn}\nTime: {datetime.now().isoformat()}\n")
                                    f.write(f"Run diff_since_handoff.py for details.\n")
                                log(f"VERIFICATION FAIL: {agent} HANDOFF {fn}")
                            # Mark as verified
                            with open(diff_marker, 'w', encoding='utf-8') as f:
                                f.write(datetime.now().isoformat())

    log("--- TICK END ---")
    return 0

if __name__ == "__main__":
    sys.exit(main())
