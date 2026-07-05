"""Claude Code PostToolUse hook -- verify + quality + delegation + fuse after file writes.
v5.35: +sync_to_agentprojects auto-routing for Codex/CC file output.
v5.34: model-gated. Frontier models skip all checks, return immediately.
DeepSeek keeps full pipeline (verify, hallucination, quality, delegation, fuse).
"""
import subprocess, sys, os, json, shutil
from datetime import datetime

PYTHON = r"C:/Users/15002/AppData/Local/Programs/Python/Python313/python.exe"
ENFORCE = r"E:\AgentHub\AgentBoosting\GodCreating\watchdog\enforce.py"
VERIFY = r"E:\AgentHub\AgentBoosting\GodCreating\watchdog\verify_task.py"
QUALITY = r"E:\AgentHub\AgentBoosting\GodCreating\watchdog\code_quality_gate.py"
DELEGATION = r"E:\AgentHub\AgentBoosting\GodCreating\watchdog\delegation_check.py"
HALLUCINATION = r"E:\AgentHub\AgentBoosting\GodCreating\watchdog\hallucination_check.py"
HALCHECK_LIVE = r"E:\AgentHub\AgentBoosting\GodCreating\watchdog\halcheck_live.py"
SELF_REVIEW = r"E:\AgentHub\AgentBoosting\GodCreating\watchdog\self_review_injector.py"
MODEL_DETECT = r"E:\AgentHub\AgentBoosting\GodCreating\watchdog\model_detect.py"

AGENT_PROJECTS_ROOT = r"E:\AgentHub\AgentProjects"
ROUTING_CONFIG = r"E:\AgentHub\AgentBoosting\GodCreating\config\session_routing.json"
CODEX_BASE = r"C:\Users\15002\Documents\Codex"
DOCS_BASE = r"C:\Users\15002\Documents"

def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=True)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return 1, "", str(e)

def is_frontier():
    try:
        sys.path.insert(0, os.path.dirname(MODEL_DETECT))
        from model_detect import detect
        _, _, _, calibration = detect(r"E:\AgentHub\AgentBoosting\GodCreating")
        return calibration == "standard"
    except Exception:
        return False

def sync_to_agentprojects(filepath):
    """Auto-route files written outside AgentProjects to their project home.
    
    Strategy:
    1. Skip if file already in AgentProjects (direct or via junction realpath).
    2. Match against session_routing.json workspace->project mappings.
    3. For Codex date/thread dirs: try AGENTS.md context, fallback FreeTalk.
    4. Copy preserving relative structure.
    """
    try:
        filepath = os.path.abspath(filepath)
    except Exception:
        return

    # --- Skip: already in AgentProjects (direct path) ---
    if filepath.lower().startswith(AGENT_PROJECTS_ROOT.lower()):
        return

    # --- Skip: junction target resolves to AgentProjects ---
    try:
        real = os.path.realpath(filepath)
        if real.lower().startswith(AGENT_PROJECTS_ROOT.lower()):
            return
    except Exception:
        pass

    # --- Load routing config ---
    try:
        with open(ROUTING_CONFIG, "r", encoding="utf-8") as f:
            routing = json.load(f)
    except Exception:
        return

    filepath_lower = filepath.lower().replace("\\", "/")
    target_project = None

    # --- Match against known workspace routes ---
    for agent_type in ("cx", "cc"):
        routes = routing.get("routes", {}).get(agent_type, {})
        for workspace, project in routes.items():
            ws_normalized = workspace.lower().replace("\\", "/")
            if filepath_lower.startswith(ws_normalized):
                target_project = project
                break
        if target_project:
            break

    # --- Determine relative path ---
    codex_base_lower = CODEX_BASE.lower().replace("\\", "/")
    docs_base_lower = DOCS_BASE.lower().replace("\\", "/")

    if filepath_lower.startswith(codex_base_lower):
        # Codex workspace: preserve date/thread structure under codex-sync/
        rel = os.path.relpath(filepath, CODEX_BASE)
        rel_target = os.path.join("codex-sync", rel)

        if not target_project:
            # Try to find AGENTS.md context by walking up
            target_project = _find_project_from_agents(filepath, routing)
        if not target_project:
            target_project = routing.get("defaults", {}).get("cx", "FreeTalk")

    elif filepath_lower.startswith(docs_base_lower):
        # Documents workspace (non-Codex, non-junction)
        rel = os.path.relpath(filepath, DOCS_BASE)
        parts = rel.split(os.sep, 1)
        if len(parts) > 1:
            rel_target = parts[1]
        else:
            rel_target = os.path.basename(filepath)

        if not target_project:
            target_project = routing.get("defaults", {}).get("cc", "FreeTalk")
    else:
        # Other paths: just the filename
        rel_target = os.path.basename(filepath)
        if not target_project:
            target_project = "FreeTalk"

    # --- Build and write target ---
    target_dir = os.path.join(AGENT_PROJECTS_ROOT, target_project)
    target_path = os.path.join(target_dir, rel_target)
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        shutil.copy2(filepath, target_path)
        print(f"[postWrite] sync: {os.path.basename(filepath)} -> AgentProjects/{target_project}")
    except Exception as e:
        print(f"[postWrite] sync FAIL: {e}")

