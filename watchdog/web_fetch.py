#!/usr/bin/env python3
import sys
import os
import hashlib
import argparse
import re
from html.parser import HTMLParser

try:
    import requests
except ImportError:
    print("requests not installed", file=sys.stderr)
    sys.exit(1)

MAX_CHARS = 8000

class TextExtractor(HTMLParser):
    SKIP_TAGS = {'script', 'style', 'head', 'noscript'}

    def __init__(self):
        super().__init__()
        self.texts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self.texts.append(text)

    def get_text(self):
        return '\n'.join(self.texts)


def html_to_text(html):
    parser = TextExtractor()
    parser.feed(html)
    return parser.get_text()


def cache_path(url):
    md5 = hashlib.md5(url.encode()).hexdigest()
    return os.path.join('docs', f'WEB_{md5}.md')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('--save', default=None)
    args = parser.parse_args()

    cached = cache_path(args.url)
    if os.path.exists(cached):
        with open(cached, encoding='utf-8') as f:
            print(f.read())
        return

    headers = {'User-Agent': 'Mozilla/5.0 (compatible; web_fetch/1.0)'}
    resp = requests.get(args.url, headers=headers, timeout=5)
    resp.raise_for_status()

    content_type = resp.headers.get('Content-Type', '')
    if 'html' in content_type:
        text = html_to_text(resp.text)
    else:
        text = resp.text

    # Collapse blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + '\n... [truncated]'

    if args.save:
        os.makedirs(os.path.dirname(args.save) if os.path.dirname(args.save) else '.', exist_ok=True)
        with open(args.save, 'w', encoding='utf-8') as f:
            f.write(text)
    else:
        print(text)


if __name__ == '__main__':
    main()
