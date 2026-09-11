#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""이번 회차 예측을 파일로 남긴다. 나중에 결과가 나오면 settle.py 가 자동 채점한다.
네가 아무것도 기록할 필요가 없다."""
import json, os, sys, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
import predict as P

SRC = os.path.join(HERE, "latest_import.json")
DIR = os.path.join(HERE, "predictions")


def main():
    if not os.path.exists(SRC):
        print("  수집 데이터가 없다."); return 1
    app = json.load(open(SRC, encoding="utf-8"))
    pub = [m for m in app.get("matches", []) if m.get("betman") and all(float(x) > 1 for x in m["betman"])]
    if not pub:
        print("  배당 공시 전이라 예측할 게 없다."); return 0
    rows = P.predict_round({"matches": pub})
    if not rows:
        print("  예측이 나오지 않았다 (팀 레이팅 확인)."); return 1

    os.makedirs(DIR, exist_ok=True)
    rnd = app.get("round") or app.get("gmTs") or "unknown"
    path = os.path.join(DIR, f"round_{rnd}.json")
    # 같은 회차를 다시 수집하면 덮어쓴다 (마감 직전 값이 최종)
    json.dump({"round": rnd, "gmTs": app.get("gmTs"), "capturedAt": app.get("capturedAt"),
               "saleEnd": app.get("saleEnd"), "predictions": rows},
              open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    from collections import Counter
    g = Counter(r["grade"] for r in rows)
    graded = [r for r in rows if r["grade"] in ("REC", "WATCH")]
    print(f"  예측 {len(rows)}픽 저장 → predictions/round_{rnd}.json")
    print(f"    🟢추천 {g.get('REC',0)} · 🟡관심 {g.get('WATCH',0)} · ⚪참고 {g.get('INFO',0)} · 등급없음 {g.get('NOREF',0)}")
    if graded:
        best = max(graded, key=lambda r: r["evLo"])
        print(f"    최고: #{best['no']} {best['home']} vs {best['away']} {best['market']} "
              f"EV {best['ev']*100:+.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
