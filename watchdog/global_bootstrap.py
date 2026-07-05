#!/usr/bin/env python3
"""Global Bootstrap -- enforce constitution compliance on any project directory.
Run once per project: python global_bootstrap.py [project_root]
Creates: watchdog/ shim, CLAUDE.md reference, adds project to watch_dirs.json.
"""
import sys, os, json, shutil
from datetime import datetime

_wd = os.path.dirname(os.path.abspath(__file__))
_godcreating = os.path.join(_wd, '..')
GLOBAL_CFG = os.path.join(_godcreating, 'config', 'watch_dirs.json')
AGENTS_MD  = os.path.join(_godcreating, '..', '..', 'AGENTS.md')

WATCHDOG_SHIM = '''\
#!/usr/bin/env python3
"""Shim -- delegates to global watchdog. Do not edit."""
import sys, os
sys.path.insert(0, r'{watchdog_dir}')
from enforce import *  # noqa
if __name__ == '__main__':
    import enforce as _m
    sys.exit(_m.main() if hasattr(_m, 'main') else 0)
'''.format(watchdog_dir=_wd.replace('\\', '\\\\'))

CLAUDE_APPEND = f"""
## Constitution Reference (auto-bootstrapped {datetime.now().date()})
- Global rules: `{AGENTS_MD}` (overrides any local rules)
- Shared watchdog: `{_wd}\\`
- Discipline skill: `{os.path.join(_godcreating, 'skills', 'SKILL_DEEPSEEK_DISCIPLINE.md')}`
"""

def bootstrap(root):
    root = os.path.abspath(root)
    print(f'[BOOTSTRAP] {root}')

    # 1. Create watchdog/ with shim if not real enforce.py present
    wd = os.path.join(root, 'watchdog')
    os.makedirs(wd, exist_ok=True)
    shim = os.path.join(wd, 'enforce_shim.py')
    if not os.path.exists(os.path.join(wd, 'enforce.py')):
        src = os.path.join(_wd, 'enforce.py')
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(wd, 'enforce.py'))
            print(f'  [OK] watchdog/enforce.py copied from global')
    # Always write the shim for reference
    with open(shim, 'w', encoding='utf-8') as f: f.write(WATCHDOG_SHIM)

    # 2. Ensure docs/ exists
    os.makedirs(os.path.join(root, 'docs'), exist_ok=True)

    # 3. Add CLAUDE.md reference if not present
    claude_md = os.path.join(root, 'CLAUDE.md')
    if os.path.exists(claude_md):
        content = open(claude_md, 'r', encoding='utf-8').read()
        if 'AgentHub' not in content:
            with open(claude_md, 'a', encoding='utf-8') as f: f.write(CLAUDE_APPEND)
            print(f'  [OK] CLAUDE.md updated with AgentHub reference')
    else:
        with open(claude_md, 'w', encoding='utf-8') as f:
            f.write(f'# Project Rules\nSee `{AGENTS_MD}` for full constitution.\n{CLAUDE_APPEND}')
        print(f'  [OK] CLAUDE.md created')

    # 4. Add project to global watch_dirs.json
    try:
        cfg = json.load(open(GLOBAL_CFG, 'r', encoding='utf-8'))
        if root not in cfg.get('watch', []):
            cfg.setdefault('watch', []).append(root)
            json.dump(cfg, open(GLOBAL_CFG, 'w', encoding='utf-8'), indent=2)
            print(f'  [OK] Added to watch_dirs.json -- fs_watcher now monitors this project')
    except Exception as e:
        print(f'  [WARN] watch_dirs.json: {e}')

    print(f'[BOOTSTRAP] Done. Restart fs_watcher to pick up new watch dir.')

if __name__ == '__main__':
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    bootstrap(root)
