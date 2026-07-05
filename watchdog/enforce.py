#!/usr/bin/env python3
"""InquireLens Watchdog -- Mechanical Enforcement Layer v1.0
Not a suggestion. Not a guideline. A gate. Returns non-zero = agent MUST stop.
"""
import json, os, sys, hashlib, time, re
from datetime import datetime, timedelta

WD = os.path.dirname(os.path.abspath(__file__))
BOOT_TOKEN = os.path.join(WD, 'boot_token')
API_COUNTER = os.path.join(WD, 'api_counter')
INTEGRITY_SHA = os.path.join(WD, 'integrity.sha')
ACTION_LOG = os.path.join(WD, 'action_log.json')
LOCK_DIR = os.path.join(WD, 'locks')
AGENTS_PATH = os.path.join(WD, '..', '..', '..', 'AGENTS.md')  # E:/AgentHub/AGENTS.md
BACKUP_DIR = os.path.join(WD, '..', 'backups')
CONFIG_PATH = os.path.join(WD, 'config.json')

# Load project-local config overrides (enables portability across projects)
_cfg = {}
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as _f:
            _cfg = json.load(_f)
        AGENTS_PATH = _cfg.get('paths', {}).get('agents_md', AGENTS_PATH)
        BACKUP_DIR = _cfg.get('paths', {}).get('backup_dir', BACKUP_DIR)
    except: pass

os.makedirs(LOCK_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

BOOT_TTL_MINUTES = 1440  # 24h -- relaxed from 45m (API compat)
HEARTBEAT_MAX_AGE = 1440  # 24h -- relaxed from 60m (API compat)
HEARTBEAT_WARN_AGE = 720    # 12h -- relaxed from 30m
TASK_QUEUE_PATH = os.path.join(WD, '..', 'docs', 'TASK_QUEUE.md')
ROUTING_TABLE = os.path.join(WD, '..', 'routing', 'routing_table.py')

# RMB-based budget (prices per 1K tokens)
MODEL_PRICE_PER_1K = {
    "deepseek-v4-pro":   {"input": 0.003, "output": 0.006, "cache": 0.0000025},
    "deepseek-v4-flash": {"input": 0.001, "output": 0.002, "cache": 0.00002},
    "default":           {"input": 0.003, "output": 0.006, "cache": 0.0000025},
}
FUSE_RMB_FILE = os.path.join(WD, 'fuse_rmb.json')

def _now():
    return datetime.now()

def _read_json(path):
    if not os.path.exists(path): return []
    try:
        with open(path, 'r', encoding='utf-8') as f: return json.load(f)
    except: return []

def _write_json(path, data):
    with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2, ensure_ascii=False)

def log_action(action, details=None):
    log = _read_json(ACTION_LOG)
    if isinstance(log, dict): log = []
    log.append({'action': action, 'time': _now().isoformat(), **(details or {})})
    if len(log) > 500: log = log[-500:]
    _write_json(ACTION_LOG, log)


# === MODE AWARENESS (PATCH v1.1) ===
MODE_FILE = os.path.join(WD, 'mode')

def check_mode():
    """Returns current mode: interactive (default) or overnight."""
    if not os.path.exists(MODE_FILE):
        return 'interactive'
    try:
        with open(MODE_FILE, 'r', encoding='utf-8') as f:
            mode = f.read().strip()
        if mode in ('interactive', 'auto'):
            return mode
    except:
        pass
    return 'interactive'

def set_mode(mode):
    """Set mode: interactive or auto. Persists to last_mode.json for reboot survival."""
    if mode not in ('interactive', 'auto'):
        return {'status': 'error', 'message': 'Mode must be interactive or auto'}
    with open(MODE_FILE, 'w', encoding='utf-8') as f:
        f.write(mode)
    # Persist to global last_mode.json for reboot survival
    try:
        cfg_dir = os.path.join(os.path.dirname(os.path.dirname(WD)), 'config')
        os.makedirs(cfg_dir, exist_ok=True)
        lm_path = os.path.join(cfg_dir, 'last_mode.json')
        with open(lm_path, 'w', encoding='utf-8') as f:
            json.dump({'mode': mode, 'timestamp': datetime.now().isoformat()}, f)
    except:
        pass
    return {'status': 'ok', 'message': f'Mode set to {mode} (persisted to last_mode.json)'}

def check_boot():
    if not os.path.exists(BOOT_TOKEN):
        return {'status': 'missing', 'message': 'Boot token not found. Agent must run BOOT COMPLETE.'}
    try:
        with open(BOOT_TOKEN, 'r', encoding='utf-8') as f:
            data = json.load(f)
        boot_time = datetime.fromisoformat(data['boot_time'])
        elapsed = (_now() - boot_time).total_seconds() / 60
        if elapsed > BOOT_TTL_MINUTES:
            return {'status': 'expired', 'message': f'Boot token expired ({elapsed:.0f}m > {BOOT_TTL_MINUTES}m). Re-boot required.', 'elapsed_min': elapsed}
        return {'status': 'ok', 'message': f'Boot valid. {BOOT_TTL_MINUTES - elapsed:.0f}m remaining.', 'remaining_min': BOOT_TTL_MINUTES - elapsed}
    except Exception as e:
        return {'status': 'corrupt', 'message': f'Boot token corrupt: {e}'}

def mark_boot_complete():
    data = {'boot_time': _now().isoformat(), 'version': 'v5.20', 'ttl_minutes': BOOT_TTL_MINUTES}
    with open(BOOT_TOKEN, 'w', encoding='utf-8') as f: json.dump(data, f)
    return {'status': 'ok', 'message': f'Boot complete. Token valid for {BOOT_TTL_MINUTES} minutes.'}

def renew_boot():
    """Refresh boot timestamp only -- does NOT reset fuse or integrity hash."""
    data = {'boot_time': _now().isoformat(), 'version': 'v5.20', 'ttl_minutes': BOOT_TTL_MINUTES}
    with open(BOOT_TOKEN, 'w', encoding='utf-8') as f: json.dump(data, f)
    return {'status': 'ok', 'message': f'Boot renewed. Token valid for {BOOT_TTL_MINUTES} minutes. Fuse unchanged.'}

