#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""해외 컨센서스 배당 수집기 — football-data.co.uk fixtures.csv (무료).

백테스트에 쓴 것과 동일한 소스·동일한 컬럼이라, 검증된 수치가 그대로 적용된다.
  AvgH/AvgD/AvgA   여러 북메이커 평균 승/무/패      → 1X2 컨센서스
  Avg>2.5/Avg<2.5  오버/언더 2.5 평균              → 언더오버 컨센서스
팀명이 이미 영문이라 레이팅 키와 그대로 맞는다 (레이팅을 이 소스로 학습했으므로).

사용법:
    python3 collect_odds.py              # latest_import.json 에 해외 배당을 병합
    python3 collect_odds.py --show       # 받아온 경기만 출력
"""
import csv, io, json, os, sys, datetime as dt, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://www.football-data.co.uk/fixtures.csv"
BIG5 = {"E0", "SP1", "I1", "D1", "F1"}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140.0 Safari/537.36"


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8-sig", "replace")
    return list(csv.DictReader(io.StringIO(raw)))


def f(row, key):
    v = (row.get(key) or "").strip()
    try:
        x = float(v)
        return x if x > 1.0 else None
    except ValueError:
        return None


def parse(rows):
    """{(div, home, away): {"1X2":[...], "OU25":[언더,오버], "date":..}}"""
    out = {}
    for r in rows:
        if r.get("Div") not in BIG5:
            continue
        h, a = (r.get("HomeTeam") or "").strip(), (r.get("AwayTeam") or "").strip()
        if not h or not a:
            continue
        # 1X2: 시장 평균 우선, 없으면 B365
        x = [f(r, "AvgH"), f(r, "AvgD"), f(r, "AvgA")]
        if None in x:
            x = [f(r, "B365H"), f(r, "B365D"), f(r, "B365A")]
        ou = [f(r, "Avg<2.5"), f(r, "Avg>2.5")]          # [언더, 오버]
        if None in ou:
            ou = [f(r, "B365<2.5"), f(r, "B365>2.5")]
        out[(r["Div"], h, a)] = {
            "1X2": None if None in x else x,
            "OU25": None if None in ou else ou,
            "date": (r.get("Date") or "").strip(), "time": (r.get("Time") or "").strip(),
        }
    return out


def merge(app_path=None):
    app_path = app_path or os.path.join(HERE, "latest_import.json")
    if not os.path.exists(app_path):
        print("latest_import.json 이 없다. 먼저 collect_betman.py 를 실행해라."); return
    app = json.load(open(app_path, encoding="utf-8"))
    if not app.get("matches"):
        print("latest_import.json 에 경기가 없다. 베트맨 수집이 먼저 성공해야 한다."); return
    odds = parse(fetch())
    print(f"fixtures.csv 에서 5대 리그 {len(odds)}경기의 배당을 받았다.")
    if odds:
        ds = sorted({v["date"] for v in odds.values()})
        print(f"  담긴 날짜: {', '.join(ds)}")

    hit = miss = 0
    seen_missing = set()
    for m in app["matches"]:
        k = (m["league"], m["home"], m["away"])
        o = odds.get(k)
        if not o:
            if m["market"] == "1X2":
                miss += 1; seen_missing.add(f'{m["home"]} vs {m["away"]}')
            continue
        if m["market"] == "1X2" and o["1X2"]:
            m["ref"] = o["1X2"]; hit += 1
        elif m["market"] == "OU" and o["OU25"] and abs(float(m.get("line") or 0) - 2.5) < 1e-6:
            m["ref"] = o["OU25"]
    app["refSource"] = "football-data.co.uk fixtures.csv"
    app["refFetchedAt"] = dt.datetime.now().isoformat(timespec="seconds")
    json.dump(app, open(app_path, "w", encoding="utf-8"), ensure_ascii=False)

    n1 = sum(1 for m in app["matches"] if m["market"] == "1X2")
    nref = sum(1 for m in app["matches"] if m.get("ref"))
    print(f"\n  승무패 {n1}경기 중 {hit}경기에 해외 배당을 붙였다. (전체 {nref}행)")
    if miss:
        print(f"  ⚠ {miss}경기는 fixtures.csv 에 아직 없다 — 그 경기는 앱에서 직접 입력해야 등급이 나온다:")
        for s in sorted(seen_missing)[:10]:
            print("     " + s)
        print("     (football-data 는 보통 경기 1~2일 전에 채워진다. 마감 전에 다시 실행해봐라.)")
    print(f"\n  저장: {os.path.basename(app_path)}")


if __name__ == "__main__":
    if "--show" in sys.argv:
        o = parse(fetch())
        print(f"5대 리그 {len(o)}경기")
        for (d, h, a), v in sorted(o.items(), key=lambda x: x[1]["date"]):
            print(f'  {d} {v["date"]} {v["time"]}  {h} vs {a}  1X2={v["1X2"]}  OU2.5={v["OU25"]}')
    else:
        merge()
