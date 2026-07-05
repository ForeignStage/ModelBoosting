#!/usr/bin/env python3
"""Static Routing Table — Mechanical task-agent matching layer.
Agent read-only. User-only modification. Not a rule. A roadblock.
"""
import re, json, sys, os
from enum import Enum
from datetime import datetime

class RouteDecision(Enum):
    CLAUDE_CODE_ONLY = "claude_code_only"
    CODEX_ONLY = "codex_only"
    EITHER = "either"
    CLAUDE_PREFERRED = "claude_preferred"
    CODEX_PREFERRED = "codex_preferred"
    BLOCKED = "blocked"
    HUMAN_REQUIRED = "human_required"

DANGER_PATTERNS = [
    {
        "patterns": [
            r"rm\s+-rf", r"del\s+/[fsq]", r"format\s+[cdef]",
            r"DROP\s+(TABLE|DATABASE)", r"TRUNCATE",
            r"chmod\s+777", r"chown\s+-R",
            r"shutdown", r"reboot", r"restart\s+server",
            r"delete\s+(all|everything|\u5168\u90e8)",
            r"\u5220\u9664\u6240\u6709", r"\u6e05\u7a7a\u6570\u636e\u5e93",
        ],
        "message": "DANGER: destructive operation. Human review required.",
    },
    {
        "patterns": [
            r"production", r"prod\b", r"\u7ebf\u4e0a", r"\u751f\u4ea7\u73af\u5883",
        ],
        "message": "DANGER: production environment. Human review required.",
    },
]

