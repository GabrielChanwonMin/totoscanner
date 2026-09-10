import json, math, dc
from backtest import metrics

R = json.load(open("cache_preds.json"))
R = [r for r in R if r["close"] and r["open"]]
print("n =", len(R))

def dv(o, how):
    return {"prop": dc.devig_prop, "power": dc.devig_power, "shin": dc.devig_shin}[how](o)

print("\n[1] 마진 제거 방식 비교 (클로징 배당 기준)")
for how in ("prop","power","shin"):
    m = metrics([(dv(r["close"],how), r["y"]) for r in R])
    print("  %-6s RPS %.5f  LL %.5f  ECE %.4f" % (how, m["rps"], m["logloss"], m["ece"]))

print("\n[2] 모델 vs 오프닝 vs 클로징")
mm = metrics([(r["pm"], r["y"]) for r in R])
mo = metrics([(dv(r["open"],"power"), r["y"]) for r in R])
mc = metrics([(dv(r["close"],"power"), r["y"]) for r in R])
for name, m in (("모델(DC)", mm), ("오프닝 시장", mo), ("클로징 시장", mc)):
    print("  %-10s RPS %.5f  LL %.5f  Brier %.4f  ECE %.4f" % (name, m["rps"], m["logloss"], m["brier"], m["ece"]))

def blendscan(key, label):
    best = None; tbl = []
    for i in range(0, 101, 2):
        w = i/100
        pr = [(dc.log_pool([r["pm"], dv(r[key],"power")], [1-w, w]), r["y"]) for r in R]
        m = metrics(pr); m["w"] = w; tbl.append(m)
        if best is None or m["rps"] < best["rps"]: best = m
    bl = min(tbl, key=lambda m: m["logloss"])
    print("  %s → RPS 최적 w_mkt=%.2f (RPS %.5f)  |  LL 최적 w_mkt=%.2f (LL %.5f)"
          % (label, best["w"], best["rps"], bl["w"], bl["logloss"]))
    return best

print("\n[3] 앙상블 최적 가중치 (log-linear pooling)")
b_open = blendscan("open", "vs 오프닝")
b_close = blendscan("close", "vs 클로징")

print("\n[4] 시즌 초반(각 팀 8경기 이내) 부분집합")
# 시즌 내 라운드 근사: 리그·시즌별 날짜 순위
from collections import defaultdict
order = defaultdict(list)
for r in R: order[(r["div"], r["season"])].append(r)
early = []
for k, v in order.items():
    v.sort(key=lambda r: r["date"])
    n_early = int(len(v) * 8 / 38)
    early += v[:n_early]
print("  n =", len(early))
me = metrics([(r["pm"], r["y"]) for r in early])
mce = metrics([(dv(r["close"],"power"), r["y"]) for r in early])
print("  모델 RPS %.5f | 클로징 RPS %.5f" % (me["rps"], mce["rps"]))
best = None
for i in range(0, 101, 2):
    w = i/100
    m = metrics([(dc.log_pool([r["pm"], dv(r["close"],"power")], [1-w, w]), r["y"]) for r in early])
    if best is None or m["rps"] < best["rps"]: best = m; best["w"] = w
print("  최적 w_mkt=%.2f RPS %.5f" % (best["w"], best["rps"]))

print("\n[5] 캘리브레이션 (모델, 10구간)")
bins = [[0,0,0] for _ in range(10)]
for r in R:
    for i in range(3):
        b = min(9, int(r["pm"][i]*10)); bins[b][0]+=r["pm"][i]; bins[b][1]+= (1.0 if r["y"]==i else 0); bins[b][2]+=1
for i,b in enumerate(bins):
    if b[2]>30: print("   %2d~%2d%%  예측 %.3f  실제 %.3f  (n=%d)" % (i*10,(i+1)*10, b[0]/b[2], b[1]/b[2], b[2]))
