#!/usr/bin/env python3
"""
API Contract Extractor -- Auto-generate api_contract.json from existing codebase.
Bootstrapping tool: run once, review output, then contract_check.py enforces against it.
Usage: python contract_extractor.py <project_root> [--output config/api_contract.json]
"""
import ast, os, sys, json, re
from datetime import datetime

def extract_backend(project_root):
    """Extract FastAPI endpoint definitions from backend .py files."""
    endpoints = []
    backend_dir = os.path.join(project_root, 'backend')
    if not os.path.isdir(backend_dir):
        return endpoints

    for root, _, files in os.walk(backend_dir):
        if any(s in root for s in ['__pycache__', '.git', 'venv', '.venv']):
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

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Match @app.get("/path"), @router.post("/path"), etc.
                    method = path = None
                    if isinstance(node.func, ast.Attribute):
                        attr = node.func.attr
                        if attr in ('get', 'post', 'put', 'delete', 'patch'):
                            method = attr.upper()
                            if node.args:
                                first = node.args[0]
                                if isinstance(first, ast.Constant):
                                    path = first.value
                    # Also detect @app.route("/path", methods=["GET"])
                    elif isinstance(node.func, ast.Name) and node.func.id == 'route':
                        if node.args:
                            first = node.args[0]
                            if isinstance(first, ast.Constant):
                                path = first.value
                        for kw in node.keywords:
                            if kw.arg == 'methods' and isinstance(kw.value, ast.List):
                                method = [e.value for e in kw.value.elts if isinstance(e, ast.Constant)]

                    if method and path:
                        endpoints.append({'method': method if isinstance(method, str) else method[0], 'path': path, 'file': os.path.relpath(fp, project_root)})

    return endpoints

def extract_frontend(project_root):
    """Extract fetch/axios calls from static/ JS files."""
    calls = []
    static_dir = os.path.join(project_root, 'static')
    if not os.path.isdir(static_dir):
        return calls

    for root, _, files in os.walk(static_dir):
        if any(s in root for s in ['node_modules', '.git']):
            continue
        for fn in files:
            if not fn.endswith(('.js', '.ts', '.html')):
                continue
            fp = os.path.join(root, fn)
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                continue

            # Match fetch("/api/...") and fetch('/api/...')
            for m in re.finditer(r'fetch\s*\(\s*["\']([^"\']+)["\']', content):
                url = m.group(1)
                if url.startswith('/api/') or url.startswith('http'):
                    calls.append({'call': f'fetch({url})', 'file': os.path.relpath(fp, project_root)})

            # Match axios.get("/api/...") etc.
            for m in re.finditer(r'axios\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']', content):
                method = m.group(1).upper()
                url = m.group(2)
                if url.startswith('/api/') or url.startswith('http'):
                    calls.append({'call': f'axios.{method.lower()}({url})', 'file': os.path.relpath(fp, project_root)})

            # Match plain path references like "/api/..." in template literals
            for m in re.finditer(r'["\'](/api/[^"\']+)["\']', content):
                url = m.group(1)
                calls.append({'call': f'reference({url})', 'file': os.path.relpath(fp, project_root)})

    return calls

def main():
    project_root = os.getcwd()
    output_path = os.path.join('config', 'api_contract.json')

    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == '--output' and i+1 < len(args):
            output_path = args[i+1]
        elif os.path.isdir(a):
            project_root = a

    endpoints = extract_backend(project_root)
    frontend_calls = extract_frontend(project_root)

    contract = {
        'version': '1.0',
        'generated': datetime.now().isoformat(),
        'project': project_root,
        'endpoints': endpoints,
        'frontend_calls': frontend_calls,
        '_note': 'Review this file manually. Add schemas, params, and response types. contract_check.py compares backend/frontend against this.'
    }

    os.makedirs(os.path.dirname(os.path.join(project_root, output_path)), exist_ok=True)
    out_full = os.path.join(project_root, output_path)
    with open(out_full, 'w', encoding='utf-8') as f:
        json.dump(contract, f, indent=2, ensure_ascii=False)

    print(f'Contract extracted: {len(endpoints)} endpoints, {len(frontend_calls)} frontend calls')
    print(f'Written: {out_full}')
    print('Review and edit this file before enforcing with contract_check.py')

if __name__ == '__main__':
    main()
