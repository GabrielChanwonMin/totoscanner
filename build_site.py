#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""totoscanner.html → docs/ (GitHub Pages 용 정적 사이트)로 빌드한다.

  python3 build_site.py
"""
import os, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "totoscanner.html")
DOCS = os.path.join(HERE, "docs")

HEAD = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive">
<meta name="referrer" content="no-referrer">
<meta name="color-scheme" content="light dark">
<style>body{margin:0;font-size:14px}img{max-width:100%}[hidden]{display:none!important}</style>
"""

def build():
    src = open(SRC, encoding="utf-8").read()
    i = src.index("<style>")
    head_bits, body = src[:i], src[i:]

    os.makedirs(os.path.join(DOCS, "data"), exist_ok=True)
    out = HEAD + head_bits + '<script src="config.js"></script>\n</head>\n<body>\n' + body + "\n</body>\n</html>\n"
    open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8").write(out)

    # 검색엔진 차단 (URL 을 모르는 사람이 흘러들어오지 않게)
    open(os.path.join(DOCS, "robots.txt"), "w").write("User-agent: *\nDisallow: /\n")
    open(os.path.join(DOCS, ".nojekyll"), "w").write("")

    cfg = os.path.join(DOCS, "config.js")
    if not os.path.exists(cfg):
        open(cfg, "w", encoding="utf-8").write(
            "// Supabase 연결 정보. 비워두면 기록이 이 브라우저에만 저장된다.\n"
            "// Supabase 대시보드 › Project Settings › API 에서 복사해 넣어라.\n"
            "window.TS_CONFIG = {\n"
            '  supabaseUrl: "",   // 예: https://abcdefgh.supabase.co\n'
            '  supabaseKey: ""    // anon public 키\n'
            "};\n")

    # 데이터가 아직 없으면 빈 껍데기를 둔다 (404 로그 방지)
    d = os.path.join(DOCS, "data", "latest.json")
    if not os.path.exists(d):
        open(d, "w").write('{"source":"betman","matches":[],"oddsChanges":[]}')

    print("docs/ 빌드 완료")
    for root, _, files in os.walk(DOCS):
        for f in sorted(files):
            p = os.path.join(root, f)
            print(f"  {os.path.relpath(p, HERE):32s} {os.path.getsize(p):>8,} bytes")

if __name__ == "__main__":
    build()
