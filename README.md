# AgentBoosting — GodCreating

**AI Agent 运行时监控与补偿系统** — 为 DeepSeek 等非前沿模型提供机械化的质量保证层。

## 问题

DeepSeek-v4-pro 等模型在复杂工程任务上与 Claude/GPT 等前沿模型存在差距：
- 没有原生 Extended Thinking（链式推理）
- 容易产生幻觉（虚构不存在的 API/模块）
- 代码变更可能破坏合约或引入回归
- 缺乏结构化的任务分解和自我审查

## 解决方案

一个**外部化的 Watchdog 引擎**，通过多层机械检查来补偿模型能力差距：

```
任务进来 → 复杂度评估 → CoT 注入 → 代码生成 → 幻觉检测 → 合约验证 → 质量门禁 → 通过/驳回
```

## 核心模块

### 🔍 `watchdog/` — 看门狗引擎

| 文件 | 功能 |
|------|------|
| `enforce.py` | **主引擎** (1116行) — 完整性校验、心跳、预算管理、锁定机制 |
| `deepseek_compensation.py` | **DeepSeek 补偿引擎** — CoT 注入、复杂度分类、D→I→R 管线编排 |
| `halcheck_live.py` | **实时幻觉检测** — AST 解析 + importlib 验证，纯静态分析 |
| `hallucination_check.py` | **快速幻觉检测** — 第一遍轻量过滤 |
| `code_quality_gate.py` | **代码质量门禁** — 提交前自动质量检查 |
| `contract_check.py` | **合约校验** — 确保输出符合 API 合约定义 |
| `self_audit.py` | **自我审计** — Agent 对自身输出的二次检查 |
| `self_review_injector.py` | **自我审查注入** — 在流程中插入审查步骤 |
| `diff_since_handoff.py` | **差异对比** — 检查任务交接后的变更 |
| `multi_pass_reason.py` | **多轮推理** — 对关键决策多次独立推理交叉验证 |
| `context_injector.py` | **上下文注入** — 动态注入项目上下文到会话 |
| `req_expand.py` | **需求展开** — 模糊需求展开为具体验收标准 |
| `verify_task.py` | **任务验证** — 验证任务是否真正完成 |
| `dead_agent_detector.py` | **死锁检测** — 检测卡死的 Agent |
| `fix_mojibake.py` | **乱码修复** — 检测和修复编码损坏 |
| `daemon_tick.py` | **守护进程 Tick** — 后台定时检查 |
| `task_poller.py` | **任务轮询** — 主动拉取待处理任务 |
| `auto_executor.py` | **自动执行器** — 自动执行已验证的任务 |
| `auto_loop_global.py` | **全局自动循环** — 持续循环处理 |
| `global_bootstrap.py` | **全局引导** — 项目初始化引导 |
| `fs_watcher.py` | **文件系统监听** — 监控项目文件变更 |
| `model_detect.py` | **模型检测** — 识别当前使用的模型 |
| `set_mode.py` | **模式切换** — 切换 ELEVATED/STANDARD 校准 |
| `web_fetch.py` | **Web 抓取** — 带验证的远程内容获取 |

### 🔗 `hooks/` — Claude Code 钩子

| 文件 | 触发时机 |
|------|---------|
| `pre_write.py` | 写文件前 — 权限、范围检查 |
| `post_write.py` | 写文件后 — 完整性校验、自动备份 |
| `session_start.py` | 会话启动 — 模型检测、模式配置、上下文注入 |

### 🛠 `skills/` — 可复用 Skill 定义

| 文件 | 用途 |
|------|------|
| `SKILL_DEBUG.md` | 调试技巧和检查清单 |
| `SKILL_FASTAPI.md` | FastAPI 后端开发 |
| `SKILL_FRONTEND.md` | 前端开发 |
| `SKILL_SQLITE.md` | SQLite 数据库操作 |
| `SKILL_DEEPSEEK_DISCIPLINE.md` | DeepSeek 使用规范和补偿策略 |

### 📋 `templates/` — 任务模板

| 文件 | 用途 |
|------|------|
| `HANDOFF_TEMPLATE.md` | Agent 任务交接 |
| `INTERRUPT_TEMPLATE.md` | 中断恢复 |
| `TASK_QUEUE_TEMPLATE.md` | 任务队列 |

### ⚙️ `scripts/` — 辅助工具

| 文件 | 功能 |
|------|------|
| `design_validator.py` | 设计文档验证 |
| `vision_bridge.py` | 视觉桥接（多模态） |

### 🚀 `bat/` — Windows 部署脚本

开机自启、守护进程、任务调度 — 让系统在 Windows 上无人值守运行。

### 🔀 `routing/`

| 文件 | 功能 |
|------|------|
| `routing_table.py` | Agent 路由规则 — 按任务类型分发到最合适的 Agent |

## 快速开始

```bash
# 1. 检测当前模型
python watchdog/model_detect.py

# 2. 任务复杂度评估
python watchdog/deepseek_compensation.py classify "写一个用户认证系统"

# 3. 生成 CoT 注入 Prompt
python watchdog/deepseek_compensation.py cot "写一个用户认证系统"

# 4. 对生成代码做幻觉检测
python watchdog/halcheck_live.py your_file.py

# 5. 运行完整门禁
python watchdog/enforce.py check-all

# 6. 预完成验证
python watchdog/deepseek_compensation.py verify
```

## 校准模式

| 模式 | 触发条件 | 行为 |
|------|---------|------|
| **ELEVATED** | 检测到 DeepSeek | 全补偿管线：CoT + D→I→R + 幻觉检测 + 验证 |
| **STANDARD** | 检测到前端模型 | 补偿层自动绕过，模型原生处理 |

## 架构原则

- **机械执行，不依赖模型判断** — 看门狗是确定性代码
- **外部化补偿** — 不修改模型，在外部添加质量控制层
- **失败即停止** — 门禁不通过则中断，不降级
- **多层纵深防御** — 快速初检 + 深度分析 + 合约验证

## 与 Claude Code 集成

CLAUDE.md 中的所有规则（模型检测、CoT 注入、变更验证、门禁检查）均由 watchdog 自动执行。会话启动时 `hooks/session_start.py` 注入上下文，`pre_write.py` / `post_write.py` 在每次文件写入时生效。

## License

Private — ForeignStage