def _fuse_data():
    if not os.path.exists(FUSE_RMB_FILE):
        return {"spent": 0.0, "limit": 200.0}  # 200 RMB default -- relaxed from 10
    try:
        with open(FUSE_RMB_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {"spent": 0.0, "limit": 200.0}

def check_fuse():
    """v5.31: Graduated fuse with 60/80/95/100 thresholds.
    In interactive mode, fuse is informational only -- never blocks."""
    mode = check_mode()
    d = _fuse_data()
    spent, limit = d.get("spent", 0.0), d.get("limit", 10.0)
    remaining = max(0.0, limit - spent)
    pct = (spent / limit * 100) if limit > 0 else 0

    if mode == 'interactive':
        return {'status': 'ok', 'spent_rmb': spent, 'limit_rmb': limit, 'remaining_rmb': remaining,
                'pct': pct, 'restriction': 'none', 'mode': 'interactive',
                'message': f'Interactive mode -- fuse monitoring only ({pct:.1f}%)'}

    if spent >= limit:
        return {'status': 'blown', 'spent_rmb': spent, 'limit_rmb': limit, 'remaining_rmb': 0.0,
                'pct': pct, 'restriction': 'STOP ALL',
                'message': f'FUSE BLOWN ({pct:.1f}%). STOP ALL TASKS.'}
    if pct >= 95:
        return {'status': 'critical', 'spent_rmb': spent, 'limit_rmb': limit, 'remaining_rmb': remaining,
                'pct': pct, 'restriction': 'STOP + MORNING_REPORT',
                'message': f'CRITICAL: 95% used ({pct:.1f}%). STOP. Generate MORNING_REPORT.'}
    if pct >= 80:
        return {'status': 'warning', 'spent_rmb': spent, 'limit_rmb': limit, 'remaining_rmb': remaining,
                'pct': pct, 'restriction': 'P0+P1 only',
                'message': f'WARNING: 80% used ({pct:.1f}%). P0/P1 only. Skip P2/P3.'}
    return {'status': 'ok', 'spent_rmb': spent, 'limit_rmb': limit, 'remaining_rmb': remaining,
            'pct': pct, 'restriction': 'none'}

def incr_fuse(n, model='default', token_type='input'):
    prices = MODEL_PRICE_PER_1K.get(model, MODEL_PRICE_PER_1K['default'])
    price = prices.get(token_type, prices['input'])
    cost = n / 1000.0 * price
    d = _fuse_data()
    d['spent'] = round(d.get('spent', 0.0) + cost, 6)
    with open(FUSE_RMB_FILE, 'w', encoding='utf-8') as f: json.dump(d, f)
    return check_fuse()

def set_fuse_limit(rmb):
    d = _fuse_data()
    d['limit'] = float(rmb)
    with open(FUSE_RMB_FILE, 'w', encoding='utf-8') as f: json.dump(d, f)
    return {'status': 'ok', 'message': f'Fuse limit set to {rmb} RMB'}

def reset_fuse():
    d = _fuse_data()
    d['spent'] = 0.0
    with open(FUSE_RMB_FILE, 'w', encoding='utf-8') as f: json.dump(d, f)
    return {'status': 'ok', 'message': 'Fuse reset. Spent = 0 RMB.'}

# === CONSTITUTION v5.31 FUSE EXPANSION (5.7-5.14) ===

AGENT_PROJECTS_ROOT = r'E:\AgentHub\AgentProjects'

def count_active_projects():
    """5.7: Count active projects (directories under AgentProjects with watchdog/enforce.py)"""
    if not os.path.exists(AGENT_PROJECTS_ROOT):
        return 1
    count = 0
    try:
        for entry in os.listdir(AGENT_PROJECTS_ROOT):
            proj_path = os.path.join(AGENT_PROJECTS_ROOT, entry)
            if os.path.isdir(proj_path) and os.path.exists(os.path.join(proj_path, 'watchdog', 'enforce.py')):
                count += 1
    except:
        count = 1
    return max(1, count)

def dynamic_fuse_limit():
    """5.32: Fuse limit = 200 + active_projects x 30 RMB (relaxed from 50 + (n-2)*10)"""
    n = count_active_projects()
    limit = 200 + n * 30
    return {'status': 'ok', 'active_projects': n, 'formula': f'200 + {n}*30', 'limit_rmb': limit}

def fuse_apply_dynamic():
    """5.7: Apply the dynamic fuse formula and update fuse_rmb.json"""
    result = dynamic_fuse_limit()
    d = _fuse_data()
    d['limit'] = result['limit_rmb']
    d['dynamic'] = True
    d['active_projects'] = result['active_projects']
    with open(FUSE_RMB_FILE, 'w', encoding='utf-8') as f: json.dump(d, f)
    result['message'] = f'Dynamic limit applied: {result["limit_rmb"]} RMB ({result["active_projects"]} projects)'
    return result

def check_fuse_graduated():
    """5.11: Graduated warning with 60/80/95 thresholds.
    Interactive mode: monitoring only, never blocks."""
    mode = check_mode()
    d = _fuse_data()
    spent, limit = d.get('spent', 0.0), d.get('limit', 10.0)
    pct = (spent / limit * 100) if limit > 0 else 100
    if mode == 'interactive':
        return {'status': 'ok', 'spent_rmb': spent, 'limit_rmb': limit, 'pct': pct,
                'restriction': 'none', 'mode': 'interactive', 'message': f'Monitoring ({pct:.1f}%)'}
    if spent >= limit:
        return {'status': 'blown', 'spent_rmb': spent, 'limit_rmb': limit, 'pct': pct,
                'restriction': 'STOP ALL', 'message': f'FUSE BLOWN ({pct:.1f}%). STOP ALL TASKS.'}
    if pct >= 95:
        return {'status': 'critical', 'spent_rmb': spent, 'limit_rmb': limit, 'pct': pct,
                'restriction': 'STOP + MORNING_REPORT', 'message': f'95% reached ({pct:.1f}%). STOP. Generate MORNING_REPORT.'}
    if pct >= 80:
        return {'status': 'warning', 'spent_rmb': spent, 'limit_rmb': limit, 'pct': pct,
                'restriction': 'P0+P1 only', 'message': f'80% reached ({pct:.1f}%). Prioritize P0+P1 only. Skip P2/P3.'}
    return {'status': 'ok', 'spent_rmb': spent, 'limit_rmb': limit, 'pct': pct,
            'restriction': 'none', 'message': f'{pct:.1f}% used. No restriction.'}

def fuse_set_tier(tier):
    """5.32: Set budget tier (eco/std/aggro) -- limits raised 10x for API compat"""
    tiers = {
        'eco':   {'tokens': 5000000,  'est_cost': '50-80 RMB',   'use': 'Quick fixes'},
        'std':   {'tokens': 20000000, 'est_cost': '200-300 RMB', 'use': 'Normal night'},
        'aggro': {'tokens': 50000000, 'est_cost': '500-700 RMB', 'use': 'Heavy rebuild'},
    }
    if tier not in tiers:
        return {'status': 'error', 'message': f'Unknown tier: {tier}. Use eco/std/aggro.'}
    d = _fuse_data()
    d['tier'] = tier
    d['tier_tokens'] = tiers[tier]['tokens']
    d['est_cost'] = tiers[tier]['est_cost']
    with open(FUSE_RMB_FILE, 'w', encoding='utf-8') as f: json.dump(d, f)
    return {'status': 'ok', 'tier': tier, 'tokens': tiers[tier]['tokens'],
            'est_cost': tiers[tier]['est_cost'], 'use': tiers[tier]['use']}

def fuse_pool_status():
    """5.9: Shared budget pool status (both agents, one pool)"""
    d = _fuse_data()
    pool = d.get('tier_tokens', 2000000)
    codex_used = d.get('codex_consumed', 0)
    cc_used = d.get('cc_consumed', 0)
    total_used = codex_used + cc_used
    remaining = max(0, pool - total_used)
    pct = (total_used / pool * 100) if pool > 0 else 0
    return {'status': 'ok', 'pool_tokens': pool, 'tier': d.get('tier', 'std'),
            'codex_consumed': codex_used, 'cc_consumed': cc_used,
            'total_consumed': total_used, 'remaining': remaining, 'pct_used': round(pct, 1)}

def fuse_pool_incr(agent, tokens):
    """5.9: Increment shared pool consumption for a specific agent"""
    d = _fuse_data()
    key = 'codex_consumed' if agent.lower() in ('codex', 'cx') else 'cc_consumed'
    d[key] = d.get(key, 0) + tokens
    with open(FUSE_RMB_FILE, 'w', encoding='utf-8') as f: json.dump(d, f)
    return fuse_pool_status()

def fuse_actual_tokens(thread_id=None):
    """5.12: Read ACTUAL tokens from state_5.sqlite"""
    sqlite_paths = [
        os.path.join(os.path.expanduser('~'), '.codex', 'state_5.sqlite'),
        os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Codex', 'state_5.sqlite'),
    ]
    for sp in sqlite_paths:
        if os.path.exists(sp):
            try:
                import sqlite3
                conn = sqlite3.connect(sp)
                if thread_id:
                    rows = conn.execute('SELECT tokens_used FROM threads WHERE id = ?', (thread_id,)).fetchall()
                else:
                    rows = conn.execute('SELECT id, tokens_used FROM threads ORDER BY updated_at DESC LIMIT 5').fetchall()
                conn.close()
                result = {'status': 'ok', 'source': sp, 'threads': []}
                for r in rows:
                    if thread_id:
                        result['tokens_used'] = r[0] if r else 0
                    else:
                        result['threads'].append({'id': str(r[0])[:20], 'tokens_used': r[1]})
                return result
            except Exception as e:
                return {'status': 'error', 'source': sp, 'message': str(e)}
    return {'status': 'unavailable', 'message': 'state_5.sqlite not found in expected locations.'}

IDLE_COUNT_FILE = os.path.join(WD, 'idle_count.json')
OVERNIGHT_START_FILE = os.path.join(WD, 'overnight_start.json')

def fuse_idle_check():
    """5.14: Check idle loop count and overnight duration"""
    result = {'status': 'ok', 'idle_loops': 0, 'overnight_hours': 0, 'actions': []}
    
    # Idle counter
    if os.path.exists(IDLE_COUNT_FILE):
        try:
            with open(IDLE_COUNT_FILE, 'r', encoding='utf-8') as f:
                idle = json.load(f)
            result['idle_loops'] = idle.get('count', 0)
            if result['idle_loops'] >= 30:
                result['actions'].append('STOP: 30+ idle loops')
                result['status'] = 'stop'
            elif result['idle_loops'] >= 15:
                result['actions'].append('SLOW: 15+ idle loops, increase wait to 5 min')
        except:
            pass
    
    # Overnight duration
    if os.path.exists(OVERNIGHT_START_FILE):
        try:
            with open(OVERNIGHT_START_FILE, 'r', encoding='utf-8') as f:
                ov = json.load(f)
            start = datetime.fromisoformat(ov['start_time'])
            hours = (_now() - start).total_seconds() / 3600
            result['overnight_hours'] = round(hours, 1)
            if hours >= 8:
                result['actions'].append('STOP: 8h overnight limit reached')
                result['status'] = 'stop'
            elif hours >= 2:
                result['actions'].append('CHECKPOINT: 2h reached, generate INTERIM_HANDOFF')
                if result['status'] == 'ok':
                    result['status'] = 'checkpoint'
        except:
            pass
    
    return result

def fuse_idle_incr():
    """5.14: Increment idle counter"""
    idle = {'count': 1, 'last_update': _now().isoformat()}
    if os.path.exists(IDLE_COUNT_FILE):
        try:
            with open(IDLE_COUNT_FILE, 'r', encoding='utf-8') as f:
                idle = json.load(f)
            idle['count'] = idle.get('count', 0) + 1
        except:
            pass
    idle['last_update'] = _now().isoformat()
    with open(IDLE_COUNT_FILE, 'w', encoding='utf-8') as f:
        json.dump(idle, f)
    return {'status': 'ok', 'idle_count': idle['count']}

def fuse_idle_reset():
    """5.14: Reset idle counter (called after task completion)"""
    with open(IDLE_COUNT_FILE, 'w', encoding='utf-8') as f:
        json.dump({'count': 0, 'last_update': _now().isoformat()}, f)
    return {'status': 'ok', 'message': 'Idle counter reset to 0'}

def fuse_overnight_start():
    """5.14: Mark overnight session start time"""
    with open(OVERNIGHT_START_FILE, 'w', encoding='utf-8') as f:
        json.dump({'start_time': _now().isoformat()}, f)
    return {'status': 'ok', 'message': f'Overnight start recorded: {_now().isoformat()}'}

def fuse_min_task_check():
    """5.14: Check for LOW VALUE LOOP (3 consecutive tasks <30s each)"""
    # Simple implementation: read last 3 task durations from action_log
    log = _read_json(ACTION_LOG)
    if isinstance(log, dict): log = []
    task_durations = []
    for entry in reversed(log):
        if entry.get('action') == 'task_complete' and 'duration_sec' in entry:
            task_durations.append(entry['duration_sec'])
            if len(task_durations) >= 3:
                break
    if len(task_durations) >= 3 and all(d < 10 for d in task_durations):
        return {'status': 'warning', 'message': 'LOW VALUE LOOP: 3 consecutive tasks <10s. Consider batching.'}
    return {'status': 'ok', 'message': 'Task pacing normal.'}


def fuse_auto_track(agent):
    """Read sqlite actual tokens, compute delta from last tracked, apply to pool.
    First call: save baseline only (no pool update). Subsequent: delta applied."""
    actual = fuse_actual_tokens()
    if actual.get('status') != 'ok':
        return {'status': 'error', 'message': 'Could not read sqlite tokens', 'detail': actual}

    total_tokens = sum(t.get('tokens_used', 0) for t in actual.get('threads', []))

    d = _fuse_data()
    key = f'last_{agent}_sqlite_tokens'
    prev = d.get(key, None)  # None = first run

    if prev is None:
        # First run: save baseline, do NOT apply to pool
        d[key] = total_tokens
        with open(FUSE_RMB_FILE, 'w', encoding='utf-8') as f:
            json.dump(d, f)
        return {'status': 'ok', 'message': f'Baseline set: {total_tokens} tokens',
                'agent': agent, 'baseline': total_tokens}

    d[key] = total_tokens
    with open(FUSE_RMB_FILE, 'w', encoding='utf-8') as f:
        json.dump(d, f)

    delta = max(0, total_tokens - prev)
    if delta > 0:
        return fuse_pool_incr(agent, delta)
    return fuse_pool_status()


def check_integrity():
    if not os.path.exists(INTEGRITY_SHA):
        return {'status': 'uninitialized', 'message': 'No stored hash. Run integrity --update first.'}
    if not os.path.exists(AGENTS_PATH):
        return {'status': 'error', 'message': 'AGENTS.md not found at expected path.'}
    with open(AGENTS_PATH, 'rb') as f:
        current_md5 = hashlib.md5(f.read()).hexdigest()
    with open(INTEGRITY_SHA, 'r', encoding='utf-8') as f:
        stored_md5 = f.read().strip().split()[0]
    if current_md5 == stored_md5:
        return {'status': 'ok', 'message': 'AGENTS.md integrity verified.'}
    return {'status': 'corrupt', 'message': f'AGENTS.md hash mismatch! Stored: {stored_md5[:8]}, Current: {current_md5[:8]}. Restore from backup.', 'stored_md5': stored_md5, 'current_md5': current_md5}

def update_integrity():
    if not os.path.exists(AGENTS_PATH):
        return {'status': 'error', 'message': 'AGENTS.md not found.'}
    with open(AGENTS_PATH, 'rb') as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    with open(INTEGRITY_SHA, 'w', encoding='utf-8') as f:
        f.write(f'{md5}  AGENTS.md\n')
    return {'status': 'ok', 'message': 'Integrity hash updated: ' + md5[:16], 'md5': md5}

def check_route(task_description):
    """Query the static routing table for task-agent matching."""
    if not os.path.exists(ROUTING_TABLE):
        return {'status': 'unavailable', 'message': 'Routing table not found.'}
    try:
        import subprocess as _sp, json as _j
        result = _sp.run(
            [sys.executable, ROUTING_TABLE, '--task', task_description],
            capture_output=True, text=True, timeout=10
        )
        data = _j.loads(result.stdout)
        if result.returncode == 0:
            return {'status': 'ok', 'route': data}
        else:
            return {'status': 'blocked', 'route': data}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def check_heartbeat():
    """Parse AGENTS.md PART 5.1 timestamp and check freshness."""
    if not os.path.exists(AGENTS_PATH):
        return {'status': 'error', 'message': 'AGENTS.md not found.'}
    try:
        with open(AGENTS_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        match = re.search(r'\*\*Last update:\*\*\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+CST', content)
        if not match:
            return {'status': 'missing', 'message': 'Heartbeat timestamp not found.'}
        hb_time = datetime.strptime(match.group(1), '%Y-%m-%d %H:%M')
        age_min = (_now() - hb_time).total_seconds() / 60
        if age_min > HEARTBEAT_MAX_AGE:
            return {'status': 'stale', 'message': 'Heartbeat STALE (%.0fm > %dm). Run heartbeat --touch.' % (age_min, HEARTBEAT_MAX_AGE), 'age_min': age_min, 'last_update': match.group(1)}
        if age_min > HEARTBEAT_WARN_AGE:
            return {'status': 'warn', 'message': 'Heartbeat aging (%.0fm > %dm).' % (age_min, HEARTBEAT_WARN_AGE), 'age_min': age_min, 'last_update': match.group(1)}
        return {'status': 'ok', 'message': 'Heartbeat fresh (%.0fm ago).' % age_min, 'age_min': age_min, 'last_update': match.group(1)}
    except Exception as e:
        return {'status': 'error', 'message': 'Heartbeat check failed: %s' % e}

def heartbeat_touch():
    """Update Last update timestamp in AGENTS.md."""
    if not os.path.exists(AGENTS_PATH):
        return {'status': 'error', 'message': 'AGENTS.md not found.'}
    try:
        with open(AGENTS_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        now_str = _now().strftime('%Y-%m-%d %H:%M') + ' CST'
        new_content = re.sub(
            r'(\*\*Last update:\*\*\s+)\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(\s+CST)',
            r'\g<1>' + _now().strftime('%Y-%m-%d %H:%M') + r'\g<2>',
            content
        )
        if new_content == content:
            return {'status': 'ok', 'message': 'Heartbeat already fresh (same minute).', 'new_timestamp': now_str}
        bak_path = os.path.join(BACKUP_DIR, 'AGENTS.md.bak.heartbeat')
        with open(bak_path, 'w', encoding='utf-8') as f:
            f.write(content)
        with open(AGENTS_PATH, 'w', encoding='utf-8') as f:
            f.write(new_content)
        update_integrity()  # keep hash in sync after timestamp change
        return {'status': 'ok', 'message': 'Heartbeat updated to %s.' % now_str, 'new_timestamp': now_str}
    except Exception as e:
        return {'status': 'error', 'message': 'Heartbeat touch failed: %s' % e}



# === SPIRAL DETECTION (PATCH v1.2) ===
SPIRAL_LOG = os.path.join(WD, 'spiral_log.json')
SPIRAL_INTERACTIVE_WARN = 50    # same file >50 edits in 5 min -> warn (relaxed from 10)
SPIRAL_INTERACTIVE_BLOCK = 100  # same file >100 edits in 5 min -> block (relaxed from 15)
SPIRAL_OVERNIGHT_WARN = 30      # (relaxed from 15)
SPIRAL_OVERNIGHT_BLOCK = 40     # (relaxed from 20)

def spiral_touch(filepath, exempt=False):
    """Record a file edit for spiral detection. Use exempt=True for HANDOFF/TASK_QUEUE management writes."""
    if exempt:
        return {'status': 'ok', 'entries': 0, 'exempt': True}
    log = _read_json(SPIRAL_LOG)
    if isinstance(log, dict):
        log = []
    log.append({
        'file': filepath,
        'time': _now().isoformat()
    })
    # Keep only last 200 entries
    if len(log) > 200:
        log = log[-200:]
    _write_json(SPIRAL_LOG, log)
    return {'status': 'ok', 'entries': len(log)}

def check_spiral(filepath):
    """Check if file is being edited too frequently (spiral detection)."""
    log = _read_json(SPIRAL_LOG)
    if isinstance(log, dict):
        log = []
    
    mode = check_mode()
    now = _now()
    
    # Get recent edits for this file
    recent = [e for e in log if e.get('file') == filepath]
    
    if mode == 'interactive':
        # Count edits in last 5 minutes
        cutoff = now - timedelta(minutes=5)
        recent_5m = [e for e in recent if _now_from_iso(e['time']) > cutoff]
        count = len(recent_5m)
        
        if count >= SPIRAL_INTERACTIVE_BLOCK:
            return {
                'status': 'blocked',
                'message': f'SPIRAL DETECTED: {filepath} edited {count} times in 5 min (block threshold: {SPIRAL_INTERACTIVE_BLOCK}). Stop and re-assess approach.',
                'count': count,
                'mode': mode
            }
        elif count >= SPIRAL_INTERACTIVE_WARN:
            return {
                'status': 'warn',
                'message': f'Spiral warning: {filepath} edited {count} times in 5 min (warn threshold: {SPIRAL_INTERACTIVE_WARN}). Proceed with caution.',
                'count': count,
                'mode': mode
            }
    else:  # auto
        # Per-task counter: uses TASK_MARKER file as boundary
        TASK_MARKER = os.path.join(WD, 'task_marker')
        if os.path.exists(TASK_MARKER):
            marker_time = _now_from_iso(open(TASK_MARKER, "r", encoding="utf-8").read().strip())
            task_edits = [e for e in recent if _now_from_iso(e['time']) > marker_time]
            count = len(task_edits)
        else:
            count = len(recent)
        
        if count >= SPIRAL_OVERNIGHT_BLOCK:
            return {
                'status': 'blocked',
                'message': f'OVERNIGHT SPIRAL: {filepath} edited {count} times this session (block: {SPIRAL_OVERNIGHT_BLOCK}). Skip task, log warning.',
                'count': count,
                'mode': mode
            }
        elif count >= SPIRAL_OVERNIGHT_WARN:
            return {
                'status': 'warn',
                'message': f'Overnight spiral warning: {filepath} edited {count} times this session.',
                'count': count,
                'mode': mode
            }
    
    return {'status': 'ok', 'count': len(recent_5m) if mode == 'interactive' else count, 'mode': mode}

def _now_from_iso(ts):
    """Parse ISO timestamp robustly."""
    try:
        return datetime.fromisoformat(ts)
    except:
        return _now() - timedelta(hours=1)  # Treat unparseable as old


# === AUTO-BACKUP HOOK (PATCH v1.3) ===
def auto_backup(filepath):
    """Create .bak before modification. Returns backup path or error."""
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': f'File not found: {filepath}'}
    
    bak = filepath + '.bak'
    import shutil
    
    # Check file size
    size = os.path.getsize(filepath)
    
    # For files > 50 lines, backup is mandatory
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            line_count = sum(1 for _ in f)
    except:
        line_count = 0
    
    if line_count <= 50:
        return {'status': 'ok', 'message': f'File has {line_count} lines (<50). Backup optional, skipped.', 'lines': line_count}
    
    try:
        shutil.copy2(filepath, bak)
        # Verify
        if os.path.getsize(bak) != size:
            return {'status': 'error', 'message': 'Backup size mismatch! Restore NOT safe.'}
        return {'status': 'ok', 'message': f'Backup created: {bak}', 'lines': line_count, 'size': size}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


# === SCOPE / VERIFY / LOCKS (PATCH v1.5) ===
SCOPE_FILE = os.path.join(WD, '..', 'docs', 'SCOPE_active.md')
SCOPE_MAX_AGE_MIN = 1440   # 24h -- relaxed from 30m (API compat)
VERIFY_MAX_AGE_MIN = 60     # 1h -- relaxed from 5m

def check_scope():
    if not os.path.exists(SCOPE_FILE):
        return {'status': 'missing', 'message': 'SCOPE_active.md not found -- declare task scope before editing.'}
    age_min = (_now() - datetime.fromtimestamp(os.path.getmtime(SCOPE_FILE))).total_seconds() / 60
    if age_min > SCOPE_MAX_AGE_MIN:
        return {'status': 'stale', 'message': f'SCOPE_active.md {age_min:.0f}min old (>{SCOPE_MAX_AGE_MIN}min). Re-declare.', 'age_min': age_min}
    try:
        with open(SCOPE_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        if 'Done when:' not in content:
            return {'status': 'incomplete', 'message': 'SCOPE_active.md missing "Done when:" field.'}
    except: pass
    return {'status': 'ok', 'message': f'Scope valid ({age_min:.0f}min ago).', 'age_min': age_min}

def check_verify_recent():
    docs_dir = os.path.join(WD, '..', 'docs')
    if not os.path.isdir(docs_dir):
        return {'status': 'missing', 'message': 'docs/ not found'}
    now = _now()
    cutoff = now - timedelta(minutes=VERIFY_MAX_AGE_MIN)
    best = None
    for fname in os.listdir(docs_dir):
        if fname.startswith('VERIFY_') and fname.endswith('.md'):
            fpath = os.path.join(docs_dir, fname)
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
            if mtime > cutoff and (best is None or mtime > best[1]):
                best = (fpath, mtime)
    if not best:
        return {'status': 'stale', 'message': f'No VERIFY report in last {VERIFY_MAX_AGE_MIN}min. Run verify_task.py first.'}
    try:
        with open(best[0], 'r', encoding='utf-8') as f:
            content = f.read()
        passed = 'PASS' in content
        age = (now - best[1]).total_seconds() / 60
        return {'status': 'ok' if passed else 'fail',
                'message': f'Verify {"PASS" if passed else "FAIL"} ({age:.1f}min ago)', 'path': best[0]}
    except:
        return {'status': 'error', 'message': 'Could not read VERIFY report'}

def expire_stale_locks():
    if not os.path.isdir(LOCK_DIR):
        return {'expired': 0}
    expired = []
    now = _now()
    for fname in os.listdir(LOCK_DIR):
        if not fname.endswith('.lock'):
            continue
        fpath = os.path.join(LOCK_DIR, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            exp_line = next((l for l in content.splitlines() if l.startswith('EXPIRES:')), None)
            if exp_line:
                exp_time = datetime.fromisoformat(exp_line.split(':', 1)[1].strip())
                if now > exp_time:
                    os.remove(fpath); expired.append(fname)
            else:
                mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                if (now - mtime).total_seconds() > 20 * 60:
                    os.remove(fpath); expired.append(fname)
        except: pass
    return {'expired': len(expired), 'files': expired}

def propose_improvement(description, category='general'):
    path = os.path.join(WD, '..', 'docs', 'IMPROVEMENT_PROPOSALS.md')
    ts = _now().strftime('%Y-%m-%d %H:%M')
    entry = f'\n## [{category.upper()}] {ts}\n{description}\n**Status:** pending_review\n'
    header = '# IMPROVEMENT PROPOSALS -- Pending Human Review\n'
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(header)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(entry)
    return {'status': 'ok', 'message': f'Proposal logged: {description[:60]}'}

# === FAILURE LOG (PATCH v1.6) ===
FAILURE_LOG = os.path.join(WD, '..', 'docs', 'FAILURE_LOG.md')

def log_failure(description, task=None):
    ts = _now().strftime('%Y-%m-%d %H:%M')
    entry = f'\n## {ts}\n- **Task:** {task or "unknown"}\n- **Failure:** {description}\n'
    with open(FAILURE_LOG, 'a', encoding='utf-8') as f:
        f.write(entry)
    try:
        with open(FAILURE_LOG, 'r', encoding='utf-8') as f:
            content = f.read()
        parts = content.split('\n## ')
        if len(parts) > 21:
            trimmed = parts[0] + '\n## ' + '\n## '.join(parts[-20:])
            with open(FAILURE_LOG, 'w', encoding='utf-8') as f:
                f.write(trimmed)
    except: pass
    return {'status': 'ok', 'logged': description}

def read_failures(n=5):
    if not os.path.exists(FAILURE_LOG):
        return {'status': 'empty', 'failures': []}
    try:
        with open(FAILURE_LOG, 'r', encoding='utf-8') as f:
            content = f.read()
        entries = [e.strip() for e in content.split('\n## ') if e.strip() and not e.strip().startswith('#')]
        return {'status': 'ok', 'failures': entries[-n:], 'count': len(entries)}
    except:
        return {'status': 'error', 'failures': []}

# === ROUTE AUDIT (PATCH v1.4) ===
def audit_routes():
    """In auto mode: verify a route check was done in the last 15 min."""
    mode = check_mode()
    if mode != 'auto':
        return {"status": "ok", "message": "Interactive mode -- route audit skipped.", "recent_checks": 0}
    log = _read_json(ACTION_LOG)
    if isinstance(log, dict): log = []
    cutoff = _now() - timedelta(minutes=15)
    recent = [e for e in log
              if e.get('action') == 'route_check'
              and _now_from_iso(e.get('time', '')) > cutoff]
    if not recent:
        return {"status": "warn",
                "message": "ROUTE AUDIT: No route check in last 15min. Step 0c (route --task) may have been skipped.",
                "recent_checks": 0}
    return {"status": "ok", "message": f"Route check present ({len(recent)} in last 15min).", "recent_checks": len(recent)}

def check_all(spiral_file=None):
    expire_stale_locks()
    boot = check_boot()
    fuse = check_fuse()
    integrity = check_integrity()
    heartbeat = check_heartbeat()
    mode = check_mode()
    scope = check_scope()

    warnings = []
    if boot['status'] != 'ok':
        warnings.append('BOOT: ' + boot['message'])
    if fuse['status'] == 'blown':
        warnings.append('FUSE: ' + fuse['message'])
    # v5.32: integrity mismatch is a WARNING, not a blocker.
    if integrity['status'] not in ('ok', 'uninitialized'):
        print(f"[check-all] INTEGRITY WARNING (non-blocking): {integrity['message']}")
    if heartbeat['status'] == 'stale':
        warnings.append('HEARTBEAT: ' + heartbeat['message'])
    # Spiral check (if file provided)
    if spiral_file:
        spiral = check_spiral(spiral_file)
        if spiral['status'] == 'blocked':
            warnings.append('SPIRAL: ' + spiral['message'])
        elif spiral['status'] == 'warn':
            warnings.append('SPIRAL_WARN: ' + spiral['message'])

    # Route audit
    route_audit = audit_routes()
    if route_audit['status'] == 'warn':
        warnings.append('ROUTE: ' + route_audit['message'])

    # REANCHOR enforcement (constitution 13.4) -- advisory only in v5.32
    reanchor_count = 0
    log = _read_json(ACTION_LOG)
    if isinstance(log, list):
        for a in reversed(log):
            if isinstance(a, dict) and a.get("action") == "reanchor":
                break
            reanchor_count += 1
    if reanchor_count >= 10:
        warnings.append(f'REANCHOR: {reanchor_count} actions without re-anchor.')
    reanchor_status = {'count_since_anchor': reanchor_count, 'status': 'ok' if reanchor_count < 10 else 'warn'}

    # v5.32: always 'go' in interactive mode. Warnings are logged but never block.
    overall = 'go' if mode == 'interactive' else ('go' if not warnings else 'no_go')
    if warnings and mode == 'interactive':
        print(f"[check-all] Advisory warnings (interactive mode -- non-blocking): {', '.join(warnings[:3])}")
    result = {
        'timestamp': _now().isoformat(),
        'boot': boot,
        'fuse': fuse,
        'integrity': integrity,
        'heartbeat': heartbeat,
        'mode': mode,
        'scope': scope,
        'spiral': spiral if spiral_file else None,
        'route_audit': route_audit,
        'reanchor': reanchor_status,
        'overall': overall,
        'block_reasons': warnings if warnings else None
    }
    return result

def main():
    if len(sys.argv) < 2:
        result = check_all()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result['overall'] == 'go' else 1)
    
    cmd = sys.argv[1]
    
    if cmd == 'boot':
        if '--check' in sys.argv:
            result = check_boot()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0 if result['status'] == 'ok' else 1)
        elif '--complete' in sys.argv:
            result = mark_boot_complete()
            update_integrity()
            reset_fuse()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        elif '--renew' in sys.argv:
            result = renew_boot()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        else:
            print(json.dumps({'error': 'Use boot --check, boot --complete, or boot --renew'}, ensure_ascii=False))
            sys.exit(1)
    
    elif cmd == 'fuse':
        if '--check' in sys.argv:
            result = check_fuse()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0 if result['status'] != 'blown' else 1)
        elif '--incr' in sys.argv:
            idx = sys.argv.index('--incr')
            n = int(sys.argv[idx+1]) if idx+1 < len(sys.argv) else 1
            model = 'default'
            if '--model' in sys.argv:
                midx = sys.argv.index('--model')
                model = sys.argv[midx+1] if midx+1 < len(sys.argv) else 'default'
            token_type = 'input'
            if '--type' in sys.argv:
                tidx = sys.argv.index('--type')
                token_type = sys.argv[tidx+1] if tidx+1 < len(sys.argv) else 'input'
            result = incr_fuse(n, model, token_type)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0 if result['status'] != 'blown' else 1)
        elif '--set-limit' in sys.argv:
            idx = sys.argv.index('--set-limit')
            rmb = float(sys.argv[idx+1]) if idx+1 < len(sys.argv) else 10.0
            result = set_fuse_limit(rmb)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        elif '--reset' in sys.argv:
            result = reset_fuse()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        elif '--dynamic' in sys.argv:
            result = fuse_apply_dynamic()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        elif '--tier' in sys.argv:
            idx = sys.argv.index('--tier')
            tier = sys.argv[idx+1] if idx+1 < len(sys.argv) else 'std'
            result = fuse_set_tier(tier)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        elif '--pool' in sys.argv:
            result = fuse_pool_status()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        elif '--pool-incr' in sys.argv:
            idx = sys.argv.index('--pool-incr')
            agent = sys.argv[idx+1] if idx+1 < len(sys.argv) else 'codex'
            tokens_idx = idx+2
            tokens = int(sys.argv[tokens_idx]) if tokens_idx < len(sys.argv) else 0
            result = fuse_pool_incr(agent, tokens)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        elif '--actual' in sys.argv:
            thread_id = None
            if '--thread' in sys.argv:
                tidx = sys.argv.index('--thread')
                thread_id = sys.argv[tidx+1] if tidx+1 < len(sys.argv) else None
            result = fuse_actual_tokens(thread_id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        elif '--idle-check' in sys.argv:
            result = fuse_idle_check()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        elif '--idle-incr' in sys.argv:
            result = fuse_idle_incr()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        elif '--idle-reset' in sys.argv:
            result = fuse_idle_reset()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        elif '--overnight-start' in sys.argv:
            result = fuse_overnight_start()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        elif '--min-task-check' in sys.argv:
            result = fuse_min_task_check()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        elif '--graduated' in sys.argv:
            result = check_fuse_graduated()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        elif '--auto-track' in sys.argv:
            idx = sys.argv.index('--auto-track')
            agent = sys.argv[idx+1] if idx+1 < len(sys.argv) else 'codex'
            result = fuse_auto_track(agent)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0 if result['status'] == 'ok' else 1)
        else:
            print(json.dumps({'error': 'Use fuse --check|--incr|--set-limit|--reset|--dynamic|--tier|--pool|--pool-incr|--auto-track|--actual|--idle-check|--idle-incr|--idle-reset|--overnight-start|--min-task-check|--graduated'}, ensure_ascii=False))
            sys.exit(1)
    
    elif cmd == 'integrity':
        if '--check' in sys.argv:
            result = check_integrity()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0 if result['status'] == 'ok' else 1)
        elif '--update' in sys.argv:
            result = update_integrity()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        else:
            print(json.dumps({'error': 'Use integrity --check or integrity --update'}, ensure_ascii=False))
            sys.exit(1)
    
    elif cmd == 'heartbeat':
        if '--check' in sys.argv:
            result = check_heartbeat()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0 if result['status'] != 'stale' else 1)
        elif '--touch' in sys.argv:
            result = heartbeat_touch()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0 if result['status'] == 'ok' else 1)
        else:
            print(json.dumps({'error': 'Use heartbeat --check or heartbeat --touch'}, ensure_ascii=False))
            sys.exit(1)
    
    elif cmd == 'route':
        if '--task' in sys.argv:
            idx = sys.argv.index('--task')
            task = sys.argv[idx+1] if idx+1 < len(sys.argv) else ''
            if not task:
                print(json.dumps({'error': 'No task description'}, ensure_ascii=False))
                sys.exit(1)
            result = check_route(task)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            log_action('route_check', {'task': task})
            sys.exit(0 if result['status'] == 'ok' else 1)
        else:
            print(json.dumps({'error': 'Use route --task "description"'}, ensure_ascii=False))
            sys.exit(1)
    
    elif cmd == 'mode':
        if '--set' in sys.argv:
            idx = sys.argv.index('--set')
            mode_val = sys.argv[idx+1] if idx+1 < len(sys.argv) else ''
            result = set_mode(mode_val)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0 if result['status'] == 'ok' else 1)
        elif '--check' in sys.argv:
            mode_val = check_mode()
            print(json.dumps({'status': 'ok', 'mode': mode_val}, ensure_ascii=False))
            sys.exit(0)
        else:
            print(json.dumps({'mode': check_mode()}, ensure_ascii=False))
    
    elif cmd == 'task-reset':
        # Reset per-task spiral counter in auto mode
        TASK_MARKER = os.path.join(WD, 'task_marker')
        with open(TASK_MARKER, 'w', encoding='utf-8') as f:
            f.write(_now().isoformat())
        print(json.dumps({'status': 'ok', 'message': 'Task marker reset. Spiral counter zeroed.'}, ensure_ascii=False))
        sys.exit(0)
    
    elif cmd == 'spiral':
        if '--touch' in sys.argv:
            idx = sys.argv.index('--touch')
            filepath = sys.argv[idx+1] if idx+1 < len(sys.argv) else ''
            if not filepath:
                print(json.dumps({'error': 'No filepath'}, ensure_ascii=False))
                sys.exit(1)
            exempt = '--exempt' in sys.argv
            result = spiral_touch(filepath, exempt)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        elif '--check' in sys.argv:
            idx = sys.argv.index('--check')
            filepath = sys.argv[idx+1] if idx+1 < len(sys.argv) else ''
            result = check_spiral(filepath) if filepath else {'status': 'error', 'message': 'No filepath'}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0 if result['status'] != 'blocked' else 1)
        else:
            print(json.dumps({'error': 'Use spiral --touch <file> or spiral --check <file>'}, ensure_ascii=False))
            sys.exit(1)
    
    elif cmd == 'backup':
        if '--target' in sys.argv:
            idx = sys.argv.index('--target')
            filepath = sys.argv[idx+1] if idx+1 < len(sys.argv) else ''
            if not filepath:
                print(json.dumps({'error': 'No filepath'}, ensure_ascii=False))
                sys.exit(1)
            result = auto_backup(filepath)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0 if result['status'] == 'ok' else 1)
        else:
            print(json.dumps({'error': 'Use backup --target <filepath>'}, ensure_ascii=False))
            sys.exit(1)
    
    elif cmd == 'improve':
        if '--propose' in sys.argv:
            idx = sys.argv.index('--propose')
            desc = sys.argv[idx+1] if idx+1 < len(sys.argv) else ''
            cat = 'general'
            if '--category' in sys.argv:
                cidx = sys.argv.index('--category')
                cat = sys.argv[cidx+1] if cidx+1 < len(sys.argv) else 'general'
            result = propose_improvement(desc, cat)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        else:
            print(json.dumps({'error': 'Use improve --propose "description" [--category rules|skill|loop]'}, ensure_ascii=False))
            sys.exit(1)

    elif cmd == 'fail':
        if '--log' in sys.argv:
            idx = sys.argv.index('--log')
            desc = sys.argv[idx+1] if idx+1 < len(sys.argv) else ''
            task = None
            if '--task' in sys.argv:
                tidx = sys.argv.index('--task')
                task = sys.argv[tidx+1] if tidx+1 < len(sys.argv) else None
            result = log_failure(desc, task)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        elif '--read' in sys.argv:
            n = 5
            if '--n' in sys.argv:
                nidx = sys.argv.index('--n')
                n = int(sys.argv[nidx+1]) if nidx+1 < len(sys.argv) else 5
            result = read_failures(n)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        else:
            print(json.dumps({'error': 'Use fail --log "desc" [--task "name"] or fail --read [--n 5]'}, ensure_ascii=False))
            sys.exit(1)

    elif cmd == 'scope':
        if '--check' in sys.argv:
            result = check_scope()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0 if result['status'] == 'ok' else 1)
        else:
            print(json.dumps({'error': 'Use scope --check'}, ensure_ascii=False))
            sys.exit(1)

    elif cmd == 'verify':
        if '--check' in sys.argv:
            result = check_verify_recent()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0 if result['status'] == 'ok' else 1)
        else:
            print(json.dumps({'error': 'Use verify --check'}, ensure_ascii=False))
            sys.exit(1)

    elif cmd == 'locks':
        if '--expire' in sys.argv:
            result = expire_stale_locks()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
        else:
            print(json.dumps({'error': 'Use locks --expire'}, ensure_ascii=False))
            sys.exit(1)

    elif cmd == 'check-all':
        spiral_file = None
        if '--file' in sys.argv:
            idx = sys.argv.index('--file')
            spiral_file = sys.argv[idx+1] if idx+1 < len(sys.argv) else None
        result = check_all(spiral_file)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result['overall'] == 'go' else 1)
    
    else:
        result = check_all()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result['overall'] == 'go' else 1)

if __name__ == '__main__':
    main()