def _find_project_from_agents(filepath, routing):
    """Walk up from filepath looking for AGENTS.md with project declaration."""
    current = os.path.dirname(os.path.abspath(filepath))
    for _ in range(6):
        agents_path = os.path.join(current, "AGENTS.md")
        if os.path.exists(agents_path):
            try:
                with open(agents_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # Check for project alias declarations
                aliases = routing.get("project_aliases", {})
                content_lower = content.lower()
                for alias, project in aliases.items():
                    if alias.lower() in content_lower:
                        return project
            except Exception:
                pass
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None

def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)

    tool = data.get("tool_name", "")
    if tool not in ("Write", "Edit"):
        sys.exit(0)

    filepath = data.get("tool_input", {}).get("file_path", "")
    if not filepath:
        sys.exit(0)

    # v5.35: Always run sync_to_agentprojects (all models, all file types)
    sync_to_agentprojects(filepath)

    # v5.34: Frontier bypass -- all post-write checks are DeepSeek compensation.
    # Frontier models handle correctness/review natively.
    if is_frontier():
        sys.exit(0)

    # ---- DeepSeek: full post-write pipeline below ----

    # Frontend files: contract check only
    if filepath.endswith((".js", ".html", ".css", ".ts", ".jsx", ".tsx")):
        proj_root = os.path.dirname(filepath)
        rc, out, err = run(f'"{PYTHON}" "{ENFORCE}" contract_check --agent claude_code "{proj_root}"', timeout=15)
        if rc != 0:
            print(f"[postWrite] contract_check: frontend API call may not match backend")
        sys.exit(0)

    # Only gate .py files below this point
    if not filepath.endswith(".py"):
        sys.exit(0)

    print(f"[postWrite] verify+quality+delegation+hallucination for {os.path.basename(filepath)} @ {datetime.now().isoformat()}")

    # 1. verify_task.py
    rc, out, err = run(f'"{PYTHON}" "{VERIFY}" "{filepath}"', timeout=60)
    if rc == 0:
        print(f"[postWrite] verify_task.py PASS")
    else:
        print(f"[postWrite] verify_task.py FAIL: {err[:200]}")

    # 1b. hallucination check
    if os.path.exists(HALLUCINATION):
        rc, out, err = run(f'"{PYTHON}" "{HALLUCINATION}" "{filepath}"', timeout=30)
        if rc == 0:
            print(f"[postWrite] hallucination_check PASS")
        else:
            print(f"[postWrite] hallucination_check FAIL: {err[:200]}")

    # 1c. live hallucination check
    if os.path.exists(HALCHECK_LIVE):
        rc, out, err = run(f'"{PYTHON}" "{HALCHECK_LIVE}" "{filepath}"', timeout=30)
        if rc == 0:
            print(f"[postWrite] halcheck_live PASS")
        else:
            print(f"[postWrite] halcheck_live FAIL")

    # 2. code_quality_gate
    rc, out, err = run(f'"{PYTHON}" "{QUALITY}" --scope "{os.path.dirname(filepath)}"', timeout=45)
    if rc == 0:
        print(f"[postWrite] code_quality_gate PASS")
    else:
        print(f"[postWrite] code_quality_gate WARN: {err[:200]}")

    # 3. delegation_check
    rc, out, err = run(f'"{PYTHON}" "{DELEGATION}" --agent claude_code "{os.path.dirname(filepath)}"', timeout=15)
    if rc == 2:
        print(f"[postWrite] delegation_check: cross-domain work queued for Codex")

    # 4. Fuse graduated check
    rc, out, err = run(f'"{PYTHON}" "{ENFORCE}" fuse --graduated', timeout=10)
    if rc == 0 and out:
        try:
            result = json.loads(out)
            pct = result.get("pct", 0)
            if pct >= 95:
                print(f"[postWrite] FUSE CRITICAL: {pct}% -- STOP")
            elif pct >= 80:
                print(f"[postWrite] FUSE WARNING: {pct}% -- P0+P1 only")
        except Exception:
            pass

    # 5. Fuse actual
    rc, out, err = run(f'"{PYTHON}" "{ENFORCE}" fuse --actual', timeout=10)
    if rc == 0 and out:
        try:
            r = json.loads(out)
            total = sum(t.get("tokens_used", 0) for t in r.get("threads", []))
            if total > 0:
                print(f"[postWrite] sqlite tokens: {total}")
        except Exception:
            pass

    # 6. Auto-track tokens
    rc, out, err = run(f'"{PYTHON}" "{ENFORCE}" fuse --auto-track claude_code', timeout=10)
    if rc == 0 and out:
        try:
            r = json.loads(out)
            pool_used = r.get("pct_used", 0)
            if pool_used > 0:
                print(f"[postWrite] pool: {pool_used:.1f}% used")
        except Exception:
            pass

    # 7. Self-review injection
    if os.path.exists(SELF_REVIEW):
        run(f'"{PYTHON}" "{SELF_REVIEW}" "{filepath}" --agent claude_code', timeout=15)

    print(f"[postWrite] DONE")

if __name__ == "__main__":
    main()