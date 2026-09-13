#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""팀별 플레이 스타일 · 최근 폼 (기획서 §6.3.3).

게임 레이팅 같은 걸 쓰지 않고 **실제 경기 통계**로 스타일을 계산한다.
예측에는 쓰지 않는다 — 시장 배당이 더 정확하다는 게 백테스트 결론이므로,
이건 "이 경기가 어떤 경기인지" 읽기 위한 정보다.

    python3 team_style.py     →  styles.json
"""
import csv, glob, json, os, statistics, datetime as dt
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
OUT  = os.path.join(HERE, "styles.json")
LEAGUES = {"E0": "EPL", "SP1": "라리가", "I1": "세리에A", "D1": "분데스리가", "F1": "리그1"}
RECENT = 40          # 팀당 최근 몇 경기로 스타일을 낼지
FORM   = 6           # 폼은 최근 몇 경기


def num(row, k):
    v = (row.get(k) or "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def load():
    ms = []
    for path in sorted(glob.glob(os.path.join(DATA, "*.csv"))):
        base = os.path.basename(path)[:-4]
        season, div = base.split("_")
        if div not in LEAGUES:
            continue
        for r in csv.DictReader(open(path, encoding="utf-8-sig")):
            if not r.get("HomeTeam"):
                continue
            try:
                hg, ag = int(r["FTHG"]), int(r["FTAG"])
            except (ValueError, KeyError, TypeError):
                continue
            d = (r.get("Date") or "").strip()
            fmt = "%d/%m/%Y" if len(d) == 10 else "%d/%m/%y"
            try:
                date = dt.datetime.strptime(d, fmt).date()
            except ValueError:
                continue
            ms.append(dict(div=div, season=season, date=date,
                           home=r["HomeTeam"].strip(), away=r["AwayTeam"].strip(),
                           hg=hg, ag=ag,
                           hth=num(r, "HTHG"), hta=num(r, "HTAG"),
                           hs=num(r, "HS"), as_=num(r, "AS"),
                           hst=num(r, "HST"), ast=num(r, "AST"),
                           hc=num(r, "HC"), ac=num(r, "AC"),
                           hf=num(r, "HF"), af=num(r, "AF"),
                           hy=num(r, "HY"), ay=num(r, "AY"),
                           hr=num(r, "HR"), ar=num(r, "AR"),
                           hxg=num(r, "HxG"), axg=num(r, "AxG")))
    ms.sort(key=lambda m: m["date"])
    return ms


def team_rows(ms):
    """경기를 팀 시점으로 펼친다."""
    per = defaultdict(list)
    for m in ms:
        per[(m["div"], m["home"])].append(dict(
            date=m["date"], season=m["season"], opp=m["away"], home=True,
            gf=m["hg"], ga=m["ag"], htf=m["hth"], hta=m["hta"],
            shots=m["hs"], shotsA=m["as_"], sot=m["hst"], sotA=m["ast"],
            corners=m["hc"], cornersA=m["ac"], fouls=m["hf"], foulsA=m["af"],
            cards=(m["hy"] or 0) + 2 * (m["hr"] or 0),
            xg=m["hxg"], xgA=m["axg"]))
        per[(m["div"], m["away"])].append(dict(
            date=m["date"], season=m["season"], opp=m["home"], home=False,
            gf=m["ag"], ga=m["hg"], htf=m["hta"], hta=m["hth"],
            shots=m["as_"], shotsA=m["hs"], sot=m["ast"], sotA=m["hst"],
            corners=m["ac"], cornersA=m["hc"], fouls=m["af"], foulsA=m["hf"],
            cards=(m["ay"] or 0) + 2 * (m["ar"] or 0),
            xg=m["axg"], xgA=m["hxg"]))
    return per


def avg(vals):
    v = [x for x in vals if x is not None]
    return round(sum(v) / len(v), 2) if v else None


def profile(rows):
    r = rows[-RECENT:]
    if not r:
        return None
    p = {
        "n": len(r),
        # 표본이 얇으면 앱이 리그평균 대비 화살표를 감춘다 (승격팀은 몇 경기뿐이다)
        "thin": len(r) < 10,
        "nThisSeason": sum(1 for x in r if x["season"] == "2627"),
        "gf": avg([x["gf"] for x in r]), "ga": avg([x["ga"] for x in r]),
        "shots": avg([x["shots"] for x in r]), "shotsA": avg([x["shotsA"] for x in r]),
        "sot": avg([x["sot"] for x in r]), "sotA": avg([x["sotA"] for x in r]),
        "corners": avg([x["corners"] for x in r]), "cornersA": avg([x["cornersA"] for x in r]),
        "fouls": avg([x["fouls"] for x in r]), "cards": avg([x["cards"] for x in r]),
    }
    # 유효슈팅률 = 슈팅 중 몇 개가 골문으로 갔나
    s = [x for x in r if x["shots"] and x["sot"] is not None and x["shots"] > 0]
    p["sotPct"] = round(sum(x["sot"] for x in s) / sum(x["shots"] for x in s), 3) if s else None
    # 전반 득점 비중 — 초반에 강한 팀인지
    h = [x for x in r if x["htf"] is not None]
    tot = sum(x["gf"] for x in h)
    p["firstHalfShare"] = round(sum(x["htf"] for x in h) / tot, 2) if h and tot else None
    # xG — 이번 시즌 CSV 에만 있다. 표본이 얇으면 아예 내지 않는다.
    xs = [x for x in r if x["xg"] is not None]
    if xs:
        p["xg"] = avg([x["xg"] for x in xs]); p["xgA"] = avg([x["xgA"] for x in xs])
        p["xgN"] = len(xs)
        if len(xs) >= 5:   # 경기당 결정력 (기대보다 얼마나 더 넣나)
            gf = sum(x["gf"] for x in xs); xg = sum(x["xg"] for x in xs)
            p["finishing"] = round((gf - xg) / len(xs), 2)
    # 최근 폼
    f = rows[-FORM:]
    p["form"] = "".join("W" if x["gf"] > x["ga"] else ("D" if x["gf"] == x["ga"] else "L") for x in f)
    p["formGF"] = avg([x["gf"] for x in f]); p["formGA"] = avg([x["ga"] for x in f])
    p["last"] = [{"d": x["date"].isoformat(), "opp": x["opp"], "h": x["home"],
                  "gf": x["gf"], "ga": x["ga"]} for x in f[::-1]]
    return p


def main():
    ms = load()
    per = team_rows(ms)
    cur = {(m["div"], t) for m in ms if m["season"] == "2627" for t in (m["home"], m["away"])}

    teams, by_div = {}, defaultdict(list)
    for key in cur:
        p = profile(per.get(key, []))
        if p:
            teams["|".join(key)] = p
            by_div[key[0]].append(p)

    league = {}
    for div, ps in by_div.items():
        la = {}
        for k in ("gf", "ga", "shots", "shotsA", "sot", "sotA", "corners", "cornersA",
                  "fouls", "cards", "sotPct", "xg", "xgA", "firstHalfShare"):
            v = [p[k] for p in ps if p.get(k) is not None]
            if v:
                la[k] = round(statistics.mean(v), 3 if k in ("sotPct", "firstHalfShare") else 2)
        league[div] = la

    out = {"asof": dt.date.today().isoformat(), "recent": RECENT,
           "leagueAvg": league, "teams": teams}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"styles.json — 팀 {len(teams)}개 / {os.path.getsize(OUT)/1024:.0f} KB")
    for div in LEAGUES:
        if div in league:
            la = league[div]
            print(f"  {LEAGUES[div]:8s} 리그평균 슈팅 {la.get('shots')} · 유효율 {la.get('sotPct')} · "
                  f"코너 {la.get('corners')} · 파울 {la.get('fouls')}"
                  + (f" · xG {la['xg']}" if la.get("xg") else ""))


if __name__ == "__main__":
    main()
