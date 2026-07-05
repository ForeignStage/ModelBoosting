#!/usr/bin/env python3
"""Code Quality Gate --runs flake8/pylint on changed files before verify passes.
Usage: python code_quality_gate.py [file1.py file2.py ...] [--scope project_root]
Exit 0 = pass. Exit 1 = issues found (see output).
"""
import sys, os, subprocess

IGNORE = 'E501,W503,W504'  # line length and line-break conventions --subjective

def run(tool, args):
    try:
        r = subprocess.run([tool] + args, creationflags=0x08000000, capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout + r.stderr
    except FileNotFoundError: return None, f'{tool} not installed'
    except subprocess.TimeoutExpired: return 1, f'{tool} timeout'

def check_files(files):
    issues = []
    for f in files:
        if not f.endswith('.py') or not os.path.exists(f): continue
        rc, out = run('flake8', [f'--ignore={IGNORE}', f])
        if rc is None:
            rc, out = run(PYTHONW_EXE, ['-m', 'py_compile', f])
            label = 'syntax'
        else:
            label = 'flake8'
        if rc and rc != 0 and out.strip():
            issues.append(f'[{label}] {f}:\n{out.strip()}')
    return issues

def files_from_scope(root):
    scope = os.path.join(root, 'docs', 'SCOPE_active.md')
    if not os.path.exists(scope): return []
    import re
    text = open(scope, encoding='utf-8').read()
    section = text.split('Will write', 1)[-1].split('Done when')[0] if 'Will write' in text else ''
    return [f.strip().lstrip('---') for f in section.splitlines()
            if f.strip() and f.strip().endswith('.py')]

def main():
    files, root = [], os.getcwd()
    for a in sys.argv[1:]:
        if a == '--scope': pass
        elif os.path.isdir(a): root = a
        elif a.endswith('.py'): files.append(a)
    if not files: files = files_from_scope(root)
    if not files: print('[QUALITY] No .py files to check.'); sys.exit(0)

    issues = check_files(files)
    if issues:
        for i in issues: print(i)
        print(f'\n[QUALITY] {len(issues)} file(s) have issues --fix before COMPLETED.')
        sys.exit(1)
    print(f'[QUALITY] {len(files)} file(s) passed.')

if __name__ == '__main__':
    main()

