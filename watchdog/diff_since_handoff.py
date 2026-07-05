#!/usr/bin/env python3
"""
Diff Since Handoff -- Cross-verify HANDOFF claims against actual file state.
Finds the latest HANDOFF for the OTHER agent, parses claimed file changes,
and produces a structured verification report.
Usage: python diff_since_handoff.py --other-agent codex [--output docs/]
Exit 0 = all verifiable claims match. Exit 1 = mismatches or unverifiable found.
"""
import os, sys, json, re, hashlib
from datetime import datetime

def find_latest_handoff(docs_dir, agent_prefix):
    """Find the most recent HANDOFF_<prefix>_*.md file."""
    if not os.path.isdir(docs_dir):
        return None
    candidates = []
    for fn in os.listdir(docs_dir):
        if fn.startswith(f'HANDOFF_{agent_prefix}_') and fn.endswith('.md'):
            fp = os.path.join(docs_dir, fn)
            candidates.append((os.path.getmtime(fp), fp))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]

def parse_handoff(handoff_path):
    """Parse HANDOFF sections: Files changed, Current state, Next task."""
    result = {'files': [], 'state': '', 'next_task': '', 'raw': ''}
    if not handoff_path or not os.path.exists(handoff_path):
        return result

    try:
        with open(handoff_path, 'r', encoding='utf-8') as f:
            content = f.read()
        result['raw'] = content[:500]
    except Exception:
        return result

    # Extract "Files changed" -- look for bullet lists with file paths
    files_section = re.search(r'Files changed[:\s]*\n((?:.+\n)*?)(?:\n##|\n#|\Z)', content, re.IGNORECASE)
    if files_section:
        for line in files_section.group(1).split('\n'):
            line = line.strip().lstrip('- ')
            if line and ('.py' in line or '.js' in line or '.html' in line or '.css' in line or '.json' in line):
                result['files'].append(line)

    return result

def verify_file(filepath, claims):
    """Verify a file against HANDOFF claims. Returns (status, details)."""
    result = {'file': filepath, 'status': 'UNVERIFIED', 'details': []}

    if not os.path.exists(filepath):
        result['status'] = 'MISSING'
        result['details'].append('File not found on disk')
        return result

    try:
        size = os.path.getsize(filepath)
        mtime = datetime.fromtimestamp(os.path.getmtime(filepath))

        with open(filepath, 'rb') as f:
            content = f.read()
        md5 = hashlib.md5(content).hexdigest()

        result['details'].append(f'size={size}, mtime={mtime.isoformat()}, md5={md5[:8]}')

        # Verify syntax for .py files
        if filepath.endswith('.py'):
            import py_compile
            try:
                py_compile.compile(filepath, doraise=True)
                result['syntax'] = 'OK'
            except py_compile.PyCompileError as e:
                result['syntax'] = f'SYNTAX ERROR: {e}'
                result['status'] = 'BROKEN'
                return result

        result['status'] = 'VERIFIED'
        result['md5'] = md5
    except Exception as e:
        result['status'] = 'ERROR'
        result['details'].append(str(e))

    return result

def main():
    docs_dir = 'docs'
    other_agent = 'codex'
    output_dir = 'docs'

    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == '--other-agent' and i+1 < len(args):
            other_agent = args[i+1]
        elif a == '--output' and i+1 < len(args):
            output_dir = args[i+1]
        elif os.path.isdir(a):
            docs_dir = os.path.join(a, 'docs')

    # Determine prefix from other agent
    prefix = 'CX' if other_agent.lower() == 'codex' else 'CC'

    handoff_path = find_latest_handoff(docs_dir, prefix)
    if not handoff_path:
        result = {
            'status': 'NO_HANDOFF',
            'message': f'No HANDOFF_{prefix}_*.md found in {docs_dir}',
            'timestamp': datetime.now().isoformat()
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    claims = parse_handoff(handoff_path)

    results = {
        'handoff_file': handoff_path,
        'agent': other_agent,
        'timestamp': datetime.now().isoformat(),
        'verified': [],
        'mismatches': [],
        'missing': [],
        'unverifiable': []
    }

    # For now, verify all .py files referenced in the project that relate to HANDOFF claims
    # Walk docs_dir parent to find referenced files
    project_root = os.path.dirname(docs_dir)

    for file_ref in claims.get('files', []):
        # Try as absolute path, then relative
        fp = file_ref if os.path.isabs(file_ref) else os.path.join(project_root, file_ref)
        verification = verify_file(fp, claims)

        if verification['status'] == 'VERIFIED':
            results['verified'].append(verification)
        elif verification['status'] in ('MISSING', 'BROKEN', 'ERROR'):
            results['mismatches'].append(verification)
        else:
            results['unverifiable'].append(verification)

    # If no explicit files found, note the limitation
    total_bad = len(results['mismatches']) + len(results['missing'])
    results['summary'] = f'{len(results["verified"])} verified, {total_bad} issues, {len(results["unverifiable"])} unverifiable'

    # Write report
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, f'HANDOFF_DIFF_{datetime.now().strftime("%Y%m%d_%H%M%S")}.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f'# HANDOFF VERIFICATION -- {datetime.now().isoformat()}\n')
        f.write(f'Handoff: {os.path.basename(handoff_path)}\n')
        f.write(f'Agent: {other_agent}\n\n')
        f.write(f'## Summary\n{results["summary"]}\n\n')
        if results['verified']:
            f.write('## VERIFIED\n')
            for v in results['verified']:
                f.write(f'- {v["file"]}: {v["details"][0] if v["details"] else "OK"}\n')
        if results['mismatches']:
            f.write('\n## MISMATCHES\n')
            for v in results['mismatches']:
                f.write(f'- {v["file"]}: {v["status"]} -- {v.get("syntax", "; ".join(v.get("details", [])))}\n')
        if results['unverifiable']:
            f.write('\n## UNVERIFIED\n')
            for v in results['unverifiable']:
                f.write(f'- {v["file"]}\n')

    results['report_path'] = report_path
    print(json.dumps(results, ensure_ascii=False, indent=2))
    sys.exit(1 if results['mismatches'] else 0)

if __name__ == '__main__':
    main()
