# AGENTS.md -> ../AgentBoosting/宪法/AGENTS.md (v5.33 MECHANICAL)

## EDIT GATE — MECHANICAL. EVERY WRITE. NO EXCEPTIONS.
BEFORE Write/Edit ANY file (CHECK EXIT CODE: != 0 = DO NOT WRITE):
  python E:\AgentHub\AgentBoosting\GodCreating\watchdog\codex_gate.py pre  <filepath>
AFTER Write/Edit ANY .py file:
  python E:\AgentHub\AgentBoosting\GodCreating\watchdog\codex_gate.py post <filepath>
  Verify FAIL (exit != 0) = task NOT complete. Fix and re-run post.

A codex_enforcer_daemon monitors the filesystem. Files edited without pre gate
trigger EMERGENCY_STOP within 5 minutes. This is mechanical, not advisory.

## STARTUP (exit != 0 at any step = DO NOT PROCEED)
1. python E:\AgentHub\AgentBoosting\GodCreating\watchdog\model_detect.py .
2. python E:\AgentHub\AgentBoosting\GodCreating\watchdog\enforce.py boot --renew
3. python E:\AgentHub\AgentBoosting\GodCreating\watchdog\enforce.py check-all
4. python E:\AgentHub\AgentBoosting\GodCreating\watchdog\enforce.py heartbeat --touch
5. python E:\AgentHub\AgentBoosting\GodCreating\watchdog\deepseek_gate.py "startup" watchdog/
6. python E:\AgentHub\AgentBoosting\GodCreating\watchdog\enforce.py locks --expire

## BLOOD RULES (Any violation = STOP)
- PowerShell/Bash echo/heredoc to .py = STOP. Use Python open().write().
- Domain: backend/api/*.py/*.db/config ONLY. static/ is FORBIDDEN.
- COMPLETED only after VERIFY PASS.
- Server/file state claims = <2min curl/Read. Never from memory.
- Ambiguous input = CLARIFY. Never default to EXECUTE.
- Every 3 tasks: REANCHOR (re-read PART 1 Blood Rules).
- Every 3 actions: ANCHOR output.

## FUSE
After task completion:
  python E:\AgentHub\AgentBoosting\GodCreating\watchdog\enforce.py fuse --auto-track codex

## SKILLS
E:\AgentHub\AgentBoosting\GodCreating\skills\SKILL_DEEPSEEK_DISCIPLINE.md
E:\AgentHub\AgentBoosting\GodCreating\skills\SKILL_FASTAPI.md
E:\AgentHub\AgentBoosting\GodCreating\skills\SKILL_SQLITE.md
E:\AgentHub\AgentBoosting\GodCreating\skills\SKILL_DEBUG.md