HARD_ROUTES = [
    {
        "patterns": [
            r"font|\u5b57\u4f53|\u5b57\u53f7|\u5b57\u91cd|\u884c\u9ad8|\u5b57\u95f4\u8ddd",
            r"color|\u989c\u8272|\u8272\u503c|\u6e10\u53d8|\u80cc\u666f\u8272|\u524d\u666f\u8272|\u8fb9\u6846\u8272",
            r"layout|\u5e03\u5c40|flex|grid|\u5bf9\u9f50|\u95f4\u8ddd|\u7559\u767d|padding|margin",
            r"animation|\u52a8\u753b|\u8fc7\u6e21|transition|transform|keyframes",
            r"hover|\u60ac\u505c|click|\u70b9\u51fb|modal|\u5f39\u7a97|dialog|\u63d0\u793a\u6846",
            r"responsive|\u54cd\u5e94\u5f0f|\u79fb\u52a8\u7aef|\u9002\u914d|\u65ad\u70b9|@media",
            r"CSS|\u6837\u5f0f|style|\.css|scss|sass|less|tailwind|bootstrap",
            r"UI|\u754c\u9762|\u9875\u9762|\u8bbe\u8ba1\u7a3f|\u89c6\u89c9|\u7f8e\u89c2|\u989c\u503c|\u597d\u770b|\u6f02\u4eae",
            r"dom|DOM|\u6e32\u67d3|\u91cd\u7ed8|\u56de\u6d41|\u865a\u62dfdom|vdom",
            r"svg|icon|\u56fe\u6807|logo|\u63d2\u56fe|\u7ed8\u5236|canvas",
        ],
        "decision": "claude_code_only",
        "reason": "UI/visual/style tasks require aesthetic judgment. DeepSeek underperforms here.",
    },
    {
        "patterns": [
            r"database|\u6570\u636e\u5e93|\u8868\u7ed3\u6784|\u5b57\u6bb5|\u7d22\u5f15|\u8fc1\u79fb|migration|schema",
            r"sql|SQL|\u67e5\u8be2|join|\u5b50\u67e5\u8be2|\u805a\u5408|group by|order by",
            r"transaction|\u4e8b\u52a1|\u9501|lock|\u6b7b\u9501|deadlock|\u9694\u79bb\u7ea7\u522b",
            r"API|\u63a5\u53e3|endpoint|\u8def\u7531|\u8bf7\u6c42|\u54cd\u5e94|REST|restful|graphql",
            r"\u5e76\u53d1|concurrency|parallel|\u5f02\u6b65|async|await|\u7ebf\u7a0b|\u8fdb\u7a0b|\u534f\u7a0b",
            r"\u7f13\u5b58|cache|redis|memcached",
            r"engine|\u5f15\u64ce|\u8ba1\u7b97|\u6279\u5904\u7406|batch|\u8c03\u5ea6|scheduler|cron",
            r"\u7f16\u7801|encoding|utf|\u4e71\u7801|\u5b57\u7b26\u96c6",
            r"orchestrator|\u7f16\u6392|\u7ba1\u9053|pipeline",
            r"Python|\.py|FastAPI|pydantic",
        ],
        "decision": "codex_only",
        "reason": "Backend/data tasks need rigorous reasoning. Claude Code lacks depth here.",
    },
    {
        "patterns": [
            r"\u4fee\u4e2abug|\u4fee\u590d\u5c0f\u95ee\u9898|\u5c0f\u8c03\u6574|\u5fae\u8c03|\u7b80\u5355\u6539|quick fix",
            r"\u6539\u4e2a\u6587\u6848|\u6587\u6848\u8c03\u6574|\u6539\u6587\u5b57|\u6539\u6807\u7b7e",
            r"\u6539\u4e2a\u53d8\u91cf\u540d|\u91cd\u547d\u540d|renam?e",
            r"\u5220\u9664\u6587\u4ef6|\u5220\u6389|\u79fb\u9664|remove",
        ],
        "decision": "either",
        "reason": "Low-risk trivial change. Either agent.",
    },
    {
        "patterns": [
            r"\u91cd\u6784|refactor|\u4ee3\u7801\u7ed3\u6784|\u76ee\u5f55\u91cd\u7ec4|\u6a21\u5757\u62c6\u5206|\u89e3\u8026",
            r"\u67b6\u6784|architecture|\u8bbe\u8ba1\u6a21\u5f0f|pattern|\u63a5\u53e3\u8bbe\u8ba1|\u62bd\u8c61",
            r"\u6280\u672f\u9009\u578b|\u9009\u578b|\u6846\u67b6\u5347\u7ea7|\u7248\u672c\u5347\u7ea7|\u4f9d\u8d56\u5347\u7ea7",
        ],
        "decision": "codex_preferred",
        "reason": "DeepSeek strong at reasoning. Sonnet preferred for review after.",
    },
    {
        "patterns": [
            r"\u5199\u6587\u7ae0|\u5199\u4f5c|\u6587\u6848|\u5c0f\u8bf4|\u6545\u4e8b|\u521b\u4f5c|creative",
            r"\u62a5\u544a|report|PPT|\u6f14\u793a|presentation",
            r"\u7ffb\u8bd1|translate|\u672c\u5730\u5316|i18n",
        ],
        "decision": "claude_preferred",
        "reason": "Creative/writing tasks benefit from Sonnet fluency.",
    },
]

def route_task(task_description: str) -> dict:
    for rule in DANGER_PATTERNS:
        for pattern in rule["patterns"]:
            if re.search(pattern, task_description, re.IGNORECASE):
                return {"decision": "human_required", "matched_pattern": pattern, "reason": rule["message"], "is_blocked": True}
    for rule in HARD_ROUTES:
        for pattern in rule["patterns"]:
            if re.search(pattern, task_description, re.IGNORECASE):
                return {"decision": rule["decision"], "matched_pattern": pattern, "reason": rule["reason"], "is_blocked": False}
    return {"decision": "blocked", "matched_pattern": None, "reason": "No routing rule matched. User must specify agent.", "is_blocked": True}

if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "--task":
        print(json.dumps({"error": "Usage: routing_table.py --task 'description'"}, ensure_ascii=False))
        sys.exit(1)
    task = sys.argv[2]
    result = route_task(task)
    result["timestamp"] = datetime.now().isoformat()
    result["task"] = task
    log_path = os.path.join(os.path.dirname(__file__), "route_log.json")
    log = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                log = json.load(f)
        except:
            log = []
    log.append(result)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log[-100:], f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(1 if result["is_blocked"] else 0)
