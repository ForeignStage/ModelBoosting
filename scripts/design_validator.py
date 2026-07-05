#!/usr/bin/env python3
"""Design Validator — Mechanical CSS compliance checker.
Like enforce.py but for frontend. Returns non-zero = fix required.
"""
import re, sys, os, json
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Design spec (sync with frontend-designer/references/design-spec.md)
SPACING_UNIT = 4
TYPE_SCALE = {12, 14, 16, 18, 20, 24, 30, 36}
COLOR_PALETTE = {
    "#ffffff", "#0f172a", "#f8fafc", "#1e293b",
    "#475569", "#94a3b8", "#e2e8f0", "#334155",
    "#3b82f6", "#60a5fa", "#2563eb",
    "#22c55e", "#4ade80", "#f59e0b", "#fbbf24",
    "#ef4444", "#f87171",
}
MIN_CONTRAST = 4.5
MIN_TOUCH_TARGET = 44
MAX_Z_INDEX = 50

def check_spacing(css_text):
    """All px values should be multiples of 4."""
    violations = []
    for m in re.finditer(r'(\w[\w-]*)\s*:\s*(\d+)px', css_text):
        prop, val = m.group(1), int(m.group(2))
        if prop in ('font-size', 'line-height', 'font-weight', 'border-width'):
            continue
        if val % SPACING_UNIT != 0 and val > 0:
            violations.append(f"  {prop}: {val}px (not multiple of {SPACING_UNIT}px)")
    return violations

def check_colors(css_text):
    """All hex colors should be from palette."""
    violations = []
    for m in re.finditer(r'#[0-9a-fA-F]{6}', css_text):
        color = m.group(0).lower()
        if color not in {c.lower() for c in COLOR_PALETTE}:
            violations.append(f"  {color} (not in design palette)")
    return violations

def check_type_scale(css_text):
    """Font sizes should match type scale."""
    violations = []
    for m in re.finditer(r'font-size\s*:\s*(\d+)px', css_text):
        size = int(m.group(1))
        if size not in TYPE_SCALE and size > 8:
            violations.append(f"  font-size: {size}px (not in type scale {sorted(TYPE_SCALE)})")
    return violations

def check_z_index(css_text):
    """Z-index should not exceed 50."""
    violations = []
    for m in re.finditer(r'z-index\s*:\s*(-?\d+)', css_text):
        val = int(m.group(1))
        if val > MAX_Z_INDEX:
            violations.append(f"  z-index: {val} (max {MAX_Z_INDEX})")
    return violations

def check_touch_targets(css_text):
    """Interactive elements should be >= 44x44px."""
    violations = []
    # Check buttons, links styled as buttons
    blocks = re.split(r'}', css_text)
    for block in blocks:
        if not block.strip():
            continue
        selectors = block.split('{')[0] if '{' in block else ''
        if re.search(r'(button|\[role="button"\]|\.btn)', selectors, re.I):
            w = re.search(r'min-width\s*:\s*(\d+)px', block)
            h = re.search(r'min-height\s*:\s*(\d+)px', block)
            pw = re.search(r'padding\s*:\s*(\d+)px', block)
            if (w and int(w.group(1)) < MIN_TOUCH_TARGET) or (h and int(h.group(1)) < MIN_TOUCH_TARGET):
                if not (pw and int(pw.group(1)) >= 12):  # padded buttons can be smaller
                    violations.append(f"  {selectors.strip()[:60]}: touch target < {MIN_TOUCH_TARGET}px")

    return violations

def check_file(filepath):
    """Run all checks on a CSS file."""
    if not os.path.exists(filepath):
        return {"status": "error", "message": f"File not found: {filepath}"}

    with open(filepath, "r", encoding="utf-8") as f:
        css = f.read()

    results = {
        "spacing": check_spacing(css),
        "colors": check_colors(css),
        "type_scale": check_type_scale(css),
        "z_index": check_z_index(css),
        "touch_targets": check_touch_targets(css),
    }

    total_violations = sum(len(v) for v in results.values())
    return {
        "status": "fail" if total_violations > 0 else "pass",
        "file": filepath,
        "violations": total_violations,
        "details": {k: v for k, v in results.items() if v},
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: design_validator.py <file.css>")
        print("       design_validator.py --check-dir <directory>")
        sys.exit(1)

    if sys.argv[1] == "--check-dir":
        directory = sys.argv[2]
        all_results = []
        for root, dirs, files in os.walk(directory):
            for f in files:
                if f.endswith(".css"):
                    fp = os.path.join(root, f)
                    all_results.append(check_file(fp))

        total = sum(r["violations"] for r in all_results)
        output = {
            "status": "fail" if total > 0 else "pass",
            "files_checked": len(all_results),
            "total_violations": total,
            "files": [r for r in all_results if r["violations"] > 0],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        sys.exit(0 if total == 0 else 1)
    else:
        result = check_file(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["status"] == "pass" else 1)
