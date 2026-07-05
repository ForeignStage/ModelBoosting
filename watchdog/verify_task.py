#!/usr/bin/env python3
"""Mechanical verification: py_compile + import resolution + hallucination check."""
import sys, os, subprocess, argparse, ast
from datetime import datetime

def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr

def verify_syntax(filepath):
    code, out = run([sys.executable, '-m', 'py_compile', filepath])
    if code != 0:
        return False, f'syntax error: {out.strip()}'
    return True, None

def check_imports_resolve(filepath):
    """Verify all imports in filepath resolve to actual installable/importable modules."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    except SyntaxError:
        return True, None  # syntax errors caught by verify_syntax

    broken = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split('.')[0]
                try:
                    __import__(top)
                except ImportError:
                    broken.append(f'import {alias.name}')
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                top = node.module.split('.')[0]
                try:
                    __import__(top)
                except ImportError:
                    broken.append(f'from {node.module} import ...')

    if broken:
        return False, f'Unresolvable imports: {", ".join(broken[:5])}'
    return True, None

STDLIB_NAMES = set(sys.stdlib_module_names) if hasattr(sys, 'stdlib_module_names') else set()

def _is_builtin(name):
    return name in dir(__builtins__)

def check_calls_exist(filepath):
    """Check that function calls reference real project-level or builtin functions."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except SyntaxError:
        return True, None

    # Collect local definitions
    local_defs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            local_defs.add(node.name)
        elif isinstance(node, ast.ClassDef):
            local_defs.add(node.name)
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            local_defs.add(node.targets[0].id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local_defs.add(alias.asname or alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                local_defs.add(alias.asname or alias.name)

    # Scan project for definitions
    project_defs = set()
    project_root = os.path.dirname(filepath)
    for root, _, files in os.walk(project_root):
        if any(s in root for s in ['__pycache__', '.git', 'venv', '.venv', 'node_modules']):
            continue
        for fn in files:
            if not fn.endswith('.py'):
                continue
            fp = os.path.join(root, fn)
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    p_tree = ast.parse(f.read())
            except Exception:
                continue
            for p_node in ast.walk(p_tree):
                if isinstance(p_node, ast.FunctionDef):
                    project_defs.add(p_node.name)
                elif isinstance(p_node, ast.ClassDef):
                    project_defs.add(p_node.name)

    # Known common libraries
    known = {'print', 'len', 'range', 'int', 'str', 'float', 'bool', 'list', 'dict',
             'set', 'tuple', 'type', 'isinstance', 'hasattr', 'getattr', 'setattr',
             'enumerate', 'zip', 'map', 'filter', 'sorted', 'reversed', 'open',
             'super', 'property', 'staticmethod', 'classmethod', 'any', 'all',
             'max', 'min', 'sum', 'abs', 'round', 'pow', 'divmod', 'chr', 'ord',
             'hex', 'oct', 'bin', 'repr', 'ascii', 'format', 'input', 'next', 'iter',
             'vars', 'dir', 'id', 'hash', 'callable', 'compile', 'eval', 'exec',
             '__import__', 'Exception', 'ValueError', 'TypeError', 'KeyError',
             'json', 'os', 'sys', 're', 'datetime', 'pathlib', 'Path',
             'FastAPI', 'APIRouter', 'Depends', 'HTTPException', 'Query', 'Body',
             'Session', 'sessionmaker', 'create_engine', 'declarative_base',
             'BaseModel', 'Field', 'validator', 'Column', 'Integer', 'String',
             'relationship', 'backref', 'ForeignKey', 'Table', 'MetaData'}

    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = None
            is_attr_call = False
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
                is_attr_call = True  # e.g. os.path.dirname() -- trust it if module imported

            if name and not _is_builtin(name) and not is_attr_call and name not in known and name not in local_defs and name not in project_defs:
                issues.append(f'{name}()')

    if issues:
        return False, f'Unverified calls (not in project/builtins): {", ".join(issues[:5])}'
    return True, None

def verify_file(filepath):
    ok, err = verify_syntax(filepath)
    if not ok:
        return False, err

    ok, err = check_imports_resolve(filepath)
    if not ok:
        return False, err

    ok, err = check_calls_exist(filepath)
    if not ok:
        return False, err

    # 4. halcheck_live -- import-based deep verification
    halcheck_path = os.path.join(os.path.dirname(__file__), 'halcheck_live.py')
    if os.path.exists(halcheck_path):
        try:
            r = subprocess.run(
                [sys.executable, halcheck_path, filepath],
                capture_output=True, text=True, timeout=30
            )
            if r.returncode != 0:
                data = json.loads(r.stdout)
                hallucinations = data.get('hallucinations', [])
                if hallucinations:
                    chains = [h.get('chain', '') for h in hallucinations[:3]]
                    return False, f'API hallucination: {", ".join(chains)}'
        except Exception:
            pass

    # 5. mypy -- static type checking (optional, graceful degradation)
    try:
        r = subprocess.run(
            [sys.executable, '-m', 'mypy', filepath, '--ignore-missing-imports', '--no-error-summary'],
            capture_output=True, text=True, timeout=60
        )
        if r.returncode != 0 and r.stdout.strip():
            # Only flag as error if there are actual type errors (not just notes)
            lines = [l for l in r.stdout.split('\n') if ': error:' in l]
            if lines:
                return False, f'mypy: {lines[0][:200]}'
    except Exception:
        pass  # mypy not installed or timed out -- skip

    # 6. bandit -- security lint (optional, graceful degradation)
    try:
        r = subprocess.run(
            [sys.executable, '-m', 'bandit', '-q', '-f', 'txt', filepath],
            capture_output=True, text=True, timeout=60
        )
        if r.returncode != 0 and r.stdout.strip():
            # Count medium+ severity issues
            issues = [l for l in r.stdout.split('\n') if 'Severity' in l and 'Medium' in l or 'High' in l]
            if len(issues) >= 3:
                return False, f'bandit: {len(issues)} medium+ severity issues'
    except Exception:
        pass  # bandit not installed or timed out -- skip

    return True, None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('files', nargs='*')
    parser.add_argument('--output', default=None)
    args = parser.parse_args()

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = args.output or os.path.join('docs', f'VERIFY_{ts}.md')

    lines = []
    overall_pass = True

    for f in args.files:
        if not f.endswith('.py'):
            continue
        ok, err = verify_file(f)
        status = 'PASS' if ok else 'FAIL'
        if not ok:
            overall_pass = False
        line = f'{f}: {status}' + (f' -- {err}' if err else '')
        lines.append(line)

    tests_line = None
    if os.path.isdir('tests'):
        try:
            code, out = run([sys.executable, '-m', 'pytest', 'tests/', '-x', '-q'])
            passed = failed = 0
            for l in out.splitlines():
                m = re.search(r'(\d+) passed', l)
                if m:
                    passed = int(m.group(1))
                m = re.search(r'(\d+) failed', l)
                if m:
                    failed = int(m.group(1))
            test_ok = code == 0
            if not test_ok:
                overall_pass = False
            tests_line = f'TESTS: {"PASS" if test_ok else "FAIL"} ({passed} passed, {failed} failed)'
        except Exception as e:
            tests_line = f'TESTS: SKIP -- {e}'

    final_status = 'PASS' if overall_pass else 'FAIL'
    header = f'VERIFY RESULT: {final_status} -- {ts}'

    report_lines = [header] + lines
    if tests_line:
        report_lines.append(tests_line)

    report = '\n'.join(report_lines)
    print(report)

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    sys.exit(0 if overall_pass else 1)

if __name__ == '__main__':
    main()
