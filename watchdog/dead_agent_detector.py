"""
Dead Agent Detector -- detect crashed/stuck agents and auto-recover tasks.
Called by daemon_tick.py every 5 minutes.

Detection methods:
  - Codex: stale codex_session_active.lock (>30 min) + IN PROGRESS tasks
  - CC: stale heartbeat (>60 min) + IN PROGRESS tasks

Response:
  - Move dead agent's IN PROGRESS tasks back to QUEUED
  - Write CC_WAKEUP.md / CODEX_WAKEUP.md for surviving agent
  - Log detection event
"""
import os, sys, json, re
from datetime import datetime

WD = os.path.dirname(os.path.abspath(__file__))
LOCK_DIR = os.path.join(WD, 'locks')
ENFORCE = os.path.join(WD, 'enforce.py')

def find_queue(project_root):
    for p in [os.path.join(project_root, 'docs', 'TASK_QUEUE.md'),
              os.path.join(project_root, '..', 'docs', 'TASK_QUEUE.md')]:
        if os.path.exists(p):
            return os.path.abspath(p)
    return None


def check_codex_alive():
    """Check if Codex session lock exists and is fresh (<30 min)."""
    lock_path = os.path.join(LOCK_DIR, 'codex_session_active.lock')
    if not os.path.exists(lock_path):
        return False, 'no lock file'
    try:
        with open(lock_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        lock_time = datetime.fromisoformat(data.get('time', '2000-01-01'))
        age_min = (datetime.now() - lock_time).total_seconds() / 60
        if age_min > 30:
            return False, f'lock stale ({age_min:.0f}m > 30m)'
        return True, f'alive ({age_min:.0f}m ago)'
    except Exception:
        return False, 'corrupt lock'


def check_cc_alive():
    """Check if CC session lock exists and is fresh (<30 min)."""
    lock_path = os.path.join(LOCK_DIR, 'cc_session_active.lock')
    if not os.path.exists(lock_path):
        return False, 'no lock file'
    try:
        with open(lock_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        lock_time = datetime.fromisoformat(data.get('time', '2000-01-01'))
        age_min = (datetime.now() - lock_time).total_seconds() / 60
        if age_min > 30:
            return False, f'lock stale ({age_min:.0f}m > 30m)'
        return True, f'alive ({age_min:.0f}m ago)'
    except Exception:
        return False, 'corrupt lock'


def detect_and_recover(project_root):
    """Main entry point. Detect dead agents and recover their tasks."""
    result = {
        'project': project_root,
        'detections': [],
        'recoveries': [],
        'timestamp': datetime.now().isoformat()
    }

    queue_path = find_queue(project_root)
    if not queue_path:
        result['error'] = 'No TASK_QUEUE.md found'
        return result

    try:
        with open(queue_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        result['error'] = str(e)
        return result

    # Find IN PROGRESS tasks
    codex_tasks = []
    cc_tasks = []
    for i, ln in enumerate(lines):
        if '[IN PROGRESS - codex]' in ln or '[IN PROGRESS -- codex]' in ln:
            codex_tasks.append((i, ln.strip()))
        elif '[IN PROGRESS - claude_code]' in ln or '[IN PROGRESS -- claude_code]' in ln:
            cc_tasks.append((i, ln.strip()))

    modified = False

    # Check Codex
    if codex_tasks:
        codex_alive, reason = check_codex_alive()
        if not codex_alive:
            result['detections'].append(f'Codex DEAD: {reason}')
            for idx, task_line in codex_tasks:
                # Move to QUEUED - Codex section
                new_line = task_line.replace('[IN PROGRESS - codex]', '').replace('[IN PROGRESS -- codex]', '').strip()
                # Find QUEUED - Codex section
                for j, ln in enumerate(lines):
                    if 'QUEUED' in ln and ('Codex' in ln or 'codex' in ln.lower()):
                        # Insert after section header
                        lines.insert(j + 1, f'- [ ] {new_line}  <!-- recovered from dead agent -->\n')
                        break
                lines[idx] = f'<!-- DEAD AGENT RECOVERED: {task_line.strip()} -->\n'
                result['recoveries'].append(new_line[:80])
                modified = True

            # Write CODEX_WAKEUP.md
            docs = os.path.dirname(queue_path)
            wp = os.path.join(docs, 'CODEX_WAKEUP.md')
            with open(wp, 'w', encoding='utf-8') as f:
                f.write(f'# CODEX WAKEUP -- {datetime.now().isoformat()}\n')
                f.write(f'Agent was DEAD. Recovered {len(codex_tasks)} task(s):\n')
                for _, tl in codex_tasks:
                    f.write(f'- {tl.strip()}\n')

    # Check CC
    if cc_tasks:
        cc_alive, reason = check_cc_alive()
        if not cc_alive:
            result['detections'].append(f'CC DEAD: {reason}')
            for idx, task_line in cc_tasks:
                new_line = task_line.replace('[IN PROGRESS - claude_code]', '').replace('[IN PROGRESS -- claude_code]', '').strip()
                # Find QUEUED - Claude Code section
                for j, ln in enumerate(lines):
                    if 'QUEUED' in ln and ('Claude Code' in ln or 'claude_code' in ln.lower()):
                        lines.insert(j + 1, f'- [ ] {new_line}  <!-- recovered from dead agent -->\n')
                        break
                lines[idx] = f'<!-- DEAD AGENT RECOVERED: {task_line.strip()} -->\n'
                result['recoveries'].append(new_line[:80])
                modified = True

            docs = os.path.dirname(queue_path)
            wp = os.path.join(docs, 'CC_WAKEUP.md')
            with open(wp, 'w', encoding='utf-8') as f:
                f.write(f'# CC WAKEUP -- {datetime.now().isoformat()}\n')
                f.write(f'Agent was DEAD. Recovered {len(cc_tasks)} task(s):\n')
                for _, tl in cc_tasks:
                    f.write(f'- {tl.strip()}\n')

    if modified:
        with open(queue_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: dead_agent_detector.py <project_root>")
        sys.exit(1)

    result = detect_and_recover(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(2 if result.get('recoveries') else 0)


if __name__ == '__main__':
    main()
