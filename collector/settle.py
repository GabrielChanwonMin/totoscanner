#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""자동 정산 — 지난 회차 예측을 실제 경기 결과와 맞춰 채점한다.

네가 손으로 적을 게 없다. 경기가 끝나면 football-data 가 결과를 올리고,
다음에 수집기를 돌릴 때 이게 알아서 채점해 성적표를 갱신한다.

    python3 settle.py            # 결과 새로 받고 채점
    python3 settle.py --keep     # 이미 받은 CSV 로 채점만
"""
import csv, glob, io, json, math, os, sys, datetime as dt
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PRED = os.path.join(HERE, "predictions")
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "engine", "scoreboard.json")
LEAGUES = ["E0", "SP1", "I1", "D1", "F1"]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140.0 Safari/537.36"

BUCKETS = [(1.0,1.3),(1.3,1.6),(1.6,2.0),(2.0,2.6),(2.6,3.5),(3.5,5.0),(5.0,8.0),(8.0,999)]


def season_code(d=None):
    d = d or dt.date.today()
    y = d.year if d.month >= 8 else d.year - 1
    return f"{str(y)[2:]}{str(y+1)[2:]}"


def download():
    import urllib.request
    os.makedirs(DATA, exist_ok=True)
    s = season_code(); got = 0
    for lg in LEAGUES:
        try:
            req = urllib.request.Request(
                f"https://www.football-data.co.uk/mmz4281/{s}/{lg}.csv", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                b = r.read()
            if len(b) > 300:
                open(os.path.join(DATA, f"{s}_{lg}.csv"), "wb").write(b); got += 1
        except Exception:
            pass
    return got


def results():
    """(리그, 홈, 원정) → [(날짜, 홈골, 원정골)]"""
    out = defaultdict(list)
    for path in glob.glob(os.path.join(DATA, "*.csv")):
        div = os.path.basename(path)[:-4].split("_")[1]
        for r in csv.DictReader(open(path, encoding="utf-8-sig")):
            if not r.get("HomeTeam"): continue
            try: hg, ag = int(r["FTHG"]), int(r["FTAG"])
            except (ValueError, KeyError, TypeError): continue
            d = (r.get("Date") or "").strip()
            try:
                date = dt.datetime.strptime(d, "%d/%m/%Y" if len(d) == 10 else "%d/%m/%y").date()
            except ValueError:
                continue
            out[(div, r["HomeTeam"].strip(), r["AwayTeam"].strip())].append((date, hg, ag))
    return out


def outcome(market, line, hg, ag, zero_even=True):
    """실제 결과가 어느 선택지였나. None 이면 적중특례(무효)."""
    if market == "1X2":
        return 0 if hg > ag else (1 if hg == ag else 2)
    if market == "HANDICAP":
        d = hg + float(line or 0) - ag
        return 0 if d > 1e-9 else (1 if abs(d) < 1e-9 else 2)
    if market == "OU":
        t = hg + ag; L = float(line or 2.5)
        if abs(t - L) < 1e-9: return None
        return 0 if t < L else 1
    t = hg + ag
    if t == 0: return 1 if zero_even else 0
    return 0 if t % 2 else 1


def metrics(rows, pkey="p"):
    """rows: [(p, hit)] 형태로 정리된 것에서 지표 계산"""
    n = len(rows)
    if not n: return None
    ll = sum(-math.log(max(p if h else 1-p, 1e-9)) for p, h in rows)/n
    br = sum((p - (1 if h else 0))**2 for p, h in rows)/n
    bins = [[0.0, 0, 0] for _ in range(10)]
    for p, h in rows:
        b = min(9, int(p*10)); bins[b][0] += p; bins[b][1] += 1 if h else 0; bins[b][2] += 1
    ece = sum(b[2]/n*abs(b[0]/b[2] - b[1]/b[2]) for b in bins if b[2])
    return {"n": n, "predSum": round(sum(p for p, _ in rows), 1),
            "hits": sum(1 for _, h in rows if h),
            "logloss": round(ll, 5), "brier": round(br, 5), "ece": round(ece, 4),
            "calib": [{"p": round(b[0]/b[2], 4), "a": round(b[1]/b[2], 4), "n": b[2]}
                      for b in bins if b[2] >= 8]}


def main():
    if "--keep" not in sys.argv:
        print(f"  결과 내려받기… ({download()}개 리그)")
    res = results()
    files = sorted(glob.glob(os.path.join(PRED, "round_*.json")))
    if not files:
        print("  채점할 예측이 없다. 회차를 한 번 수집하면 쌓이기 시작한다."); return 0

    settled, pending = [], 0
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        for r in d["predictions"]:
            games = res.get((r["league"], r["home"], r["away"]))
            if not games: pending += 1; continue
            kick = (r.get("kick") or "")[:10]
            try: kd = dt.date.fromisoformat(kick)
            except ValueError: kd = None
            g = None
            for date, hg, ag in games:
                if kd is None or abs((date - kd).days) <= 2: g = (date, hg, ag); break
            if not g: pending += 1; continue
            y = outcome(r["market"], r.get("line"), g[1], g[2])
            if y is None: continue                     # 적중특례
            rec = dict(r); rec["round"] = d["round"]
            rec["hit"] = (r["sel"] == y); rec["score"] = f"{g[1]}-{g[2]}"; rec["date"] = g[0].isoformat()
            settled.append(rec)

    if not settled:
        print(f"  아직 결과가 나온 경기가 없다 (대기 {pending}픽)."); return 0

    sb = {"builtAt": dt.datetime.now().isoformat(timespec="seconds"),
          "settled": len(settled), "pending": pending,
          "rounds": sorted({r["round"] for r in settled}, key=str)}

    sb["overall"] = metrics([(r["p"], r["hit"]) for r in settled])
    # 앱(시장 기반) vs 자체 모델 — 같은 경기에서 누가 더 맞았나.
    # 단, 레이팅 학습 기준일보다 이전 경기는 모델이 이미 본 경기라 비교가 오염된다 → 제외.
    try:
        asof = dt.date.fromisoformat(json.load(
            open(os.path.join(ROOT, "engine", "ratings.json"), encoding="utf-8"))["asof"])
    except Exception:
        asof = dt.date(1900, 1, 1)
    both = [r for r in settled if r.get("pModel") is not None and r["source"] != "model"
            and dt.date.fromisoformat(r["date"]) > asof]
    leaked = sum(1 for r in settled if r.get("pModel") is not None
                 and dt.date.fromisoformat(r["date"]) <= asof)
    if both:
        sb["appVsModel"] = {"app": metrics([(r["p"], r["hit"]) for r in both]),
                            "model": metrics([(r["pModel"], r["hit"]) for r in both]),
                            "asof": asof.isoformat()}
    if leaked:
        sb["leakedExcluded"] = leaked
    # 등급별 실제 수익
    sb["byGrade"] = {}
    for gname in ("REC", "WATCH", "INFO", "NOREF"):
        g = [r for r in settled if r["grade"] == gname]
        if len(g) < 3: continue
        ret = [(r["odds"]-1) if r["hit"] else -1 for r in g]
        sb["byGrade"][gname] = {"n": len(g), "hits": sum(1 for r in g if r["hit"]),
                                "roi": round(sum(ret)/len(ret), 4),
                                "avgOdds": round(sum(r["odds"] for r in g)/len(g), 2),
                                "avgEv": round(sum(r["ev"] for r in g)/len(g), 4)}
    # 베트맨 배당 구간별 (친구 요청: 몇 번 적중 몇 번 터졌나)
    sb["byBucket"] = []
    for lo, hi in BUCKETS:
        g = [r for r in settled if lo <= r["odds"] < hi]
        if len(g) < 3: continue
        ret = [(r["odds"]-1) if r["hit"] else -1 for r in g]
        sb["byBucket"].append({"b": f"{lo:.2f}-{hi:.2f}" if hi < 999 else f"{lo:.2f}+",
                               "n": len(g), "w": sum(1 for r in g if r["hit"]),
                               "l": sum(1 for r in g if not r["hit"]),
                               "roi": round(sum(ret)/len(ret), 4),
                               "expP": round(sum(r["p"] for r in g)/len(g), 4)})
    sb["byMarket"] = {}
    for mk in ("1X2", "HANDICAP", "OU", "SUM"):
        g = [r for r in settled if r["market"] == mk]
        m = metrics([(r["p"], r["hit"]) for r in g])
        if m: sb["byMarket"][mk] = m

    json.dump(sb, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    o = sb["overall"]
    print(f"  ✓ {len(settled)}픽 자동 채점 (대기 {pending})")
    print(f"    앱이 예상한 적중 {o['predSum']} / 실제 {o['hits']}  ·  ECE {o['ece']}")
    if sb.get("leakedExcluded"):
        print(f"    ({sb['leakedExcluded']}픽은 레이팅 학습 기간과 겹쳐 모델 비교에서 뺐다)")
    if "appVsModel" in sb:
        a, m = sb["appVsModel"]["app"], sb["appVsModel"]["model"]
        print(f"    log loss — 앱 {a['logloss']} vs 자체모델 {m['logloss']}  "
              f"({'앱이 낫다' if a['logloss'] < m['logloss'] else '모델이 낫다'}, n={a['n']})")
    for gname, g in sb["byGrade"].items():
        print(f"    {gname:6s} {g['n']:4d}픽 적중 {g['hits']:4d}  ROI {g['roi']*100:+6.1f}%")
    print(f"  → engine/scoreboard.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
