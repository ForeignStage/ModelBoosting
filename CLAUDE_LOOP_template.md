# Claude Code Overnight Loop — TEMPLATE v6
# Copy to project root as CLAUDE_LOOP.md and customize PROJECT_PATH.

PROJECT_PATH = E:\AgentHub\AgentProjects\[project]

## Session Startup (run ONCE at session start)
S1. RUN `python watchdog/enforce.py mode --set overnight`
S2. RUN `python watchdog/enforce.py boot --renew` → if expired: `boot --complete`
S3. READ latest `docs/HANDOFF_CC_*.md` (context recovery after restart)
S4. Output: `BOOT OK — CLAUDE_LOOP v6 | mode: overnight | ready`

## Loop Protocol (DO NOT STOP until EMERGENCY_STOP exists)

For each iteration:
1. READ [PROJECT_PATH]\docs\TASK_QUEUE.md
2. CHECK docs/EMERGENCY_STOP — if exists: generate final HANDOFF, output "CLAUDE CODE STOPPED", STOP
3. Check QUEUED — Claude Code for tasks
4. If task exists AND no file lock conflict:
   0. READ E:\AgentHub\AgentBoosting\GodCreating\AGENTS_CHEATSHEET.md (every task, no exception)
   0a. RUN `python watchdog/enforce.py fail --read` → note recent failure patterns
   0b. RUN `python watchdog/enforce.py task-reset` (reset per-task spiral counter)
   0c. RUN `python watchdog/enforce.py route --task "[task description]"`:
       - CLAUDE_CODE_ONLY / CC_PREFERRED / EITHER → proceed
       - CODEX_ONLY → re-queue under `QUEUED — Codex`, write HANDOFF, skip to next task
       - HUMAN_REQUIRED → write docs/IDLE_ALERT.md, skip to next task
   a. RUN `python watchdog/enforce.py check-all`:
      - overall=go → proceed
      - no_go AND boot expired → RUN `python watchdog/enforce.py boot --renew` → re-check; still no_go → write HANDOFF, STOP
      - no_go other reason → wait 2 min, retry once; still no_go → write HANDOFF, STOP
   a1. CHECK task step count: if >5 steps → split sub-tasks, mark [BLOCKED-SPLIT], restart loop
   b. READ matching skill files from E:\AgentHub\AgentBoosting\GodCreating\skills\
   b1. COUNT [REANCHOR] in COMPLETED — if total mod 3 == 0 and total > 0: re-read AGENTS.md PART 1
   c. WRITE docs/SCOPE_active.md: Task / Will write / Done when
   d. Claim task (add [IN PROGRESS — Claude Code])
   e. Execute: plan → code → verify
   f. RUN `python watchdog/verify_task.py [changed .py files]` → FAIL: log failure, re-queue, skip
   g. SELF-ASSESS: lower frontend score by 0.3-0.5 points; FIND 5+ defects; FIX each
   h. WRITE docs/HANDOFF_CC_[timestamp].md (`spiral --touch TASK_QUEUE.md --exempt`)
   h1. RUN `python watchdog/enforce.py verify --check` → fail: re-run verify_task.py, retry; still fail: mark [NEEDS-VERIFY], re-queue, skip
   h2. IF improvement found → `python watchdog/enforce.py improve --propose "..." --category [rules|skill|loop]`
   h3. RUN `python watchdog/enforce.py heartbeat --touch`
   i. UPDATE TASK_QUEUE.md: mark COMPLETED (`spiral --touch TASK_QUEUE.md --exempt`)
   j. WRITE 0 to docs/CC_IDLE_COUNT.txt
   k. SCHEDULE next iteration (CronCreate recurring=false, durable=true, +1 min)
5. If no tasks:
   a. Increment docs/CC_IDLE_COUNT.txt
   b. N==1: append CC REQUEST to TASK_QUEUE.md
   c. N>=20: output "NO TASKS — IDLE STOP", RUN `python watchdog/enforce.py mode --set interactive`, STOP
   d. N==15: write docs/MORNING_REPORT.md, schedule +10 min (durable=true)
   e. N>=5: schedule +5 min (durable=true); else +1 min (durable=true)
6. CHECK file locks before every edit

## Constraints
- ONLY touch files in static/ (frontend domain)
- NEVER touch backend/ api/ (Codex domain)
- Respect locks in watchdog/locks/

## Stop Conditions
- docs/EMERGENCY_STOP exists
- Fuse blown
- 20 consecutive idle loops
- On any STOP: RUN `python watchdog/enforce.py mode --set interactive`
