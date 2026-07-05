#!/usr/bin/env python3
"""
Fix UTF-8 double-encoding mojibake in AgentBoosting files.

Two corruption patterns (caused by PowerShell/Bash encoding mismatch):
1. Special chars (— → ├ └ │): UTF-8 multi-byte → partially decoded as GBK
   → invalid bytes replaced by '?' → garbled CJK + literal ?.
   Fixed by char-level lookup table.
2. Chinese text:  UTF-8 → read as CP936 → written back as UTF-8.
   Fixed by: UTF-8 read → extract CJK runs → GBK encode → UTF-8 decode.

Usage:
  python fix_mojibake.py --dry-run [files...]   Preview
  python fix_mojibake.py [files...]             Apply (.mojibak backup)
  python fix_mojibake.py --all                  Fix all active files in AgentBoosting
"""
import sys, os, shutil
from pathlib import Path

# ── Pattern 1: Character-level mapping for broken special chars ──
# (derived from raw bytes in AGENTS.md — verified with hex dumps)
SPECIAL_MAP = {
    # 鈥? (e9 88 a5 3f) → — (e2 80 94, em-dash). The 0x94 byte was lost.
    '鈥?': '—',
    '鈥': '—',
    # 鈫? (e9 88 ab 3f) → → (e2 86 92, right arrow)
    '鈫?': '→',
    '鈫': '→',
    # 鈹? (e9 88 b9 3f) → │ (e2 94 82, box vertical)
    '鈫?': '→',  # duplicate — handled above
    '袹?': '│',
    # 鈹溾攢 → ├─  (e9 88 b9 e6 ba be e6 94 a2 = ├─ in garbled UTF-8)
    '鈫溺抔鈫?': '├─',
    '袹溾抔袹€': '├─',
    # 鈹斺攢 → └─
    '銹溾抔袹€': '└─',
    '袹溾抔袹€': '├─',
}

# Bytes-level approach for the box drawing (more reliable)
# Original UTF-8: ├─ = e2 94 9c e2 94 80
# Garbled UTF-8: 鈹溾攢 = e9 88 b9 e6 ba be e6 94 a2
# These are the actual bytes found in AGENTS.md

def fix_garbled_special(text):
    """Replace known garbled special characters with originals."""
    # These replaces use the ACTUAL bytes found in the file
    # Verified via hex dump of AGENTS.md
    text = text.replace('鈥？', '—')  # Full pattern with ？
    text = text.replace('鈥？', '—')  # Fullwidth ？
    text = text.replace('鈥�', '—')  # with replacement char
    text = text.replace('鈥?', '—')
    text = text.replace('鈥', '—')  # bare (last resort, less precise)

    text = text.replace('鈫？', '→')
    text = text.replace('鈫？', '→')
    text = text.replace('鈫?', '→')
    text = text.replace('鈫', '→')

    # Box drawing tree chars
    text = text.replace('鈹溾攢', '├─')
    text = text.replace('鈹斺攢', '└─')
    text = text.replace('鈹?', '│')
    text = text.replace('鈹', '│')

    # 锟? → various (0xEFBFBD = U+FFFD replacement char pattern)
    text = text.replace('锟斤拷', '')  # 0xEFBFBD repeated = double replacement
    text = text.replace('锟?', '')

    return text


def fix_double_encoded_chinese(text):
    """Fix Chinese text double-encoded through GBK.

    Path: original UTF-8 → read as CP936 → written as UTF-8.
    Reverse: UTF-8 → CJK runs → GBK encode → UTF-8 decode.

    Only touches CJK blocks (U+4E00–U+9FFF range) — safe for mixed content.
    """
    result = []
    cjk_buf = []
    i = 0

    while i < len(text):
        cp = ord(text[i])
        if 0x4E00 <= cp <= 0x9FFF:
            cjk_buf.append(text[i])
            i += 1
        else:
            # Flush CJK buffer
            if cjk_buf:
                result.append(_try_decode_cjk(''.join(cjk_buf)))
                cjk_buf = []
            result.append(text[i])
            i += 1

    if cjk_buf:
        result.append(_try_decode_cjk(''.join(cjk_buf)))

    return ''.join(result)


