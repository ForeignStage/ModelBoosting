#!/usr/bin/env python3
"""
API Contract Checker -- Cross-validate backend endpoints vs frontend API calls.
Compares actual code against config/api_contract.json (authoritative source).
Usage: python contract_check.py --agent codex|claude_code <project_root>
Exit 0 = no issues. Exit 1 = mismatches found.
"""
import os, sys, json, re
from datetime import datetime

def find_contract(project_root):
    """Find api_contract.json in project config dir."""
    paths = [
        os.path.join(project_root, 'config', 'api_contract.json'),
        os.path.join(project_root, 'docs', 'api_contract.json'),
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

def extract_backend_endpoints(project_root):
    """Extract FastAPI route decorators from backend .py files."""
    import ast
    endpoints = []
    for scan_dir in ['backend', 'api']:
        scan_path = os.path.join(project_root, scan_dir)
        if not os.path.isdir(scan_path):
            continue
        for root, _, files in os.walk(scan_path):
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
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                        if node.func.attr in ('get', 'post', 'put', 'delete', 'patch'):
                            method = node.func.attr.upper()
                            if node.args and isinstance(node.args[0], ast.Constant):
                                endpoints.append({
                                    'method': method,
                                    'path': node.args[0].value,
                                    'file': os.path.relpath(fp, project_root)
                                })
    return endpoints

def extract_frontend_calls(project_root):
    """Extract API URL references from static/ JS/HTML files."""
    calls = []
    for scan_dir in ['static', 'frontend', 'templates']:
        scan_path = os.path.join(project_root, scan_dir)
        if not os.path.isdir(scan_path):
            continue
        for root, _, files in os.walk(scan_path):
            if any(s in root for s in ['node_modules', '.git']):
                continue
            for fn in files:
                if not fn.endswith(('.js', '.ts', '.html', '.jsx', '.tsx', '.css')):
                    continue
                fp = os.path.join(root, fn)
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        content = f.read()
                except Exception:
                    continue
                # Find fetch/axios URL references
                for m in re.finditer(r'(?:fetch|axios\.\w+)\s*\(\s*["\']([^"\']+)["\']', content):
                    url = m.group(1)
                    if '/api/' in url or url.startswith('http'):
                        calls.append({'url': url, 'file': os.path.relpath(fp, project_root)})
                # Find bare API path strings
                for m in re.finditer(r'["\'](/api/[^"\']+)["\']', content):
                    calls.append({'url': m.group(1), 'file': os.path.relpath(fp, project_root)})
    # Deduplicate
    seen = set()
    unique = []
    for c in calls:
        key = (c['url'], c['file'])
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique

def match_url(url, endpoints):
    """Check if a frontend URL matches any backend endpoint path."""
    # Exact match
    for ep in endpoints:
        if url == ep['path']:
            return ep
    # Prefix match (e.g. /api/users/123 matches /api/users/{id})
    for ep in endpoints:
        ep_path_no_params = ep['path'].split('?')[0]
        url_path = url.split('?')[0]
        # If endpoint has path params, do prefix match
        if '{' in ep_path_no_params:
            prefix = ep_path_no_params.split('{')[0].rstrip('/')
            if url_path.startswith(prefix):
                return ep
    return None

def check(project_root, agent):
    """Run contract check. Returns (issues, contract_path)."""
    contract_path = find_contract(project_root)
    if not contract_path:
        return [], None  # No contract = no check (optional feature)

    try:
        with open(contract_path, 'r', encoding='utf-8') as f:
            contract = json.load(f)
    except Exception:
        return [{'type': 'CONTRACT_CORRUPT', 'message': f'Could not parse {contract_path}'}], contract_path

    issues = []

    if agent in ('codex', 'cx'):
        # Codex modifies backend -- check frontend calls against new endpoints
        backend_eps = extract_backend_endpoints(project_root)
        frontend_calls = extract_frontend_calls(project_root)

        # Check: every backend endpoint has a matching frontend call OR is documented
        contract_paths = {ep.get('path', '') for ep in contract.get('endpoints', [])}
        for ep in backend_eps:
            path = ep['path']
            # Check if any frontend call references this path
            matched = match_url(path, [{'path': c['url']} for c in frontend_calls])
            if not matched:
                issues.append({
                    'type': 'UNCALLED_ENDPOINT',
                    'message': f'Backend defines {ep["method"]} {path} but no frontend calls it',
                    'file': ep['file']
                })

        # Check: every frontend call has a backend endpoint
        for fc in frontend_calls:
            url = fc['url']
            if not url.startswith('/api/'):
                continue
            matched = match_url(url, [{'path': ep['path']} for ep in backend_eps])
            if not matched:
                issues.append({
                    'type': 'ORPHAN_FRONTEND_CALL',
                    'message': f'Frontend calls {url} but no backend endpoint found',
                    'file': fc['file']
                })

    elif agent in ('claude_code', 'cc'):
        # CC modifies frontend -- check that new frontend calls have backend endpoints
        frontend_calls = extract_frontend_calls(project_root)
        backend_eps = extract_backend_endpoints(project_root)

        for fc in frontend_calls:
            url = fc['url']
            if not url.startswith('/api/'):
                continue
            matched = match_url(url, [{'path': ep['path']} for ep in backend_eps])
            if not matched:
                issues.append({
                    'type': 'UNMATCHED_FRONTEND_CALL',
                    'message': f'Frontend {fc["file"]} calls {url} -- no matching backend endpoint found',
                    'file': fc['file']
                })

    return issues, contract_path


def main():
    agent = 'codex'
    project_root = os.getcwd()

    for i, a in enumerate(sys.argv[1:]):
        if a == '--agent' and i+1 < len(sys.argv):
            agent = sys.argv[i+2]
        elif os.path.isdir(a):
            project_root = a

    issues, contract_path = check(project_root, agent)

    result = {
        'agent': agent,
        'contract': contract_path,
        'issues': issues,
        'count': len(issues),
        'status': 'PASS' if not issues else 'FAIL',
        'timestamp': datetime.now().isoformat()
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(1 if issues else 0)


if __name__ == '__main__':
    main()
