#!/usr/bin/env python3
"""
Live Hallucination Check -- Runtime import verification engine.
Does NOT execute the target file. Instead:
  1. AST-parses .py files to find attribute chains (obj.method, module.sub.func)
  2. Resolves the root object (imported module, local class, known package)
  3. Uses importlib + hasattr to verify each chain element exists
  4. Marks unresolvable chains as HALLUCINATION

This is the deep verification layer. hallucination_check.py is the fast first-pass filter.
Usage: python halcheck_live.py <filepath> [--project-root <path>]
Exit 0 = clean. Exit 1 = hallucinations found.
"""
import ast, sys, os, json, importlib
from datetime import datetime
from pathlib import Path

# ===== Module/Class/Function name resolver =====

def collect_imports(tree):
    """Extract all imports from an AST tree.
    Returns dict: {local_name: full_module_path} and set of imported names."""
    import_map = {}   # alias -> full module path
    imported_names = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split('.')[0]
                import_map[name] = alias.name
                imported_names.add(name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name
                if node.module:
                    import_map[name] = f"{node.module}.{alias.name}"
                imported_names.add(name)

    return import_map, imported_names


def collect_local_defs(tree):
    """Collect all class/function definitions in the file.
    Returns: {name: {'type': 'class'|'function', 'methods': [...]}}"""
    local = {}

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            methods = []
            for body_node in ast.walk(node):
                if isinstance(body_node, ast.FunctionDef) and body_node.parent == node if hasattr(body_node, 'parent') else True:
                    if isinstance(body_node, ast.FunctionDef):
                        methods.append(body_node.name)
            # Also collect class-level assignments (e.g. Column definitions for ORM models)
            for body_node in node.body if hasattr(node, 'body') else []:
                if isinstance(body_node, ast.Assign):
                    for target in body_node.targets:
                        if isinstance(target, ast.Name):
                            methods.append(target.id)
                elif isinstance(body_node, ast.AnnAssign) and isinstance(body_node.target, ast.Name):
                    methods.append(body_node.target.id)

            local[node.name] = {'type': 'class', 'methods': methods}
        elif isinstance(node, ast.FunctionDef):
            local[node.name] = {'type': 'function', 'methods': []}

    return local


def try_import_verify(module_path, attr_chain):
    """Try to import a module and verify an attribute chain exists.
    Returns (exists: bool, detail: str)."""
    try:
        mod = importlib.import_module(module_path)
    except ImportError:
        return False, f"cannot import {module_path}"
    except Exception:
        return False, f"import error for {module_path}"

    obj = mod
    for i, attr in enumerate(attr_chain):
        if not hasattr(obj, attr):
            return False, f"{module_path}.{'.'.join(attr_chain)} -- '{attr}' not found (resolved up to: {'.'.join(attr_chain[:i])})"
        obj = getattr(obj, attr)

    return True, "verified"


KNOWN_PACKAGE_IMPORTS = {
    'fastapi': ['FastAPI', 'APIRouter', 'Depends', 'HTTPException', 'Query', 'Body', 'Path', 'Header', 'Cookie', 'Response', 'Request', 'BackgroundTasks', 'UploadFile', 'Form', 'File'],
    'sqlalchemy': ['create_engine', 'Column', 'Integer', 'String', 'Float', 'Boolean', 'DateTime', 'Text', 'ForeignKey', 'Table', 'MetaData', 'relationship', 'backref', 'sessionmaker', 'Session', 'select', 'insert', 'update', 'delete', 'func', 'and_', 'or_', 'not_'],
    'sqlalchemy.orm': ['Session', 'sessionmaker', 'relationship', 'backref', 'declarative_base', 'joinedload', 'subqueryload', 'Query'],
    'pydantic': ['BaseModel', 'Field', 'validator', 'root_validator'],
    'os.path': ['join', 'dirname', 'basename', 'exists', 'isdir', 'isfile', 'abspath', 'splitext'],
    'json': ['load', 'loads', 'dump', 'dumps'],
    'datetime': ['datetime', 'date', 'time', 'timedelta', 'timezone', 'now', 'fromisoformat', 'strptime', 'strftime', 'utcnow', 'today', 'fromtimestamp', 'timestamp', 'isoformat', 'replace', 'astimezone'],
    're': ['search', 'match', 'findall', 'sub', 'split', 'compile', 'IGNORECASE', 'MULTILINE', 'DOTALL'],
    'os': ['path', 'environ', 'getcwd', 'chdir', 'listdir', 'makedirs', 'remove', 'rename', 'walk', 'sep', 'linesep', 'getenv', 'name'],
    'sys': ['argv', 'exit', 'path', 'version', 'platform', 'executable', 'stdin', 'stdout', 'stderr', 'modules'],
    'pathlib.Path': ['exists', 'is_dir', 'is_file', 'mkdir', 'rmdir', 'unlink', 'rename', 'read_text', 'write_text', 'glob', 'rglob'],
    'subprocess': ['run', 'Popen', 'call', 'check_output', 'DEVNULL', 'PIPE', 'STDOUT'],
    'hashlib': ['md5', 'sha256', 'sha1', 'sha512'],
}

# Common stdlib types with known methods (for local variable type inference)
COMMON_TYPES = {
    'dict': {'get', 'keys', 'values', 'items', 'update', 'pop', 'clear', 'copy', 'setdefault', 'fromkeys', '__getitem__'},
    'list': {'append', 'extend', 'insert', 'remove', 'pop', 'clear', 'index', 'count', 'sort', 'reverse', 'copy', '__getitem__'},
    'str': {'strip', 'split', 'join', 'replace', 'lower', 'upper', 'startswith', 'endswith', 'find', 'format', 'encode', 'isdigit', 'isalpha', 'lstrip', 'rstrip'},
    'int': set(),
    'float': set(),
    'bool': set(),
    'tuple': {'index', 'count', '__getitem__'},
    'set': {'add', 'remove', 'discard', 'pop', 'clear', 'union', 'intersection', 'difference', 'update', 'copy'},
    'frozenset': {'union', 'intersection', 'difference', 'copy'},
    'bytes': {'decode', 'hex', 'strip', 'split', 'join', 'replace', 'startswith', 'endswith', 'find'},
    'bytearray': {'decode', 'append', 'extend', 'insert', 'remove', 'pop', 'clear'},
    'range': set(),
    'type': set(),
}

def infer_local_types(tree):
    """Walk AST and infer types of local variables from assignments.
    Returns dict: {var_name: inferred_type_string}."""
    inferred = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    # Infer from json.loads/json.load -> dict
                    if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
                        if node.value.func.attr in ('loads', 'load'):
                            # json.loads() / json.load() -> dict
                            inferred[target.id] = 'dict'
                    # Infer from dict literal
                    elif isinstance(node.value, ast.Dict):
                        inferred[target.id] = 'dict'
                    # Infer from list literal
                    elif isinstance(node.value, ast.List):
                        inferred[target.id] = 'list'
                    # Infer from str literal
                    elif isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        inferred[target.id] = 'str'
                    # Infer from int/float literal
                    elif isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float)):
                        inferred[target.id] = 'int'
                    # Infer from call result: any dict method -> dict
                    elif isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
                        dict_methods = {'get', 'keys', 'values', 'items', 'copy', 'setdefault', 'fromkeys'}
                        if node.value.func.attr in dict_methods:
                            inferred[target.id] = 'dict'
                    # os.getcwd() / os.path.dirname() -> str
                    elif isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
                        str_methods = {'getcwd', 'dirname', 'basename', 'abspath', 'join', 'strftime', 'isoformat', 'strip', 'replace'}
                        if node.value.func.attr in str_methods:
                            inferred[target.id] = 'str'

    return inferred


