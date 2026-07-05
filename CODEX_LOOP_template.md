# Codex Overnight Loop — TEMPLATE v1
# Copy to project root as CODEX_LOOP.md and customize PROJECT_PATH.

PROJECT_PATH = E:\AgentHub\AgentProjects\[project]

## Session Startup (run ONCE at session start)
S1. RUN `python watchdog/enforce.py mode --set overnight`
S2. RUN `python watchdog/enforce.py boot --renew` → if expired: `boot --complete`
S3. READ latest `docs/HANDOFF_CX_*.md` (context recovery after restart)
S4. Output: `BOOT OK — CODEX_LOOP v1 | mode: overnight | ready`

## Loop Protocol (DO NOT STOP until EMERGENCY_STOP exists)

For each iteration:
1. READ [PROJECT_PATH]\docs\TASK_QUEUE.md
2. CHECK docs/EMERGENCY_STOP — if exists: generate final HANDOFF_CX_[timestamp].md, output "CODEX STOPPED", STOP
3. CHECK QUEUED — Codex for tasks
4. If task exists AND no file lock conflict:
   0. READ E:\AgentHub\AgentBoosting\GodCreating\AGENTS_CHEATSHEET.md (every task, no exception)
   0a. RUN `python watchdog/enforce.py fail --read` → note recent failure patterns
   0b. RUN `python watchdog/enforce.py task-reset` (reset per-task spiral counter)
   0c. RUN `python watchdog/enforce.py route --task "[task description]"`:
       - CODEX_ONLY / CODEX_PREFERRED / EITHER → proceed
       - CLAUDE_CODE_ONLY → re-queue under `QUEUED — Claude Code`, skip to next task
       - HUMAN_REQUIRED → write docs/IDLE_ALERT.md, skip to next task
   a. RUN `python watchdog/enforce.py check-all`:
      - overall=go → proceed
      - no_go AND boot expired → RUN `python watchdog/enforce.py boot --renew` → re-check; still no_go → write HANDOFF_CX, STOP
      - no_go other reason → wait 2 min, retry once; still no_go → write HANDOFF_CX, STOP
   a1. CHECK task step count: if >5 steps → split sub-tasks, mark [BLOCKED-SPLIT], restart loop
   b. READ matching skill files: SKILL_FASTAPI.md / SKILL_SQLITE.md / SKILL_DEBUG.md
   b1. COUNT [REANCHOR] in COMPLETED — if total mod 3 == 0 and total > 0: re-read AGENTS.md PART 1
   c. WRITE docs/SCOPE_active.md: Task / Will write / Done when
   d. Claim task (add [IN PROGRESS — Codex])
   e. Execute: plan → code → verify
   f. RUN `python watchdog/verify_task.py [changed .py files]` → FAIL: log failure, re-queue, skip
   g. RUN `python watchdog/enforce.py fuse --incr [tokens] --model pro --type output`
   h. WRITE docs/HANDOFF_CX_[timestamp].md (`spiral --touch TASK_QUEUE.md --exempt`)
   h1. RUN `python watchdog/enforce.py verify --check` → fail: re-run verify_task.py, retry; still fail: mark [NEEDS-VERIFY], re-queue, skip
   h2. IF improvement found → `python watchdog/enforce.py improve --propose "..." --category [rules|skill|loop]`
   h3. RUN `python watchdog/enforce.py heartbeat --touch`
   i. UPDATE TASK_QUEUE.md: mark COMPLETED; if frontend impact → write task under `QUEUED — Claude Code` (`spiral --touch TASK_QUEUE.md --exempt`)
   j. WRITE 0 to docs/CX_IDLE_COUNT.txt
   k. SCHEDULE next: CronCreate recurring=false, durable=true, +1 min
5. If no tasks:
   a. Increment docs/CX_IDLE_COUNT.txt
   b. N==1: append CX REQUEST to TASK_QUEUE.md
   c. N>=20: output "NO TASKS — IDLE STOP", RUN `python watchdog/enforce.py mode --set interactive`, STOP
   d. N==15: write docs/MORNING_REPORT_CX.md, schedule +10 min (durable=true)
   e. N>=5: schedule +5 min (durable=true); else +1 min (durable=true)
6. CHECK file locks before every edit

## Constraints
- ONLY touch files in backend/ api/ main.py *.db config files
- NEVER touch static/ HTML CSS JS (Claude Code domain)
- Respect locks in watchdog/locks/
- Track budget with `fuse --incr` after each task

## Stop Conditions
- docs/EMERGENCY_STOP exists
- Fuse blown
- 20 consecutive idle loops
- On any STOP: RUN `python watchdog/enforce.py mode --set interactive`
