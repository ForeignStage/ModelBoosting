"""
Codex Enforcer Daemon -- Filesystem-based mechanical enforcement for Codex agent.
Codex has no settings.json hooks. This daemon provides equivalent mechanical gates:
  - Detects .py file modifications without prior gate marker lock
  - Violations >= tripwire within a tick window create EMERGENCY_STOP + auto-restore
  - Gate marker locks are written by codex_gate.py pre_gate()

Two modes:
  --fast : 30s scan window, tripwire=2 (for standalone 30s Task Scheduler job)
  default: 10min scan window, tripwire=3 (for daemon_tick.py integration)
"""
import os, json, hashlib, sys, shutil
from datetime import datetime

LOCK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'locks')
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backups')
WATCH_EXTENSIONS = ('.py', '.md', '.json', '.toml')
VIOLATION_TRIPWIRE = 3
RECENT_MINUTES = 10

def _file_hash(filepath):
    """Short deterministic hash of a file path for lock naming."""
    return hashlib.md5(filepath.encode()).hexdigest()[:12]


def find_gate_marker(filepath):
    """Check if a gate marker lock exists for this file."""
    marker_path = os.path.join(LOCK_DIR, f'codex_gate_{_file_hash(filepath)}.lock')
    if os.path.exists(marker_path):
        try:
            with open(marker_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            marker_time = datetime.fromisoformat(data.get('time', '2000-01-01'))
            age_sec = (datetime.now() - marker_time).total_seconds()
            # Marker valid for 5 minutes (edit window)
            if age_sec < 300:
                return True, marker_time.isoformat()
        except Exception:
            pass
    return False, None


def codex_is_active():
    """Check if Codex is currently active based on session lock."""
    session_lock = os.path.join(LOCK_DIR, 'codex_session_active.lock')
    if not os.path.exists(session_lock):
        return False
    try:
        with open(session_lock, 'r', encoding='utf-8') as f:
            data = json.load(f)
        lock_time = datetime.fromisoformat(data.get('time', '2000-01-01'))
        age_min = (datetime.now() - lock_time).total_seconds() / 60
        return age_min < 30
    except Exception:
        return False


def scan_project(project_root):
    """Scan a project for files modified without gate markers.
    Returns list of (filepath, mtime_age_min) violations."""
    violations = []
    scope_path = os.path.join(project_root, 'docs', 'SCOPE_active.md')
    has_scope = os.path.exists(scope_path)

    # Walk backend/ and api/ directories only -- skip docs/, backups/, logs/, .git, etc.
    for scan_dir in ['backend', 'api']:
        scan_path = os.path.join(project_root, scan_dir)
        if not os.path.isdir(scan_path):
            continue
        try:
            for root, _, files in os.walk(scan_path):
                # Skip __pycache__, .git, node_modules, venv
                if any(skip in root for skip in ['__pycache__', '.git', 'node_modules', 'venv', '.venv']):
                    continue
                for fn in files:
                    if not fn.endswith(WATCH_EXTENSIONS):
                        continue
                    fp = os.path.join(root, fn)
                    try:
                        mtime = os.path.getmtime(fp)
                    except OSError:
                        continue
                    age_min = (datetime.now().timestamp() - mtime) / 60
                    if age_min > RECENT_MINUTES:
                        continue

                    has_gate, gate_time = find_gate_marker(fp)
                    if not has_gate:
                        violations.append((fp, round(age_min, 1)))
                        if len(violations) >= VIOLATION_TRIPWIRE:
                            return violations  # early return if tripwire hit
        except Exception:
            continue

    return violations


def auto_restore(filepath):
    """Restore file from latest .bak backup. Returns True if restored."""
    # Try filepath.bak first (direct backup)
    bak = filepath + '.bak'
    if os.path.exists(bak):
        shutil.copy2(bak, filepath)
        return True
    # Try backup dir
    bn = os.path.basename(filepath)
    if os.path.isdir(BACKUP_DIR):
        candidates = []
        for f in os.listdir(BACKUP_DIR):
            if bn in f and f.endswith('.bak'):
                candidates.append(os.path.join(BACKUP_DIR, f))
        if candidates:
            candidates.sort(key=os.path.getmtime, reverse=True)
            shutil.copy2(candidates[0], filepath)
            return True
    return False


def enforce(project_root, fast=False):
    """Main enforcement entry point.
    Args:
        project_root: path to project
        fast: if True, use shorter scan window (2min) and lower tripwire (2)
    Returns dict with violations, restores, and action taken."""
    os.makedirs(LOCK_DIR, exist_ok=True)

    # Fast mode: only enforce if Codex is actually running
    if fast and not codex_is_active():
        return {
            'project': project_root,
            'violations': [],
            'restores': [],
            'action': 'none',
            'mode': 'fast-skip',
            'reason': 'Codex not active',
            'timestamp': datetime.now().isoformat()
        }

    # Fast mode overrides
    global RECENT_MINUTES, VIOLATION_TRIPWIRE
    if fast:
        RECENT_MINUTES = 2
        VIOLATION_TRIPWIRE = 2

    result = {
        'project': project_root,
        'violations': [],
        'restores': [],
        'action': 'none',
        'mode': 'fast' if fast else 'normal',
        'timestamp': datetime.now().isoformat()
    }

    violations = scan_project(project_root)
    result['violations'] = violations

    if len(violations) >= VIOLATION_TRIPWIRE:
        # Auto-restore each violated file from .bak
        for vp, age in violations:
            if auto_restore(vp):
                result['restores'].append(vp)

        emergency = os.path.join(project_root, 'docs', 'EMERGENCY_STOP')
        os.makedirs(os.path.dirname(emergency), exist_ok=True)
        with open(emergency, 'w', encoding='utf-8') as f:
            f.write(f"CODEX ENFORCER ({result['mode']}): {len(violations)} gate violations\n")
            f.write(f"Time: {datetime.now().isoformat()}\n")
            f.write("Files modified without codex_gate.py pre gate:\n")
            for vp, age in violations:
                restored = ' [RESTORED from .bak]' if vp in result['restores'] else ''
                f.write(f"  - {vp} ({age}m ago){restored}\n")
        result['action'] = 'EMERGENCY_STOP'

    return result


def main():
    fast = '--fast' in sys.argv
    args = [a for a in sys.argv[1:] if a != '--fast']

    if len(args) < 1:
        print("Usage: codex_enforcer_daemon.py [--fast] <project_root>")
        sys.exit(1)

    project_root = args[0]
    result = enforce(project_root, fast=fast)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result['action'] == 'EMERGENCY_STOP':
        sys.exit(2)  # exit 2 = EMERGENCY_STOP created
    sys.exit(0)


if __name__ == '__main__':
    main()
