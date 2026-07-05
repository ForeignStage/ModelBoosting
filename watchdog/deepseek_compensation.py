#!/usr/bin/env python3
"""
DeepSeek Compensation Engine v2.1 (v5.34)
==========================================
Bridges the gap between deepseek-v4-pro and Claude Opus 4.8 by externalizing
capabilities that deepseek lacks natively:
  - Strict Chain-of-Thought injection (compensates for no Extended Thinking)
  - Design->Implement->Review pipeline orchestration
  - Adversarial review dispatch
  - Tool-call verification
  - Context trimming recommendations
  - Pre-completion integrity check
  - Auto-escalation for complex tasks (leverage Claude Code Workflow)
  - Verify-pipeline: ensures every change passes adversarial review

Usage:
  python deepseek_compensation.py classify "<task>"           -> complexity score + pipeline recommendation
  python deepseek_compensation.py cot "<task>"                 -> emit standard CoT injection prompt
  python deepseek_compensation.py strict-cot "<task>"          -> emit strict structured CoT (XML-tag enforced)
  python deepseek_compensation.py pipeline "<task>"            -> emit full pipeline instructions for Claude Code
  python deepseek_compensation.py verify                       -> pre-completion integrity check
  python deepseek_compensation.py verify-pipeline [--dir <scan_dir>]  -> check if recent changes passed adversarial review
  python deepseek_compensation.py trim <file1> <file2> ...     -> recommend context trimming
  python deepseek_compensation.py escalate "<task>"            -> emit auto-escalation directive for Workflow
"""

import sys
import os
import json
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from paths import GODCREATING_ROOT, WATCHDOG_DIR, safe_print

# ── Configuration ──────────────────────────────────────────────
COMPLEXITY_KW_HIGH = {
    "refactor", "refactoring", "restructure",
    "architecture", "architectural",
    "migrate", "migration",
    "audit", "auditing",
    "security", "vulnerability",
    "redesign", "rewrite", "overhaul",
    "multi-module", "cross-cutting", "cross-module",
    "database schema", "schema change", "db migration",
    "API redesign", "breaking change",
    "auth", "authentication", "authorization",
    "transaction", "concurrency", "race condition",
    "encryption", "hashing", "crypto",
}

COMPLEXITY_KW_MEDIUM = {
    "implement", "implementation",
    "feature", "functionality",
    "endpoint", "API endpoint", "route",
    "component", "module",
    "service", "handler",
    "add", "adding",
    "fix bug", "bug fix", "debug",
    "optimize", "optimization", "performance",
    "test", "unit test", "integration test",
    "refine", "enhance", "improve",
}

# v5.33 strict CoT -- XML-tag enforced, deepseek can't skip it
STRICT_COT_TEMPLATE = """BEFORE ANY TOOL USE, you MUST output your reasoning in this EXACT format:

<thinking>
1. TASK RESTATEMENT: Restate {task} in your own words -- one sentence.
2. FILES TO CHANGE: List each file path and WHY it must change.
3. EDGE CASES: What could go wrong? What inputs are unexpected?
4. MINIMAL CHANGE: What is the SMALLEST code diff that satisfies this?
5. VERIFICATION: How will you prove it works (compile, run, test)?
</thinking>

After closing </thinking> tag, proceed with tool calls. Do NOT skip this step."""

# ── Core Functions ─────────────────────────────────────────────

