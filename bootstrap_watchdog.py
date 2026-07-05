#!/usr/bin/env python3
"""Bootstrap watchdog structure into any AgentHub project.
Usage: python bootstrap_watchdog.py [project_path]  (default: current dir)
"""
import sys, os, shutil, json
from datetime import datetime

SHARED = os.path.dirname(os.path.abspath(__file__))

def bootstrap(project_path):
    project_path = os.path.abspath(project_path)
    print(f"Bootstrapping: {project_path}")

    for d in ['watchdog/locks', 'docs', 'backups']:
        os.makedirs(os.path.join(project_path, d), exist_ok=True)

    # Copy watchdog scripts from _shared/watchdog/ (self-contained canonical source)
    src_watchdog = os.path.join(SHARED, 'watchdog')
    for script in ['enforce.py', 'verify_task.py', 'web_fetch.py']:
        src = os.path.join(src_watchdog, script)
        dst = os.path.join(project_path, 'watchdog', script)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            print(f"  Copied {script}")
        elif os.path.exists(dst):
            print(f"  Exists {script} (skipped)")
        else:
            print(f"  WARN: {src} not found")

    # Copy shared cheatsheet
    shutil.copy2(os.path.join(SHARED, 'AGENTS_CHEATSHEET.md'),
                 os.path.join(project_path, 'docs', 'AGENTS_CHEATSHEET.md'))
    print("  Copied AGENTS_CHEATSHEET.md")

    # Copy loop templates (substitute PROJECT_PATH placeholder)
    for tmpl, dest in [('CLAUDE_LOOP_template.md', 'CLAUDE_LOOP.md'),
                       ('CODEX_LOOP_template.md', 'CODEX_LOOP.md')]:
        src = os.path.join(SHARED, tmpl)
        dst = os.path.join(project_path, dest)
        if os.path.exists(src) and not os.path.exists(dst):
            content = open(src, encoding='utf-8').read()
            content = content.replace('[PROJECT_PATH]', project_path)
            open(dst, 'w', encoding='utf-8').write(content)
            print(f"  Created {dest}")
        elif os.path.exists(dst):
            print(f"  Exists {dest} (skipped)")

    # Write project config for enforce.py
    config = {
        'agents_md': r'E:/AgentHub/AGENTS.md',
        'backup_dir': os.path.join(project_path, 'backups'),
        'project_root': project_path
    }
    config_path = os.path.join(project_path, 'watchdog', 'config.json')
    if not os.path.exists(config_path):
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        print("  Created watchdog/config.json")

    # Initialize fuse
    fuse_path = os.path.join(project_path, 'watchdog', 'fuse_rmb.json')
    if not os.path.exists(fuse_path):
        with open(fuse_path, 'w') as f:
            json.dump({'spent': 0.0, 'limit': 10.0}, f)
        print("  Initialized fuse_rmb.json (limit: 10 RMB)")

    print(f"\nDone. Next steps:")
    print(f"  cd {project_path}")
    print(f"  python watchdog/enforce.py boot --complete")

if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    bootstrap(path)
