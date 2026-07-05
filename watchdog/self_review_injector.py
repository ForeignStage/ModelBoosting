#!/usr/bin/env python3
"""
Self-Review Injector -- Opus-4.8 compensation layer.
Deepseek cannot self-review natively. After each file write, this script:
  1. Reads the changed files
  2. Generates a review checklist (edge cases, type safety, error handling)
  3. Writes CC_WAKEUP.md / CODEX_WAKEUP.md with review prompts
The agent reads these on next session/turn and is prompted to self-correct.

Usage: python self_review_injector.py <filepath> --agent codex|claude_code [--project-root <path>]
"""
import os, sys, json, re, ast
from datetime import datetime

PROJECTS_ROOT = r"E:\AgentHub\AgentProjects"


def analyze_file(filepath):
    """Quick static analysis of a Python file. Returns review items."""
    items = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception:
        return items

    # Check for bare except clauses
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            items.append("Bare `except:` found -- should catch specific exception types")
            break

    # Check for functions with no docstring
    funcs_without_docs = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            if not (node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                funcs_without_docs.append(node.name)
    if len(funcs_without_docs) > 2:
        items.append(f"{len(funcs_without_docs)} functions without docstrings: {', '.join(funcs_without_docs[:3])}...")

    # Check for functions > 50 lines (potential complexity)
    try:
        lines = source.split('\n')
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) and node.end_lineno:
                func_lines = node.end_lineno - node.lineno
                if func_lines > 50:
                    items.append(f"Large function '{node.name}' ({func_lines} lines) -- consider splitting")
    except Exception:
        pass

    # Check for TODO/FIXME/HACK
    for m in re.finditer(r'(TODO|FIXME|HACK):', source):
        items.append(f"Pending marker: {m.group(0)} at line {source[:m.start()].count(chr(10)) + 1}")
        break

    # Check for return type hints (Python 3.9+)
    has_return_annotations = 0
    total_funcs = 0
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            total_funcs += 1
            if node.returns:
                has_return_annotations += 1
    if total_funcs > 0 and has_return_annotations < total_funcs:
        items.append(f"Return type hints: {has_return_annotations}/{total_funcs} functions annotated")

    # Check for hardcoded secrets/keys
    if re.search(r'(password|secret|api_key|token)\s*=\s*["\'][^"\']{8,}["\']', source, re.IGNORECASE):
        items.append("Potential hardcoded credential detected (password/api_key/token = string literal)")

    return items


def find_project(filepath):
    """Find the AgentProject root for a given file."""
    for proj in os.listdir(PROJECTS_ROOT):
        proj_path = os.path.join(PROJECTS_ROOT, proj)
        if os.path.isdir(proj_path) and filepath.startswith(proj_path):
            return proj_path
    return os.path.dirname(filepath)


def inject_review(project_root, agent, filepath, items):
    """Write review prompt to agent's wakeup file."""
    docs_dir = os.path.join(project_root, 'docs')
    os.makedirs(docs_dir, exist_ok=True)

    agent_key = 'CC' if agent in ('claude_code', 'cc') else 'CODEX'
    wakeup_file = os.path.join(docs_dir, f'{agent_key}_WAKEUP.md')

    content = f"# SELF-REVIEW INJECTION -- {datetime.now().isoformat()}\n\n"
    content += f"File changed: {os.path.basename(filepath)}\n\n"
    content += "## Review Checklist\n"
    for i, item in enumerate(items, 1):
        content += f"{i}. {item}\n"
    if not items:
        content += "- No automated issues detected. Manual review still recommended.\n"
    content += f"\n## Action Required\n- Review the file for correctness, error handling, and edge cases\n"
    content += f"- Fix any issues before marking task COMPLETED\n"

    with open(wakeup_file, 'w', encoding='utf-8') as f:
        f.write(content)

    return wakeup_file


def main():
    agent = 'codex'
    filepath = None
    project_root = None

    for i, a in enumerate(sys.argv[1:]):
        if a == '--agent' and i + 1 < len(sys.argv):
            agent = sys.argv[i + 2]
        elif a == '--project-root' and i + 1 < len(sys.argv):
            project_root = sys.argv[i + 2]
        elif os.path.exists(a):
            filepath = a

    if not filepath:
        print(json.dumps({'status': 'skipped', 'reason': 'no filepath'}, ensure_ascii=False))
        sys.exit(0)

    if not project_root:
        project_root = find_project(filepath)

    items = analyze_file(filepath)
    wakeup_path = inject_review(project_root, agent, filepath, items)

    result = {
        'file': filepath,
        'agent': agent,
        'review_items': len(items),
        'items': items[:5],
        'wakeup_file': wakeup_path,
        'status': 'injected',
        'timestamp': datetime.now().isoformat()
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0)


if __name__ == '__main__':
    main()
