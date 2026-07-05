#!/usr/bin/env python3
"""PART 0 Model Self-Detection -- sqlite > toml > config.json priority.
Usage: python model_detect.py [search_dir] [--persist watchdog_dir]
Outputs calibration level for deepseek discipline enforcement.

v5.35 -- --persist writes calibration.json for all watchdog scripts to consume.
"""
import sys, os, json

DEEPSEEK = ("deepseek",)
FRONTIER = ("claude", "gpt", "opus", "sonnet", "gemini")

CALIBRATION_FILE = "calibration.json"

def _sqlite_model(base):
    try:
        import sqlite3
        for p in [os.path.join(base, "state_5.sqlite"), os.path.join(base, "..", "state_5.sqlite")]:
            if os.path.exists(p):
                conn = sqlite3.connect(p)
                row = conn.execute("SELECT model FROM threads ORDER BY id DESC LIMIT 1").fetchone()
                conn.close()
                if row and row[0]:
                    return row[0], "sqlite", "high"
    except Exception:
        pass
    return None, None, None

def _toml_model(base):
    for p in [os.path.join(base, "config.toml"), os.path.join(base, "..", "config.toml")]:
        if os.path.exists(p):
            try:
                for line in open(p, encoding="utf-8"):
                    k, _, v = line.partition("=")
                    if "model" in k.lower() and v.strip():
                        return v.strip().strip('"\''), "toml", "medium"
            except Exception:
                pass
    return None, None, None

def _json_model(base):
    for p in [os.path.join(base, "config.json"), os.path.join(base, "..", "config.json")]:
        if os.path.exists(p):
            try:
                d = json.load(open(p, encoding="utf-8"))
                m = d.get("model") or d.get("activeModel") or (d.get("provider") or {}).get("model")
                if m:
                    return m, "config.json", "low"
            except Exception:
                pass
    return None, None, None

def _settings_json_model(base):
    """Claude Code stores model in .claude/settings.json (or settings.local.json)."""
    for d in [base, os.path.join(base, ".."), os.path.expanduser("~")]:
        for fname in [".claude/settings.local.json", ".claude/settings.json"]:
            p = os.path.join(d, fname) if fname.startswith(".claude") else os.path.join(d, ".claude", fname)
            if os.path.exists(p):
                try:
                    d2 = json.load(open(p, encoding="utf-8"))
                    m = d2.get("model")
                    if m:
                        return m, fname, "medium"
                except Exception:
                    pass
    return None, None, None

def detect(base="."):
    for fn in (_sqlite_model, _toml_model, _json_model, _settings_json_model):
        model, source, confidence = fn(base)
        if model:
            break
    else:
        model, source, confidence = "unknown", "none", "none"

    lo = model.lower()
    if any(x in lo for x in DEEPSEEK):
        calibration = "elevated"
    elif any(x in lo for x in FRONTIER):
        calibration = "standard"
    else:
        calibration = "max_caution"

    return model, source, confidence, calibration


def persist_calibration(result, watch_dir):
    """Write calibration.json -- canonical model state for all watchdog scripts.

    All gate/audit/compensation scripts read this file FIRST before falling
    back to calling detect(). This removes the latency of repeated sqlite reads
    and eliminates the risk of agent non-compliance (agent can't "forget"
    to check calibration -- scripts enforce it programmatically).
    """
    payload = {
        "model": result[0],
        "source": result[1],
        "confidence": result[2],
        "calibration": result[3],
        "deepseek_active": result[3] in ("elevated", "max_caution"),
        "frontier_active": result[3] == "standard",
        "detected_at": __import__("datetime").datetime.now().isoformat(),
        "version": "v5.35"
    }
    os.makedirs(watch_dir, exist_ok=True)
    path = os.path.join(watch_dir, CALIBRATION_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def read_calibration(watch_dir):
    """Read cached calibration.json. Returns None if missing or stale (>1h)."""
    path = os.path.join(watch_dir, CALIBRATION_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Invalidate if older than 1 hour -- force re-detect
        from datetime import datetime, timedelta
        detected = datetime.fromisoformat(data.get("detected_at", "2000-01-01T00:00:00"))
        if datetime.now() - detected > timedelta(hours=1):
            return None
        return data
    except Exception:
        return None


def get_calibration(watch_dir=None, project_dir="."):
    """Canonical calibration resolver -- all watchdog scripts call this.

    Priority:
    1. calibration.json (if fresh) -- zero-latency cache
    2. model_detect.detect() -- live detection
    3. max_caution (conservative fallback)
    """
    # Layer 1: cached calibration
    if watch_dir:
        cached = read_calibration(watch_dir)
        if cached:
            return cached

    # Layer 2: live detection
    try:
        model, source, confidence, calibration = detect(project_dir)
        result = {
            "model": model,
            "source": source,
            "confidence": confidence,
            "calibration": calibration,
            "deepseek_active": calibration in ("elevated", "max_caution"),
            "frontier_active": calibration == "standard",
        }
        # Persist if watch_dir provided
        if watch_dir:
            persist_calibration((model, source, confidence, calibration), watch_dir)
        return result
    except Exception:
        return {
            "model": "unknown",
            "calibration": "max_caution",
            "deepseek_active": True,
            "frontier_active": False,
        }


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else os.getcwd()
    model, source, confidence, calibration = detect(base)
    print(f"[SELF-DETECTED] Model: {model}. Source: {source} ({confidence}). Calibration: {calibration.upper()}.")
    if calibration == "elevated":
        print("[DS-CALIBRATION] deepseek-v4 active -> gate MANDATORY, REANCHOR/3 tasks, CLARIFY-first.")
    elif calibration == "max_caution":
        print("[CAUTION] Unknown model -> maximum enforcement. Assume all rules may be bypassed.")

    # --persist: write calibration.json for watchdog scripts
    if "--persist" in sys.argv:
        idx = sys.argv.index("--persist")
        watch_dir = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else os.path.join(os.path.dirname(os.path.abspath(__file__)))
        p = persist_calibration((model, source, confidence, calibration), watch_dir)
        print(f"[PERSIST] calibration -> {p}")

    sys.exit(0)