def resolve_attr_chain(root_name, attr_chain, import_map, local_defs, project_root, local_types=None):
    """Try to resolve and verify an attribute chain.
    Returns (status: str, detail: str) where status is 'ok'|'hallucination'|'uncertain'."""
    full_chain = f"{root_name}.{'.'.join(attr_chain)}"
    if local_types is None:
        local_types = {}

    # Check if root is a local variable with inferred type
    if root_name in local_types:
        inferred_type = local_types[root_name]
        if inferred_type in COMMON_TYPES:
            if attr_chain[0] in COMMON_TYPES[inferred_type]:
                return 'ok', f"local {root_name}:{inferred_type} has {attr_chain[0]}"
            return 'hallucination', f"{full_chain} -- '{attr_chain[0]}' not a known method of {inferred_type} (known: {sorted(COMMON_TYPES[inferred_type])[:8]})"
        return 'ok', f"local {root_name} inferred as {inferred_type}"

    # Check if root is a local class
    if root_name in local_defs and local_defs[root_name]['type'] == 'class':
        # Verify attr_chain[0] exists as a method/attribute of the class
        local_methods = local_defs[root_name].get('methods', [])
        if attr_chain[0] in local_methods:
            return 'ok', f"local class {root_name} has {attr_chain[0]}"
        # Check if it's a SQLAlchemy model with query attribute
        if attr_chain[0] == 'query':
            return 'ok', f"SQLAlchemy model {root_name}.query (ORM standard)"
        # Unknown method on local class -> likely hallucination
        return 'hallucination', f"{full_chain} -- '{attr_chain[0]}' not found on local class {root_name} (known methods: {local_methods[:5]}...)"

    # Check if root is imported from a known package
    if root_name in import_map:
        module_path = import_map[root_name]
        # Try to verify via import
        exists, detail = try_import_verify(module_path, attr_chain)
        if exists:
            return 'ok', f"{module_path}.{'.'.join(attr_chain)} verified"

        # Check KNOWN_PACKAGE_IMPORTS as fallback
        for pkg, members in KNOWN_PACKAGE_IMPORTS.items():
            if module_path.startswith(pkg):
                if attr_chain[0] in members:
                    return 'ok', f"{full_chain} -- known member of {pkg}"
                # Not a known member -- hallucination
                return 'hallucination', f"{full_chain} -- 'attr_chain[0]' not a known member of {pkg}"

        return 'uncertain', f"{full_chain} -- could not verify via import ({detail})"

    # Check if root is a known builtin/stdlib module used as direct import
    for pkg, members in KNOWN_PACKAGE_IMPORTS.items():
        if root_name in pkg or pkg.startswith(root_name):
            if attr_chain[0] in members:
                return 'ok', f"{full_chain} -- known member of {pkg}"
            return 'hallucination', f"{full_chain} -- '{attr_chain[0]}' not a known member of {pkg}"

    # Root not resolved -> uncertain
    return 'uncertain', f"cannot resolve root '{root_name}'"


