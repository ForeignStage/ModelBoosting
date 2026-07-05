# SKILL: DeepSeek Discipline (inject at EVERY task start for deepseek-v4-pro/flash)

## BOOT LINE (output immediately)
`[DS-DISCIPLINE v1.0] deepseek-v4 active. Elevated rules. Mode: [EXPLORE|EXECUTE|CLARIFY]`

---

## Step -2: Pre-Task Enhancement (non-trivial tasks only)
```
# Expand implicit requirements
python E:\AgentHub\_shared\watchdog\req_expand.py "[task]" --agent [agent] [root]
# Inject relevant codebase context
python E:\AgentHub\_shared\watchdog\context_injector.py "[task]" [root]
# Complex task (>3 files): multi-pass reasoning
python E:\AgentHub\_shared\watchdog\multi_pass_reason.py "[task]" --agent [agent] [root]
```
Read docs/REQUIREMENTS_EXPANDED.md + CONTEXT_INJECTION.md before writing scope.
Skip for trivial/single-line fixes.

---

## Step -1: Chain-of-Thought Injection (MANDATORY for deepseek — before ANY code or file change)
Output a THINK block before acting:
```
THINK:
1. What exactly does this task require? (be precise)
2. Which files will I change and why each one?
3. What could go wrong / what are the edge cases?
4. What is the MINIMAL change needed (avoid scope creep)?
5. What would Opus 4.8 do differently here?
END THINK
```
Only proceed after completing THINK. This compensates for weaker native CoT.

---

## Step 0: Self-Audit (MANDATORY — before ANY file edit)
```
python E:\AgentHub\_shared\watchdog\self_audit.py [--no-scope] [--no-backup] [project_root]
```
- Exit 0 = Q1-Q5 pass. Exit 1 = STOP.

---

## Step 1: Pre-Execution Gate (MANDATORY — runs before ANY file edit)
```
python E:\AgentHub\_shared\watchdog\deepseek_gate.py "[task description]" watchdog/
```
- Exit 0 = GO
- Exit 1 = STOP → read CLARIFY_PENDING.md → fix → re-run gate

---

## Mode Detection (first match wins)
| Signal | Mode |
|--------|------|
| "写入" "执行" "开工" "干" "修" "部署" + no ? | EXECUTE |
| Ends with ? or ？, or "如何" "你觉得" "探讨" | EXPLORE |
| Both signals, or empty/vague | CLARIFY (default) |

**EXPLORE = discuss only, write nothing.**
**CLARIFY = ask user before doing anything.**

---

## Post-Task Delegation Check (MANDATORY before COMPLETED)
```
python E:\AgentHub\_shared\watchdog\delegation_check.py --agent codex [project_root]
```
- Exit 0 = no cross-domain work, OK
- Exit 2 = auto-queued to other agent, confirm TASK_QUEUE.md updated

---

## REANCHOR (every 3 completed tasks)
Re-read PART 1 (Blood Rules) of AGENTS.md fully.
Output: `[REANCHOR] Blood Rules re-read at [timestamp]`

---

## Context Anchor (every 3 actions within a task)
Output: `ANCHOR: [task name] | Step [N] | Mode: [current]`

---

## Vision Gap (image/screenshot/photo in input)
NEVER guess or describe from memory. ALWAYS:
```
python E:\AgentHub\_shared\scripts\vision_bridge.py "[image_path]" docs/
```
Read the generated `IMG_DESC_*.md`, then proceed as normal text task.

---

## Known DeepSeek Failure Modes
| Failure | Symptom | Block |
|---------|---------|-------|
| EXECUTE default | Writes code on ambiguous input | deepseek_gate.py STOP |
| Context drift | Forgets task scope after 10+ steps | ANCHOR output every 3 actions |
| Hallucinated state | "server is probably running" | Blood Rule 1.5: verify (<2min curl) |
| Scope creep | Edits files not in SCOPE_active.md | gate checks scope exists |
| Image hallucination | Describes image without vision | vision_bridge.py MANDATORY |
| Rule amnesia | Stops following constitution mid-task | REANCHOR every 3 tasks |