def classify_complexity(task: str) -> dict:
    """Score task complexity 1-5 and recommend pipeline depth."""
    t = task.lower()
    high_hits = sum(1 for kw in COMPLEXITY_KW_HIGH if kw.lower() in t)
    medium_hits = sum(1 for kw in COMPLEXITY_KW_MEDIUM if kw.lower() in t)

    file_count = len(re.findall(r'[\w/\\-]+\.(py|js|ts|md|json|yml|yaml|sql|txt)', task))
    mod_matches = re.findall(r'(?i)(\d+)\s*(?:module|file|service|endpoint|component|layer|table)s?', task)
    if mod_matches:
        file_count += sum(int(m) for m in mod_matches)
    action_count = len(re.findall(r'(?i)\b(and|then|also|next|step\s*\d|across|multiple|several)\b', task))

    score = 1
    score += min(high_hits * 2, 3)
    score += min(medium_hits, 2)
    score += min(file_count // 2, 2)
    score += min(action_count // 2, 1)
    score = min(score, 5)

    if score <= 2:
        recommendation = "single_agent"
        pipeline = "Single Agent call -- no pipeline needed."
        escalate = False
    elif score == 3:
        recommendation = "implement_review"
        pipeline = "Implement -> Review (2 agents sequential)"
        escalate = False
    elif score == 4:
        recommendation = "design_implement_review"
        pipeline = "Design -> Implement -> Review (3 agents sequential)"
        escalate = True  # v5.33: auto-escalate at complexity 4+
    else:
        recommendation = "full_panel"
        pipeline = "Design -> 3 independent implements -> Judge panel -> Review (6 agents)"
        escalate = True  # v5.33: auto-escalate at complexity 5

    return {
        "complexity": score,
        "recommendation": recommendation,
        "pipeline": pipeline,
        "escalate": escalate,  # v5.33 new field
        "escalate_reason": "Use Claude Code Workflow for multi-agent orchestration" if escalate else None,
        "metrics": {
            "high_keyword_hits": high_hits,
            "medium_keyword_hits": medium_hits,
            "file_references": file_count,
            "action_steps": action_count
        }
    }


def emit_cot_prompt(task: str) -> str:
    """Generate standard CoT injection for deepseek."""
    return f"""THINK -- before writing ANY code:
1. RESTATE the task in your own words: "{task}"
2. Which files WILL you change and WHY each one?
3. What EDGE CASES and failure modes exist?
4. What is the MINIMAL change that satisfies this task?
5. What VERIFICATION will prove it works?
Only after completing ALL 5 steps above, proceed to act.
"""


def emit_strict_cot(task: str) -> str:
    """v5.33: Generate strict CoT with XML-tag enforcement."""
    return STRICT_COT_TEMPLATE.format(task=task)


def emit_pipeline_instructions(task: str, analysis: dict) -> str:
    """Generate full pipeline instructions for Claude Code Workflow."""
    score = analysis["complexity"]
    rec = analysis["recommendation"]

    base = f"""# DeepSeek Compensation Pipeline
## Task: {task}
## Complexity: {score}/5 | Strategy: {rec}

### Strict CoT Injection (MANDATORY before each agent call):
{emit_strict_cot(task)}

"""
    if score <= 2:
        base += """### Single Agent Pipeline:
Use one general-purpose agent. Inject strict CoT. Verify output.
"""
    elif score == 3:
        base += """### Implement -> Review Pipeline:
Phase 1 (Implement): Agent(type="general-purpose", prompt="Implement: [task]. Write code only. Do not review yourself.")
Phase 2 (Review): Agent(type="general-purpose", prompt="Adversarially review the implementation. Find bugs, edge cases, missing error handling. Be a harsh critic.")
"""
    elif score == 4:
        base += """### Design -> Implement -> Review Pipeline:
Phase 1 (Design): Agent(type="general-purpose", prompt="Design the architecture for: [task]. Output a plan, not code. List files to change, data flow, interfaces.")
Phase 2 (Implement): Agent(type="general-purpose", prompt="Implement exactly this design: [design_result]. Write code. Do NOT deviate.")
Phase 3 (Review): Agent(type="general-purpose", prompt="Adversarially review the implementation against the design. Check: correctness, edge cases, error handling, performance.")
"""
    else:
        base += """### Full Judge Panel Pipeline:
Phase 1 (Design): Agent(type="general-purpose", prompt="Design architecture for: [task]")
Phase 2 (3 parallel implements):
  - Agent(type="general-purpose", prompt="Implement approach A (MVP-first) for: [design]")
  - Agent(type="general-purpose", prompt="Implement approach B (robustness-first) for: [design]")
  - Agent(type="general-purpose", prompt="Implement approach C (performance-first) for: [design]")
Phase 3 (Judge): Agent(type="general-purpose", prompt="Judge the 3 implementations. Pick winner, graft best ideas from runners-up. Produce final merged version.")
Phase 4 (Review): Agent(type="general-purpose", prompt="Final adversarial review of merged version.")
"""

    if analysis.get("escalate"):
        base += """
### ⚠ AUTO-ESCALATE (v5.33):
This task complexity ({score}/5) exceeds single-agent threshold.
RECOMMENDATION: Use Claude Code Workflow tool for multi-agent orchestration.
The Workflow tool supports parallel agents, judge panels, and adversarial verification.
"""

    base += """
### Verification (after all agents):
- Run `python enforce.py verify --check` if watchdog exists
- Manually compile/test critical paths
- Check all files exist and are well-formed
"""
    return base


def emit_escalate(task: str) -> dict:
    """v5.33: Emit auto-escalation directive for Workflow."""
    analysis = classify_complexity(task)
    return {
        "task": task,
        "complexity": analysis["complexity"],
        "escalate": analysis["escalate"],
        "recommendation": analysis["recommendation"],
        "action": (
            "USE WORKFLOW: Spawn parallel agents for Design->Implement->Review pipeline."
            if analysis["escalate"]
            else "No escalation needed -- single agent is sufficient."
        ),
        "workflow_hint": (
            "Launch Plan agent first for design, then parallel worker-dev agents for implementation, "
            "then general-purpose agent for adversarial review. Final synthesis agent merges results."
            if analysis["escalate"]
            else None
        )
    }


def verify_pre_completion() -> dict:
    """Pre-completion integrity check -- gate before declaring task done."""
    results = {
        "status": "ok",
        "checks": [],
        "warnings": [],
        "timestamp": datetime.now().isoformat()
    }

    task_dir = Path(GODCREATING_ROOT) / "docs"
    clarify_file = task_dir / "CLARIFY_PENDING.md"
    if clarify_file.exists():
        age = datetime.now().timestamp() - clarify_file.stat().st_mtime
        if age < 300:
            results["warnings"].append("CLARIFY_PENDING.md still fresh -- may indicate unresolved ambiguity")
            results["checks"].append("clarify_pending: WARN")
        else:
            results["checks"].append("clarify_pending: stale (OK)")

    results["checks"].append("reminder: run adversarial-review agent before COMPLETED")

    bak_count = len(list(Path(WATCHDOG_DIR).glob("*.bak")))
    if bak_count > 3:
        results["warnings"].append(f"{bak_count} .bak files in watchdog -- may indicate unsettled changes")

    enforce = Path(WATCHDOG_DIR) / "enforce.py"
    if enforce.exists():
        rc, _, _ = run_cmd(f'python -m py_compile "{enforce}"', 10)
        if rc != 0:
            results["warnings"].append("enforce.py compile FAILED")
            results["status"] = "fail"
        else:
            results["checks"].append("enforce.py compile: OK")

    audit = Path(WATCHDOG_DIR) / "self_audit.py"
    if audit.exists():
        rc, out, _ = run_cmd(f'python "{audit}"', 10)
        if rc != 0:
            results["warnings"].append(f"self_audit FAILED: {out[:200]}")
            results["status"] = "fail"
        else:
            results["checks"].append("self_audit: OK")

    return results


def verify_pipeline(scan_dir: str = None) -> dict:
    """v5.33: Check if recent changes have passed adversarial review pipeline.

    Scans for:
    1. Files modified in last session that lack a corresponding VERIFY_ report
    2. Whether the Design->Implement->Review pattern was followed for complex changes
    3. Whether any changes bypassed the gate system
    """
    if scan_dir is None:
        scan_dir = GODCREATING_ROOT

    docs_dir = os.path.join(scan_dir, "docs")
    results = {
        "status": "ok",
        "checks": [],
        "warnings": [],
        "actions_needed": [],
        "timestamp": datetime.now().isoformat()
    }

    # Check 1: VERIFY report freshness
    if os.path.isdir(docs_dir):
        now = datetime.now()
        verify_cutoff = now - timedelta(hours=2)  # 2h window
        found = False
        for fname in os.listdir(docs_dir):
            if fname.startswith("VERIFY_") and fname.endswith(".md"):
                fpath = os.path.join(docs_dir, fname)
                mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                if mtime > verify_cutoff:
                    found = True
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if "PASS" in content:
                        results["checks"].append(f"VERIFY report: PASS ({fname})")
                    else:
                        results["warnings"].append(f"VERIFY report exists but no PASS: {fname}")
                        results["actions_needed"].append("Fix issues and re-verify")
                    break
        if not found:
            results["warnings"].append("No recent VERIFY report (<2h). Run verify--check before declaring done.")
            results["actions_needed"].append("Run: python watchdog/verify_task.py --all")

    # Check 2: Adversarial review coverage
    audit_dir = os.path.join(scan_dir, "watchdog")
    audit_log = os.path.join(audit_dir, "action_log.json")
    if os.path.exists(audit_log):
        try:
            with open(audit_log, 'r', encoding='utf-8') as f:
                actions = json.load(f)
            if isinstance(actions, dict):
                actions = []
            reviews = [a for a in actions if isinstance(a, dict) and a.get("action") == "adversarial_review"]
            changes = [a for a in actions if isinstance(a, dict) and a.get("action") in ("write", "edit")]
            if len(changes) > 0 and len(reviews) == 0:
                results["warnings"].append(f"No adversarial review found for {len(changes)} changes")
                results["actions_needed"].append("Run adversarial review agent before completing")
            else:
                results["checks"].append(f"Adversarial reviews: {len(reviews)} for {len(changes)} changes")
        except:
            pass

    # Check 3: SCOPE_active.md existence for complex changes
    scope_file = os.path.join(docs_dir, "SCOPE_active.md")
    if not os.path.exists(scope_file):
        results["warnings"].append("SCOPE_active.md not found -- task scope not declared")
        results["actions_needed"].append("Write docs/SCOPE_active.md (Task / Will write / Done when)")

    # Overall status
    if len(results["warnings"]) >= len(results["checks"]):
        results["status"] = "needs_attention"
    if results["actions_needed"]:
        results["status"] = "pipeline_incomplete" if results["status"] == "ok" else results["status"]

    return results


def recommend_trim(files: list) -> dict:
    """Recommend which files to keep/drop for context efficiency."""
    if not files:
        return {"keep": [], "drop": [], "reason": "no files provided"}

    keep, drop = [], []
    priority_exts = {".py", ".js", ".ts", ".json", ".yml", ".yaml", ".md"}
    priority_paths = {"watchdog", "hooks", "skills", "agents"}

    for f in files:
        p = Path(f)
        ext = p.suffix.lower()
        if any(x in str(p) for x in ["node_modules", "__pycache__", ".bak", "logs/"]):
            drop.append(f)
        elif ext in {".pyc", ".exe", ".dll", ".obj", ".class"}:
            drop.append(f)
        elif ext in priority_exts:
            keep.append(f)
        elif any(pp in str(p).lower() for pp in priority_paths):
            keep.append(f)
        else:
            keep.append(f)

    advice = f"Keep {len(keep)} files, drop {len(drop)}. "
    if len(keep) > 15:
        advice += "WARNING: >15 files -- consider splitting into sub-tasks."
    elif len(keep) > 8:
        advice += "Consider using Explore agent to pre-filter."

    return {"keep": keep, "drop": drop, "advice": advice}


def run_cmd(cmd, timeout=15):
    """Run shell command, return (rc, stdout, stderr)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=True)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


# ── Main ───────────────────────────────────────────────────────

def compensation_active(project_dir: str = ".") -> dict:
    """Check if DeepSeek compensation layer should be active.
    Returns {active: bool, calibration: str, model: str, reason: str}.
    Frontier models -> inactive. DeepSeek/unknown -> active.
    v5.35 -- uses canonical get_calibration() (calibration.json cache).
    """
    try:
        from model_detect import get_calibration
        wd = os.path.join(project_dir, "watchdog") if os.path.isdir(os.path.join(project_dir, "watchdog")) else project_dir
        cal = get_calibration(watch_dir=wd, project_dir=project_dir)
        active = cal.get("deepseek_active", True)
        model = cal.get("model", "unknown")
        calibration = cal.get("calibration", "max_caution")
        reason = (
            "DeepSeek compensation DISABLED -- frontier model natively handles CLARIFY/CoT/vision."
            if not active
            else f"Compensation ACTIVE ({calibration}) -- external CoT/gate/audit enforced."
        )
        return {"active": active, "calibration": calibration, "model": model, "reason": reason}
    except Exception as e:
        return {"active": True, "calibration": "max_caution", "model": "unknown", "reason": f"Detect failed: {e}. Conservative: assume compensation needed."}


def main():
    if len(sys.argv) < 2:
        print("Usage: python deepseek_compensation.py <command> [args...]")
        print("Commands: check, classify, cot, strict-cot, pipeline, verify, verify-pipeline, escalate, trim")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "check":
        # v5.34: query whether compensation layer is active
        project_dir = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
        result = compensation_active(project_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if not result["active"] else 1)

    elif cmd == "classify":
        task = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not task:
            task = sys.stdin.read().strip()
        if not task:
            print(json.dumps({"error": "no task provided"}, ensure_ascii=False))
            sys.exit(1)
        result = classify_complexity(task)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "cot":
        task = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else sys.stdin.read().strip()
        if not task:
            print("Error: no task provided")
            sys.exit(1)
        print(emit_cot_prompt(task))

    elif cmd == "strict-cot":
        task = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else sys.stdin.read().strip()
        if not task:
            print("Error: no task provided")
            sys.exit(1)
        print(emit_strict_cot(task))

    elif cmd == "pipeline":
        task = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else sys.stdin.read().strip()
        if not task:
            print("Error: no task provided")
            sys.exit(1)
        analysis = classify_complexity(task)
        instructions = emit_pipeline_instructions(task, analysis)
        print(instructions)

    elif cmd == "verify":
        result = verify_pre_completion()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["status"] == "ok" else 1)

    elif cmd == "verify-pipeline":
        scan_dir = None
        if "--dir" in sys.argv:
            idx = sys.argv.index("--dir")
            scan_dir = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        result = verify_pipeline(scan_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["status"] == "ok" else 1)

    elif cmd == "escalate":
        task = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not task:
            task = sys.stdin.read().strip()
        if not task:
            print(json.dumps({"error": "no task provided"}, ensure_ascii=False))
            sys.exit(1)
        result = emit_escalate(task)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "trim":
        files = sys.argv[2:]
        if not files:
            print(json.dumps({"error": "no files provided"}, ensure_ascii=False))
            sys.exit(1)
        result = recommend_trim(files)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        print(f"Unknown command: {cmd}")
        print("Commands: classify, cot, strict-cot, pipeline, verify, verify-pipeline, escalate, trim")
        sys.exit(1)


if __name__ == "__main__":
    main()