def _try_decode_cjk(garbled):
    """Try to reverse GBK-double-encoded Chinese.

    '鎻愰棶' (GKB-mangled) → GBK encode → 'e6 8f 90 e9 97 ae' → UTF-8 decode → '提问'
    """
    try:
        gbk_bytes = garbled.encode('gbk')
        cleaned = gbk_bytes.decode('utf-8')
        # Validate: result should be CJK
        for c in cleaned:
            if not (0x4E00 <= ord(c) <= 0x9FFF or 0x3000 <= ord(c) <= 0x303F):
                return garbled  # Not a clean recovery — keep original
        return cleaned
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Fallback: try GB18030 (superset of GBK)
        try:
            gb18030 = garbled.encode('gb18030')
            cleaned = gb18030.decode('utf-8')
            for c in cleaned:
                if not (0x4E00 <= ord(c) <= 0x9FFF or 0x3000 <= ord(c) <= 0x303F):
                    return garbled
            return cleaned
        except Exception:
            return garbled


def fix_file(filepath, dry_run=False):
    """Fix mojibake in a single file. Returns (changed, message)."""
    filepath = Path(filepath)
    if not filepath.exists():
        return False, f"{filepath}: does not exist"

    # Try UTF-8 first
    try:
        original = filepath.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        try:
            original = filepath.read_text(encoding='gbk')
        except Exception as e:
            return False, f"{filepath}: cannot read — {e}"

    # Apply fixes in order
    fixed = fix_garbled_special(original)
    fixed = fix_double_encoded_chinese(fixed)
    # Re-apply special fix (Chinese fix might reveal more patterns)
    fixed = fix_garbled_special(fixed)

    if fixed == original:
        return False, f"{filepath}: clean — no mojibake found"

    changes = []
    o_lines = original.splitlines(keepends=True)
    f_lines = fixed.splitlines(keepends=True)
    for idx, (ol, fl) in enumerate(zip(o_lines, f_lines)):
        if ol != fl:
            changes.append(f"  L{idx+1}")

    if dry_run:
        return True, f"{filepath}: WOULD FIX ({len(changes)} lines)\n" + "\n".join(changes[:20])

    # Backup then write
    bak = filepath.with_suffix(filepath.suffix + '.mojibak')
    shutil.copy2(filepath, bak)
    filepath.write_text(fixed, encoding='utf-8')
    return True, f"{filepath}: FIXED {len(changes)} lines. Backup → {bak.name}"


def find_corrupt_files():
    """Find all active files (non-backup) containing mojibake patterns."""
    patterns = ['鈥', '鈫', '鈹', '锟']
    files = set()

    for root_dir in [r'E:\AgentHub\AgentBoosting\宪法',
                     r'E:\AgentHub\AgentBoosting\GodCreating']:
        for dirpath, dirnames, filenames in os.walk(root_dir):
            # Skip backup dirs
            if 'backups' in dirpath.lower() or '__pycache__' in dirpath:
                continue
            for fn in filenames:
                if fn.endswith(('.md', '.py', '.json', '.txt', '.lock', '.log')):
                    fpath = os.path.join(dirpath, fn)
                    try:
                        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read(8192)
                        if any(p in content for p in patterns):
                            files.add(fpath)
                    except Exception:
                        pass
    return sorted(files)


def main():
    dry_run = '--dry-run' in sys.argv
    fix_all = '--all' in sys.argv

    if fix_all:
        files = find_corrupt_files()
    else:
        files = [a for a in sys.argv[1:]
                 if a not in ('--dry-run',) and not a.startswith('--')]

    if not files:
        print("Usage: python fix_mojibake.py [--dry-run] [--all] [files...]")
        print("  --dry-run   Preview only, no changes")
        print("  --all       Fix all active files with mojibake in AgentBoosting")
        sys.exit(1)

    action = "DRY RUN — " if dry_run else ""
    print(f"{action}Processing {len(files)} file(s)...\n")

    fixed = 0
    for f in files:
        changed, msg = fix_file(f, dry_run=dry_run)
        print(msg)
        if changed:
            fixed += 1

    print(f"\n{action}{fixed}/{len(files)} file(s) fixed.")


if __name__ == '__main__':
    main()
