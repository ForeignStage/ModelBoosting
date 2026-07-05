"""Claude Code PreToolUse hook -- audit + gate + backup + spiral before file writes.
v5.34: model-gated. Frontier models skip audit/gate, keep only backup+spiral.
"""
import subprocess, sys, os, json

PYTHON = r"C:/Users/15002/AppData/Local/Programs/Python/Python313/python.exe"
ENFORCE = r"E:\AgentHub\AgentBoosting\GodCreating\watchdog\enforce.py"
GATE = r"E:\AgentHub\AgentBoosting\GodCreating\watchdog\deepseek_gate.py"
AUDIT = r"E:\AgentHub\AgentBoosting\GodCreating\watchdog\self_audit.py"
MODEL_DETECT = r"E:\AgentHub\AgentBoosting\GodCreating\watchdog\model_detect.py"

def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=True)
        return r.returncode, r.stdout.strip()
    except Exception:
        return 1, ""

def is_frontier():
    """Quick model check -- return True if frontier (opus/gpt/sonnet/gemini)."""
    try:
        # Use inline import to avoid slow subprocess
        sys.path.insert(0, os.path.dirname(MODEL_DETECT))
        from model_detect import detect
        _, _, _, calibration = detect(r"E:\AgentHub\AgentBoosting\GodCreating")
        return calibration == "standard"
    except Exception:
        return False

def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)

    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool not in ("Write", "Edit"):
        sys.exit(0)

    filepath = tool_input.get("file_path", "")
    if not filepath:
        sys.exit(0)

    # v5.34: Frontier bypass -- gate & audit only needed for DeepSeek
    if is_frontier():
        # Core safety only: backup + spiral (always enforced, all models)
        run(f'"{PYTHON}" "{ENFORCE}" backup --target "{filepath}"')
        run(f'"{PYTHON}" "{ENFORCE}" spiral --touch "{filepath}"')
        sys.exit(0)

    # DeepSeek full gate
    run(f'"{PYTHON}" "{AUDIT}"')
    run(f'"{PYTHON}" "{GATE}" "editing {os.path.basename(filepath)}" watchdog/')
    run(f'"{PYTHON}" "{ENFORCE}" backup --target "{filepath}"')
    run(f'"{PYTHON}" "{ENFORCE}" spiral --touch "{filepath}"')

if __name__ == "__main__":
    main()
