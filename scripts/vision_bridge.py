#!/usr/bin/env python3
"""Vision Bridge — Routes image analysis to Claude API since deepseek is text-only.
Usage: python vision_bridge.py <image_path> [output_dir]
Requires: ANTHROPIC_API_KEY env var
"""
import sys, os, base64, json
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import HTTPError

MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"
}

def describe_image(image_path, output_dir="docs"):
    path = os.path.abspath(image_path)
    if not os.path.exists(path):
        sys.exit(f"[VISION] Image not found: {path}")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("[VISION] ANTHROPIC_API_KEY not set. Export it first.")

    ext = os.path.splitext(path)[1].lower()
    media_type = MEDIA_TYPES.get(ext, "image/png")

    with open(path, "rb") as f:
        img_b64 = base64.standard_b64encode(f.read()).decode()

    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_b64}},
            {"type": "text", "text": (
                "Describe this image in full detail for a developer who cannot see it. "
                "Include: layout, all text content, UI elements, data values, relationships, "
                "technical content, file paths, error messages. Be complete and literal."
            )}
        ]}]
    }).encode()

    req = Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
    )
    try:
        with urlopen(req) as resp:
            result = json.loads(resp.read())
        description = result["content"][0]["text"]
    except HTTPError as e:
        sys.exit(f"[VISION] API error {e.code}: {e.read().decode()}")

    stem = os.path.splitext(os.path.basename(path))[0]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, f"IMG_DESC_{stem}_{ts}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# Image Description: {os.path.basename(path)}\n")
        f.write(f"Source: {path}\nGenerated: {datetime.now().isoformat()}\n\n")
        f.write(description + "\n")

    print(f"[VISION] Saved: {out}")
    print(description)
    return out

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python vision_bridge.py <image_path> [output_dir]")
        sys.exit(1)
    describe_image(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "docs")