def check_file(filepath, project_root):
    """Run live hallucination check on a Python file.
    Returns list of hallucination issues."""
    issues = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except SyntaxError as e:
        return [{'chain': 'N/A', 'status': 'syntax_error', 'detail': str(e)}]
    except Exception as e:
        return [{'chain': 'N/A', 'status': 'parse_error', 'detail': str(e)}]

    import_map, imported_names = collect_imports(tree)
    local_defs = collect_local_defs(tree)
    local_types = infer_local_types(tree)

    # Find all attribute call chains
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            # Build the full dotted chain
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.insert(0, current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.insert(0, current.id)
            else:
                continue  # too complex, skip

            if len(parts) < 2:
                continue

            root_name = parts[0]
            attr_chain = parts[1:]

            # Skip if root is a local variable (can't statically resolve)
            if root_name in imported_names or root_name in local_defs:
                pass  # resolvable
            elif root_name[0].islower():
                continue  # likely a local variable, skip

            status, detail = resolve_attr_chain(root_name, attr_chain, import_map, local_defs, project_root, local_types)

            if status == 'hallucination':
                issues.append({
                    'chain': '.'.join(parts),
                    'status': 'hallucination',
                    'detail': detail
                })
            elif status == 'uncertain':
                issues.append({
                    'chain': '.'.join(parts),
                    'status': 'uncertain',
                    'detail': detail
                })

    return issues


def main():
    if len(sys.argv) < 2:
        print("Usage: halcheck_live.py <filepath> [--project-root <path>]")
        sys.exit(0)

    filepath = sys.argv[1]
    project_root = os.path.dirname(filepath)

    if '--project-root' in sys.argv:
        idx = sys.argv.index('--project-root')
        project_root = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else project_root

    if not os.path.exists(filepath):
        print(json.dumps({'error': f'File not found: {filepath}'}, ensure_ascii=False))
        sys.exit(1)

    issues = check_file(filepath, project_root)
    hallucinations = [i for i in issues if i['status'] == 'hallucination']
    uncertains = [i for i in issues if i['status'] == 'uncertain']

    result = {
        'file': filepath,
        'hallucinations': hallucinations,
        'uncertain': uncertains,
        'total_hallucinations': len(hallucinations),
        'total_uncertain': len(uncertains),
        'status': 'PASS' if not hallucinations else 'FAIL',
        'timestamp': datetime.now().isoformat()
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(1 if hallucinations else 0)


if __name__ == '__main__':
    main()
