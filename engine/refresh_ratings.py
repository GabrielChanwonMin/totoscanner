#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""팀 레이팅 재학습 — 실제 경기 결과가 쌓인 만큼 모델을 다시 맞춘다.

경기 결과 → 팀 공격/수비력 → 다음 경기 예측. 이게 이 앱의 유일한 자동 학습 루프다.
(EV·앙상블 가중치는 표본이 턱없이 부족해서 학습하지 않는다 — 방법론 탭 참조)

    python3 refresh_ratings.py          # CSV 새로 받고 재학습
    python3 refresh_ratings.py --keep   # 이미 받은 CSV로 재학습만
"""
import datetime as dt, os, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
LEAGUES = ["E0", "SP1", "I1", "D1", "F1"]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140.0 Safari/537.36"


def seasons(n=7):
    """최근 n시즌 코드. 8월 이후면 새 시즌이 시작된 것으로 본다."""
    t = dt.date.today()
    start = t.year if t.month >= 8 else t.year - 1
    out = []
    for i in range(n):
        a, b = start - n + 1 + i, start - n + 2 + i
        out.append(f"{str(a)[2:]}{str(b)[2:]}")
    return out


def download():
    os.makedirs(DATA, exist_ok=True)
    got = fail = 0
    for s in seasons():
        for lg in LEAGUES:
            url = f"https://www.football-data.co.uk/mmz4281/{s}/{lg}.csv"
            path = os.path.join(DATA, f"{s}_{lg}.csv")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=40) as r:
                    body = r.read()
                if len(body) < 500:
                    fail += 1; continue
                open(path, "wb").write(body); got += 1
            except Exception:
                fail += 1
    print(f"  CSV {got}개 내려받음" + (f" (실패 {fail}개 — 아직 없는 시즌일 수 있다)" if fail else ""))
    return got


def main():
    print("팀 레이팅 재학습")
    print("─" * 40)
    if "--keep" not in sys.argv:
        print("[1/2] 최신 경기 결과 내려받기")
        if not download():
            print("  내려받기 실패. 인터넷을 확인하거나 --keep 으로 기존 데이터를 써라.")
            return 1
    print("[2/2] Dixon-Coles 재학습")
    # export.py 의 ASOF 를 오늘로 맞춘다
    exp = os.path.join(HERE, "export.py")
    src = open(exp, encoding="utf-8").read()
    import re
    t = dt.date.today()
    src2 = re.sub(r"ASOF = dt\.date\(\d+, \d+, \d+\)",
                  f"ASOF = dt.date({t.year}, {t.month}, {t.day})", src)
    if src2 != src:
        open(exp, "w", encoding="utf-8").write(src2)
        print(f"  기준일을 {t} 로 갱신")
    r = subprocess.run([sys.executable, "export.py"], cwd=HERE)
    if r.returncode:
        return r.returncode
    print("\n" + "─" * 40)
    print("완료. 새 레이팅을 앱에 반영하려면 Claude Code 에 이렇게 말해라:")
    print('  "engine/ratings.json 새로 뽑았어. 앱에 반영하고 재배포해줘"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
