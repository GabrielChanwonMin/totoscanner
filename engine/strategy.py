"""EV 파이프라인 검증: 컨센서스 확률로 EV>0 픽을 고르면 실제로 이익인가?
   p_true  = 클로징 컨센서스(파워법 디빅)  ← 앱의 '해외 컨센서스' 역할
   O_bet   = 오프닝 배당(마진 큼)          ← 앱의 '베트맨 배당' 역할
   추가로 모델 단독 p_true도 비교."""
import json, math, random, dc
from backtest import metrics

R = [r for r in json.load(open("cache_preds.json")) if r["close"] and r["open"]]

def platt(p, a, b):
    out = []
    for x in p:
        z = math.log(max(x,1e-9)/max(1-x,1e-9))
        out.append(1/(1+math.exp(-(a+b*z))))
    s = sum(out); return [v/s for v in out]

print("[A] Platt 보정 후 모델 재평가 (a,b 그리드)")
best=None
for a in [x/100 for x in range(-20,21,5)]:
    for b in [x/100 for x in range(80,141,5)]:
        m = metrics([(platt(r["pm"],a,b), r["y"]) for r in R])
        if best is None or m["rps"]<best[0]: best=(m["rps"],a,b,m["logloss"])
print("  최적 a=%.2f b=%.2f → RPS %.5f LL %.5f (보정 전 %.5f)"
      % (best[1],best[2],best[0],best[3], metrics([(r["pm"],r["y"]) for r in R])["rps"]))
A,B = best[1],best[2]
bw=None
for i in range(0,101,2):
    w=i/100
    m=metrics([(dc.log_pool([platt(r["pm"],A,B), dc.devig_power(r["close"])],[1-w,w]), r["y"]) for r in R])
    if bw is None or m["rps"]<bw[0]: bw=(m["rps"],w)
print("  보정모델+클로징 앙상블 최적 w_mkt=%.2f RPS %.5f" % (bw[1],bw[0]))

def sim(pfun, label, thresholds=(0.0,0.02,0.05,0.10)):
    print("\n" + label)
    print("  %-8s %6s %8s %8s %9s %10s" % ("EV기준","픽수","적중률","평균배당","ROI","95%CI"))
    for th in thresholds:
        stakes=[]; 
        for r in R:
            pt = pfun(r)
            for i in range(3):
                ev = pt[i]*r["open"][i] - 1
                if ev > th:
                    stakes.append((r["open"][i], 1.0 if r["y"]==i else 0.0))
        if len(stakes)<20: print("  %-8s %6d  (표본 부족)" % ("+%.0f%%"%(th*100), len(stakes))); continue
        ret=[o*w-1 for o,w in stakes]
        roi=sum(ret)/len(ret); hit=sum(w for o,w in stakes)/len(stakes)
        avgo=sum(o for o,w in stakes)/len(stakes)
        # 부트스트랩 95% CI
        bs=[]
        for _ in range(1500):
            s=sum(ret[random.randrange(len(ret))] for _ in range(len(ret)))/len(ret); bs.append(s)
        bs.sort(); lo,hi = bs[37], bs[1462]
        print("  %-8s %6d %7.1f%% %8.2f %8.2f%% [%+.1f%%, %+.1f%%]"
              % ("+%.0f%%"%(th*100), len(stakes), hit*100, avgo, roi*100, lo*100, hi*100))

random.seed(7)
sim(lambda r: dc.devig_power(r["close"]), "[B] p_true = 클로징 컨센서스 → 오프닝 배당에 베팅 (지연배당 전략)")
sim(lambda r: platt(r["pm"],A,B),        "[C] p_true = 보정된 DC 모델 → 오프닝 배당에 베팅")
sim(lambda r: dc.log_pool([platt(r["pm"],A,B), dc.devig_power(r["open"])],[0.3,0.7]),
    "[D] p_true = 모델30% + 오프닝시장70% → 오프닝 배당에 베팅 (자기참조, 대조군)")

print("\n[E] 오프닝 배당의 마진(오버라운드) 분포")
ov=sorted(sum(1/o for o in r["open"])-1 for r in R)
print("  중앙값 %.3f  하위10%% %.3f  상위10%% %.3f" % (ov[len(ov)//2], ov[len(ov)//10], ov[len(ov)*9//10]))
