# SKILL: Debug Flow — Systematic Process

## Step 1: Reproduce (2 min max)
```
Minimal reproduction: smallest input that triggers the bug.
If can't reproduce → it's an environment issue, not a code bug.
```

## Step 2: Isolate (read before guessing)
```
1. Read the error message completely — last line is usually the cause
2. Read the file at the exact line number in the traceback
3. Check: what changed last? (git diff HEAD~1)
```

## Step 3: Form ONE hypothesis
```
"I think X is happening because Y"
Test it with a print/log before touching code.
Never change 2 things at once.
```

## Python debugging
```python
# Quick print debug
import json; print(json.dumps(vars(obj), default=str, indent=2))

# Check type
print(type(x), repr(x))

# Trace execution
import traceback; traceback.print_stack()
```

## HTTP/API debugging
```bash
# Check server is up
curl -s http://localhost:8000/ -w "\nHTTP %{http_code}\n"

# Inspect response
curl -s -X POST http://localhost:8000/endpoint \
  -H "Content-Type: application/json" \
  -d '{"key":"value"}' | python -m json.tool
```

## SQLite debugging
```python
# Check what's in the DB
import sqlite3
conn = sqlite3.connect("state.db")
for row in conn.execute("SELECT * FROM table_name LIMIT 5"):
    print(row)
```

## When stuck (2-attempt rule)
```
Attempt 1 fails → read the error again, not the code
Attempt 2 fails → STOP. Diagnose root cause. Switch approach.
Never patch the same line 3 times.
```

## Common patterns
| Symptom | First check |
|---------|------------|
| ImportError | Virtual env activated? Right Python? |
| 422 Unprocessable | Request body schema mismatch |
| CORS error | Middleware order / origin config |
| DB locked | Unclosed session / transaction |
| Infinite loop | Missing base case / wrong condition |
| None where object expected | Missing db.refresh() / wrong query |
