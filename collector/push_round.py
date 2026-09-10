#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""수집한 회차를 Supabase 로 올린다 (승인된 회원만 읽을 수 있는 곳).

service_role 키를 쓴다 — RLS 를 통과해야 쓰기가 되기 때문이다.
그 키는 secrets.json 에만 두고 절대 저장소에 올리지 않는다 (.gitignore 처리됨).

    python3 push_round.py
"""
import json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SEC = os.path.join(HERE, "secrets.json")
SRC = os.path.join(HERE, "latest_import.json")


def load_secrets():
    if not os.path.exists(SEC):
        return None
    try:
        d = json.load(open(SEC, encoding="utf-8"))
    except Exception as e:
        print(f"  secrets.json 을 읽지 못했다: {e}")
        return None
    url, key = (d.get("supabaseUrl") or "").rstrip("/"), d.get("serviceRoleKey") or ""
    if not url or not key or "여기에" in url + key or "YOUR_" in url + key:
        return None
    return url, key


def push():
    sec = load_secrets()
    if not sec:
        print("  Supabase 설정이 없다 (collector/secrets.json). 건너뛴다.")
        return False
    url, key = sec
    if not os.path.exists(SRC):
        print("  올릴 데이터가 없다.")
        return False
    app = json.load(open(SRC, encoding="utf-8"))
    if not app.get("matches"):
        print("  경기가 0건이라 올리지 않는다 (기존 데이터를 지우지 않기 위해).")
        return False

    row = {
        "id": "current",
        "gm_ts": app.get("gmTs"),
        "round_no": app.get("round"),
        "captured_at": app.get("capturedAt"),
        "sale_end": app.get("saleEnd"),
        "payload": {"matches": app["matches"], "oddsChanges": app.get("oddsChanges", [])},
        "updated_at": app.get("capturedAt"),
    }
    body = json.dumps([row]).encode()
    req = urllib.request.Request(url + "/rest/v1/rounds", data=body, method="POST")
    for k, v in {"apikey": key, "Authorization": "Bearer " + key,
                 "Content-Type": "application/json",
                 "Prefer": "resolution=merge-duplicates,return=minimal"}.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    except urllib.error.HTTPError as e:
        print(f"  올리기 실패 {e.code}: {e.read().decode('utf-8','replace')[:200]}")
        return False
    except Exception as e:
        print(f"  올리기 실패: {e}")
        return False

    pub = [m for m in app["matches"] if all(x > 1 for x in m.get("betman", []))]
    print(f"  ✓ {app.get('round')}회차 {len(app['matches'])}행 올렸다 (배당 공시 {len(pub)}행)")
    return True


if __name__ == "__main__":
    sys.exit(0 if push() else 1)
