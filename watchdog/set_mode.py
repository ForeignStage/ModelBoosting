#!/usr/bin/env python3
"""Set mode globally and propagate to all watched project watchdogs.
Usage: python set_mode.py interactive|auto
"""
import sys, os, json

GLOBAL_WD  = os.path.dirname(os.path.abspath(__file__))
GLOBAL_CFG = os.path.join(GLOBAL_WD, '..', 'config', 'watch_dirs.json')

def set_mode(wd, mode):
    try:
        open(os.path.join(wd, 'mode'), 'w', encoding='utf-8').write(mode)
        return True
    except Exception: return False

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('interactive', 'auto'):
        print('Usage: set_mode.py interactive|auto'); sys.exit(1)
    mode = sys.argv[1]
    ok = [GLOBAL_WD] if set_mode(GLOBAL_WD, mode) else []
    try:
        dirs = json.load(open(GLOBAL_CFG, encoding='utf-8')).get('watch', [])
        for d in dirs:
            wd = os.path.join(d, 'watchdog')
            if os.path.isdir(wd) and set_mode(wd, mode): ok.append(wd)
    except Exception: pass
    print(f'[MODE] {mode} -- {len(ok)} watchdog(s) updated')
    for p in ok: print(f'  {p}')

if __name__ == '__main__':
    main()
