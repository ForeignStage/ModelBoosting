# OPERATIONAL CHEATSHEET — 任务前必读（每次）v5.34

## 启动检查（按序，缺一不可）
```
python watchdog/enforce.py mode --set overnight   → 自动模式
python watchdog/enforce.py boot --renew           → 续期token（首次用 boot --complete）
python watchdog/enforce.py check-all              → go? 否则STOP
```
写 docs/SCOPE_active.md：
```
Task: [精确任务名]
Will write: [文件列表]
Done when: [可测试条件]
```

## 域边界（违反=立即停止）
| 我是Codex | 我是Claude Code |
|-----------|----------------|
| backend/ api/ main.py *.db 配置 | static/ HTML CSS JS |
| 禁止碰 static/ | 禁止碰 backend/ api/ |

## 编辑文件前（顺序不可乱）
1. `enforce.py backup --target [file]`（>50行必须）
2. **先Read，再Write/Edit**（从不用Bash echo写文件）
3. 检查锁：`watchdog/locks/[file].lock` 存在且未过期？→ 等待

## 完成任务前（必须全通过）
```
python watchdog/verify_task.py [改动的.py文件]
python watchdog/enforce.py verify --check   → 必须PASS
```

## 预算记录
```
python watchdog/enforce.py fuse --incr [tokens] --model [pro|flash] --type [input|output]
```

## 绝对禁止
- Bash echo/heredoc 写任何文件
- 越域操作
- 凭记忆报服务器状态（必须有2min内curl验证）
- 没有VERIFY PASS就标COMPLETED

## Skill注射（任务前读对应文件）
E:\AgentHub\AgentBoosting\GodCreating\skills\SKILL_FASTAPI.md
E:\AgentHub\AgentBoosting\GodCreating\skills\SKILL_SQLITE.md
E:\AgentHub\AgentBoosting\GodCreating\skills\SKILL_FRONTEND.md
E:\AgentHub\AgentBoosting\GodCreating\skills\SKILL_DEBUG.md
E:\AgentHub\AgentBoosting\GodCreating\skills\SKILL_DEEPSEEK_DISCIPLINE.md  <- deepseek必读

## DeepSeek补偿层（v5.34 — frontier模型自动跳过）
```
# 检查补偿层是否激活
python E:\AgentHub\AgentBoosting\GodCreating\watchdog\deepseek_compensation.py check [project_dir]
# → {"active": false} = frontier模型，以下全部跳过
# → {"active": true}  = deepseek模型，以下强制执行

# Session启动（H1 Anti-Amnesia，代码修改前必跑）
E:\AgentHub\AgentBoosting\GodCreating\bat\ds_boot.bat [watchdog_dir]

# 任务开始门（任何文件修改前）
E:\AgentHub\AgentBoosting\GodCreating\bat\ds_task_start.bat "任务描述" [watchdog_dir]
  或直接：python E:\AgentHub\AgentBoosting\GodCreating\watchdog\deepseek_gate.py "[任务描述]" watchdog/

# 模型自检（PART 0）
python E:\AgentHub\AgentBoosting\GodCreating\watchdog\model_detect.py [project_dir]

# 图像处理（需要ANTHROPIC_API_KEY）
python E:\AgentHub\AgentBoosting\GodCreating\scripts\vision_bridge.py "[图片路径]" docs/
```
- Gate: Exit 0=GO，Exit 1=STOP（读 docs\CLARIFY_PENDING.md）
- 每3个已完成任务：REANCHOR（重读PART 1血规则）
- 每3个动作：输出 ANCHOR: [任务] | Step [N] | Mode: [模式]
- Calibration: ELEVATED=deepseek强制所有13.x规则，STANDARD=frontier自动绕过所有补偿

## 结构性协调（v5.28+）
```
# 每个 Agent session 开头：领取待办任务
python E:\AgentHub\AgentBoosting\GodCreating\watchdog\task_poller.py --agent codex [root]
python E:\AgentHub\AgentBoosting\GodCreating\watchdog\task_poller.py --agent claude_code [root]
# Exit 0=没任务  Exit 2=已认领任务(执行它)
```
- fs_watcher 后台常驻，检测 TASK_QUEUE.md 变化 → 自动写 CC_WAKEUP.md / CODEX_WAKEUP.md
- 任务出现 2秒内 wakeup 文件就绪，下次 session 启动即刻认领

## 自动模式 v5.29
```
# 单次执行（auto模式自动调CLI；interactive模式写prompt文件）
python E:\AgentHub\AgentBoosting\GodCreating\watchdog\auto_executor.py --agent codex --mode auto [root]

# 持续循环（仅熔断停止）
E:\AgentHub\AgentBoosting\GodCreating\bat\auto_loop.bat codex [root]
E:\AgentHub\AgentBoosting\GodCreating\bat\auto_loop.bat claude_code [root]

# 任务前自审（H3 Q1-Q5）
python E:\AgentHub\AgentBoosting\GodCreating\watchdog\self_audit.py [--no-scope] [root]

# 新项目全局接入
python E:\AgentHub\AgentBoosting\GodCreating\watchdog\global_bootstrap.py [project_root]
```
