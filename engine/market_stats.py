#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""시장 적중 통계 — 배당 구간별 / 팀별 / 맞대결별.

"1.50~1.59 배당은 올해 몇 번 적중이고 몇 번 터졌나" 에 답한다.
모두 실경기 결과로 계산하며, 시즌이 지날수록 다시 돌리면 갱신된다.

    python3 market_stats.py          # stats.json 생성
"""
import csv, glob, json, math, os, datetime as dt
from collections import defaultdict
import dc

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
OUT = os.path.join(HERE, "stats.json")

# 배당 구간 (친구 요청대로 0.1 단위 세분, 위로 갈수록 넓게)
BUCKETS = [(1.0,1.1),(1.1,1.2),(1.2,1.3),(1.3,1.4),(1.4,1.5),(1.5,1.6),(1.6,1.7),
           (1.7,1.8),(1.8,1.9),(1.9,2.0),(2.0,2.2),(2.2,2.5),(2.5,3.0),(3.0,3.5),
           (3.5,4.5),(4.5,6.0),(6.0,8.0),(8.0,12.0),(12.0,999)]

def f(row, k):
    v = (row.get(k) or "").strip()
    try:
        x = float(v); return x if x > 1.0 else None
    except ValueError:
        return None

def load():
    ms = []
    for path in sorted(glob.glob(os.path.join(DATA, "*.csv"))):
        base = os.path.basename(path)[:-4]
        season, div = base.split("_")
        for r in csv.DictReader(open(path, encoding="utf-8-sig")):
            if not r.get("HomeTeam"): continue
            try: hg, ag = int(r["FTHG"]), int(r["FTAG"])
            except (ValueError, KeyError, TypeError): continue
            o = [f(r,"PSCH"), f(r,"PSCD"), f(r,"PSCA")]
            if None in o: o = [f(r,"AvgCH"), f(r,"AvgCD"), f(r,"AvgCA")]
            if None in o: o = [f(r,"AvgH"), f(r,"AvgD"), f(r,"AvgA")]
            if None in o: continue
            d = (r.get("Date") or "").strip()
            try:
                date = dt.datetime.strptime(d, "%d/%m/%Y" if len(d)==10 else "%d/%m/%y").date()
            except ValueError:
                continue
            y = 0 if hg>ag else (1 if hg==ag else 2)
            ms.append(dict(season=season, div=div, date=date, home=r["HomeTeam"].strip(),
                           away=r["AwayTeam"].strip(), hg=hg, ag=ag, y=y, odds=o))
    ms.sort(key=lambda m: m["date"])
    return ms

def bucket_of(o):
    for lo, hi in BUCKETS:
        if lo <= o < hi: return "%.2f-%.2f" % (lo, hi) if hi < 999 else "%.2f+" % lo
    return None

def odds_buckets(ms, season=None):
    """각 배당 구간에서 그 픽이 몇 번 적중/실패했는가."""
    agg = defaultdict(lambda: {"n":0,"w":0,"impSum":0.0,"ret":0.0})
    for m in ms:
        if season and m["season"] != season: continue
        for i, o in enumerate(m["odds"]):
            b = bucket_of(o)
            if not b: continue
            a = agg[b]; a["n"] += 1
            hit = (m["y"] == i)
            a["w"] += 1 if hit else 0
            a["impSum"] += 1.0/o
            a["ret"] += (o-1) if hit else -1
    out = []
    order = {("%.2f-%.2f" % (lo,hi) if hi<999 else "%.2f+" % lo): k for k,(lo,hi) in enumerate(BUCKETS)}
    for b, a in sorted(agg.items(), key=lambda kv: order.get(kv[0], 99)):
        if a["n"] < 20: continue
        out.append({"b":b, "n":a["n"], "w":a["w"], "l":a["n"]-a["w"],
                    "hit":round(a["w"]/a["n"], 4),
                    "exp":round(a["impSum"]/a["n"], 4),          # 배당이 말한 확률(마진 포함)
                    "roi":round(a["ret"]/a["n"], 4)})
    return out

def team_stats(ms):
    """팀별: 시장이 이 팀을 얼마나 잘 맞혔나."""
    t = defaultdict(lambda: {"n":0,"w":0,"d":0,"l":0,"pSum":0.0,"act":0,
                             "favN":0,"favW":0,"dogN":0,"dogW":0,"gf":0,"ga":0})
    for m in ms:
        p = dc.devig_power(m["odds"])
        for side, name in ((0, m["home"]), (1, m["away"])):
            a = t[(m["div"], name)]
            pi = p[0] if side==0 else p[2]                      # 이 팀이 이길 확률
            won = (m["y"]==0) if side==0 else (m["y"]==2)
            drew = m["y"]==1
            a["n"] += 1; a["pSum"] += pi; a["act"] += 1 if won else 0
            a["w"] += 1 if won else 0; a["d"] += 1 if drew else 0
            a["l"] += 1 if (not won and not drew) else 0
            a["gf"] += m["hg"] if side==0 else m["ag"]
            a["ga"] += m["ag"] if side==0 else m["hg"]
            fav = pi > (p[2] if side==0 else p[0])
            if fav: a["favN"] += 1; a["favW"] += 1 if won else 0
            else:   a["dogN"] += 1; a["dogW"] += 1 if won else 0
    out = {}
    for (div, name), a in t.items():
        if a["n"] < 20: continue
        out.setdefault(div, {})[name] = {
            "n":a["n"], "w":a["w"], "d":a["d"], "l":a["l"],
            "pExp":round(a["pSum"]/a["n"],4),                    # 시장이 본 평균 승률
            "pAct":round(a["act"]/a["n"],4),                     # 실제 승률
            "favN":a["favN"], "favW":a["favW"],                  # 정배였을 때
            "dogN":a["dogN"], "dogW":a["dogW"],                  # 역배였을 때
            "gf":a["gf"], "ga":a["ga"]}
    return out

def h2h(ms, active, keep=6):
    """맞대결: 최근 전적 + 그때 시장이 뭐라 했는지.
    현재 시즌 5대 리그 팀끼리의 대결만 남기고, 배열로 압축한다.
      [날짜YYMMDD, t1이홈인가, t1골, t2골, 시장이본 t1승률(‰), 무(‰)]
    """
    pair = defaultdict(list)
    for m in ms:
        t1, t2 = sorted([m["home"], m["away"]])
        if m["div"] not in active: continue
        if t1 not in active[m["div"]] or t2 not in active[m["div"]]: continue
        p = dc.devig_power(m["odds"])
        t1home = (m["home"] == t1)
        g1, g2 = (m["hg"], m["ag"]) if t1home else (m["ag"], m["hg"])
        p1 = p[0] if t1home else p[2]
        pair[(m["div"], t1, t2)].append(
            [m["date"].strftime("%y%m%d"), 1 if t1home else 0, g1, g2,
             round(p1*1000), round(p[1]*1000)])
    out = {}
    for (div, t1, t2), games in pair.items():
        games = games[-keep:]
        ok = 0
        for d_, t1h, g1, g2, p1, pd_ in games:
            p2 = 1000 - p1 - pd_
            pred = 0 if p1 >= max(pd_, p2) else (1 if pd_ >= p2 else 2)
            res = 0 if g1 > g2 else (1 if g1 == g2 else 2)
            ok += 1 if pred == res else 0
        out.setdefault(div, {})[t1 + "|" + t2] = {"g": games, "ok": ok}
    return out


def main():
    ms = load()
    print(f"경기 {len(ms):,}개 ({ms[0]['date']} ~ {ms[-1]['date']})")
    # 현재 레이팅에 있는 팀 = 이번 시즌 5대 리그 팀
    R = json.load(open(os.path.join(HERE, "ratings.json"), encoding="utf-8"))
    active = {div: set(L["teams"].keys()) for div, L in R["leagues"].items()}
    print("현재 시즌 팀:", sum(len(v) for v in active.values()), "개")
    cur = max(m["season"] for m in ms)
    prev = sorted({m["season"] for m in ms})[-2]
    stats = {
        "builtAt": dt.date.today().isoformat(),
        "n": len(ms),
        "span": [ms[0]["date"].isoformat(), ms[-1]["date"].isoformat()],
        "buckets": {"all": odds_buckets(ms),
                    "cur": odds_buckets(ms, cur), "curLabel": cur,
                    "prev": odds_buckets(ms, prev), "prevLabel": prev},
        "teams": team_stats(ms),
        "h2h": h2h(ms, active),
    }
    json.dump(stats, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",",":"))
    size = os.path.getsize(OUT)/1024
    print(f"stats.json {size:.0f} KB")
    print("\n배당 구간별 적중/실패 (전체 기간)")
    print("  %-12s %7s %7s %7s %8s %8s %8s" % ("구간","픽수","적중","실패","적중률","배당이본확률","ROI"))
    for b in stats["buckets"]["all"]:
        print("  %-12s %7d %7d %7d %7.1f%% %9.1f%% %8.1f%%" %
              (b["b"], b["n"], b["w"], b["l"], b["hit"]*100, b["exp"]*100, b["roi"]*100))
    return stats

if __name__ == "__main__":
    main()
