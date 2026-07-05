#!/usr/bin/env python3
"""Context Injector -- finds relevant code snippets from project and injects as reference.
Compensates for deepseek's 'implicit understanding' gap by making context explicit.
Usage: python context_injector.py "[task]" [project_root] [--max N]
Writes: docs/CONTEXT_INJECTION.md (read this before executing task)
"""
import sys, os, re, ast

MAX_SNIPPETS = 5
MAX_LINES = 40  # max lines per snippet

def keywords(task):
    # Extract meaningful tokens (skip common words)
    stop = {'the','a','an','to','for','in','of','and','or','with','from','that','this','is','are'}
    return [w.lower() for w in re.findall(r'\b\w{3,}\b', task) if w.lower() not in stop]

def score_file(path, kws):
    """Score a file's relevance to the task keywords."""
    try:
        text = open(path, encoding='utf-8', errors='ignore').read().lower()
        return sum(text.count(k) for k in kws)
    except: return 0

def extract_functions(path, kws, max_lines):
    """Extract most relevant functions/classes from a Python file."""
    snippets = []
    try:
        src = open(path, encoding='utf-8', errors='ignore').read()
        tree = ast.parse(src)
        lines = src.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name.lower()
                if any(k in name for k in kws):
                    start = node.lineno - 1
                    end = min(start + max_lines, len(lines))
                    snippet = '\n'.join(lines[start:end])
                    snippets.append((name, path, node.lineno, snippet))
    except Exception:
        pass
    return snippets

def main():
    task, root, max_n = '', os.getcwd(), MAX_SNIPPETS
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == '--max' and i+1 < len(args): max_n = int(args[i+1])
        elif os.path.isdir(a):              root  = a
        elif not a.startswith('--'):        task  = a

    if not task: print('[CTX] Usage: context_injector.py "[task]" [root]'); sys.exit(1)

    kws = keywords(task)
    if not kws: print('[CTX] No keywords extracted.'); sys.exit(0)

    # Find relevant Python files
    scored = []
    for dirpath, _, files in os.walk(root):
        if any(x in dirpath for x in ('__pycache__','.git','node_modules','Library')): continue
        for fn in files:
            if not fn.endswith('.py'): continue
            p = os.path.join(dirpath, fn)
            s = score_file(p, kws)
            if s > 0: scored.append((s, p))

    scored.sort(reverse=True)
    top_files = [p for _, p in scored[:10]]

    snippets = []
    for fp in top_files:
        snippets.extend(extract_functions(fp, kws, MAX_LINES))
        if len(snippets) >= max_n: break

    docs = os.path.join(root, 'docs'); os.makedirs(docs, exist_ok=True)
    out = os.path.join(docs, 'CONTEXT_INJECTION.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(f'# Context Injection -- task: {task[:80]}\n')
        f.write(f'Keywords matched: {kws}\n\n')
        if not snippets:
            f.write('No matching functions found -- proceed without injection.\n')
        for name, path, lineno, code in snippets[:max_n]:
            rel = os.path.relpath(path, root)
            f.write(f'## {name} ({rel}:{lineno})\n```python\n{code}\n```\n\n')
    print(f'[CTX] {len(snippets[:max_n])} snippet(s) -> {out}')

if __name__ == '__main__':
    main()
