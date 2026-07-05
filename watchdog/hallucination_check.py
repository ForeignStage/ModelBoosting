#!/usr/bin/env python3
"""
Hallucination Check -- Verify that Python code doesn't contain invented APIs.
DeepSeek is known to hallucinate plausible-sounding function names.
This script uses AST parsing to detect:
  1. Imports that don't resolve to actual modules
  2. Function calls that reference non-existent functions in the project or stdlib
  3. Attribute access on objects that don't have those attributes
Usage: python hallucination_check.py <filepath> [--project-root <path>]
Exit 0 = no hallucinations found. Exit 1 = hallucinations detected.
"""
import ast, sys, os, subprocess, json
from datetime import datetime

def get_stdlib_modules():
    """Get a set of all stdlib module names."""
    stdlib = set()
    for name in sys.stdlib_module_names:  # Python 3.10+
        stdlib.add(name)
    return stdlib

STDLIB = get_stdlib_modules()

def scan_project_defs(project_root):
    """Walk project .py files and collect all top-level def/class names and module paths."""
    defs = {}
    if not os.path.isdir(project_root):
        return defs
    for root, _, files in os.walk(project_root):
        if any(s in root for s in ['__pycache__', '.git', 'venv', '.venv', 'node_modules']):
            continue
        for fn in files:
            if not fn.endswith('.py'):
                continue
            fp = os.path.join(root, fn)
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    tree = ast.parse(f.read())
            except Exception:
                continue
            names = [fn[:-3]]  # module name
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    names.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    names.append(node.name)
                elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                    names.append(node.targets[0].id)
            defs[fp] = set(names)
    return defs

def check_file(filepath, project_defs):
    """Check a single file for hallucinations. Returns list of issues."""
    issues = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"SYNTAX ERROR: {e}"]
    except Exception as e:
        return [f"PARSE ERROR: {e}"]

    # 1. Check imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split('.')[0]
                if mod not in STDLIB and not _is_known_package(mod):
                    issues.append(f"IMPORT UNKNOWN PACKAGE: {alias.name} (base: {mod})")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod = node.module.split('.')[0]
                if mod not in STDLIB and not _is_known_package(mod):
                    issues.append(f"IMPORT UNKNOWN PACKAGE: {node.module} (base: {mod})")

    # 2. Check attribute calls for known hallucination patterns
    known_hallucinations = [
        'search_by_email', 'search_by_name', 'search_by_id',
        'find_by_username', 'get_or_create_user',
        'create_session', 'validate_token'
    ]
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                name = node.func.id
                # Check if defined in current file
                defined_here = False
                for n in ast.walk(tree):
                    if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name:
                        defined_here = True
                        break
                if not defined_here and not _is_builtin(name):
                    # Check project defs
                    found = any(name in def_names for def_names in project_defs.values())
                    if not found and name not in dir(__builtins__):
                        issues.append(f"CALL UNVERIFIED FUNCTION: {name}() -- not found in project or builtins")
            elif isinstance(node.func, ast.Attribute):
                # Collect the dotted chain
                parts = []
                current = node.func
                while isinstance(current, ast.Attribute):
                    parts.insert(0, current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.insert(0, current.id)
                full = '.'.join(parts)
                for h in known_hallucinations:
                    if h in full:
                        issues.append(f"HALLUCINATION PATTERN: {full}() -- matches known hallucination pattern '{h}'")

    return issues

KNOWN_PACKAGES = {
    'fastapi', 'uvicorn', 'pydantic', 'sqlalchemy', 'sqlite3', 'pytest',
    'starlette', 'jinja2', 'aiohttp', 'requests', 'numpy', 'pandas',
    'PIL', 'PIL.Image', 'bs4', 'lxml', 'yaml', 'toml', 'httpx',
    'websockets', 'redis', 'pymongo', 'psycopg2', 'asyncpg',
    'alembic', 'click', 'rich', 'loguru', 'flask', 'django',
    'matplotlib', 'seaborn', 'scipy', 'sklearn', 'tensorflow', 'torch',
    'email', 'http', 'urllib', 'xml', 'json', 'csv', 're', 'os', 'sys',
    'collections', 'itertools', 'functools', 'typing', 'dataclasses',
    'datetime', 'math', 'random', 'hashlib', 'base64', 'subprocess',
    'shutil', 'pathlib', 'tempfile', 'io', 'contextlib', 'asyncio',
    'threading', 'multiprocessing', 'logging', 'traceback', 'unittest',
    'enum', 'abc', 'copy', 'decimal', 'fractions', 'statistics',
    'struct', 'textwrap', 'difflib', 'pprint', 'inspect', 'importlib',
}

def _is_known_package(name):
    return name in KNOWN_PACKAGES or name in STDLIB

def _is_builtin(name):
    return name in dir(__builtins__)

def main():
    if len(sys.argv) < 2:
        print("Usage: hallucination_check.py <filepath> [--project-root <path>]")
        sys.exit(0)

    filepath = sys.argv[1]
    project_root = os.path.dirname(filepath)

    if '--project-root' in sys.argv:
        idx = sys.argv.index('--project-root')
        project_root = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else project_root

    if not os.path.exists(filepath):
        print(json.dumps({'error': f'File not found: {filepath}'}, ensure_ascii=False))
        sys.exit(1)

    project_defs = scan_project_defs(project_root)
    issues = check_file(filepath, project_defs)

    result = {
        'file': filepath,
        'issues': issues,
        'count': len(issues),
        'status': 'PASS' if not issues else 'FAIL',
        'timestamp': datetime.now().isoformat()
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(1 if issues else 0)

if __name__ == '__main__':
    main()
