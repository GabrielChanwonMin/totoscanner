"""베트맨形 배당 합성 → EV 파이프라인 실전 시뮬레이션.
합성식: 부록 A(1.30/4.20/7.00 vs 적정 1.32/6.35/11.63)에서 역산한
        implied_i = exp(c) * p_i^k   (k<1 → 역배에 마진을 더 얹는 정배/역배 편향)
베트맨은 '초기 시장'을 보고 가격을 매기고 갱신이 느리다고 가정 → p_open 기준으로 합성.
p_true 는 클로징 컨센서스."""
import json, math, random, dc

R = [r for r in json.load(open("cache_preds.json")) if r["close"] and r["open"]]
random.seed(11)

def betman_odds(p, k=0.774, c=-0.046):
    return [1.0 / (math.exp(c) * (x ** k)) for x in p]

# 합성 검증 (부록 A)
fair = [0.7564, 0.1576, 0.0860]
print("부록A 검증: 합성 %s  vs 문서 [1.30, 4.20, 7.00]"
      % [round(o,2) for o in betman_odds(fair)])
print("합성 오버라운드 중앙값 %.3f\n"
      % sorted(sum(1/o for o in betman_odds(dc.devig_power(r["open"])))-1 for r in R)[len(R)//2])

def run(k, label, ths=(0.0,0.02,0.05,0.08,0.12)):
    print(label)
    print("  %-7s %7s %8s %8s %9s %9s %18s" % ("EV기준","픽수","경기당","적중률","평균배당","ROI","95%CI"))
    for th in ths:
        st=[]
        for r in R:
            pt = dc.devig_power(r["close"])
            bo = betman_odds(dc.devig_power(r["open"]), k=k)
            for i in range(3):
                if pt[i]*bo[i]-1 > th: st.append((bo[i], 1.0 if r["y"]==i else 0.0))
        if len(st)<25:
            print("  %-7s %7d   (표본 부족)" % ("+%.0f%%"%(th*100), len(st))); continue
        ret=[o*w-1 for o,w in st]; roi=sum(ret)/len(ret)
        bs=sorted(sum(ret[random.randrange(len(ret))] for _ in range(len(ret)))/len(ret) for _ in range(1200))
        print("  %-7s %7d %8.2f %7.1f%% %8.2f %8.2f%%   [%+.1f%%, %+.1f%%]"
              % ("+%.0f%%"%(th*100), len(st), len(st)/len(R), 100*sum(w for o,w in st)/len(st),
                 sum(o for o,w in st)/len(st), roi*100, bs[30]*100, bs[1169]*100))
    print()

run(0.774, "[F] 베트맨形 (오버라운드 ~15%, 정배/역배 편향 있음)")
run(1.0,   "[G] 대조: 편향 없이 균등 마진 15%만 얹은 경우")

print("[H] 배당 구간별 평균 EV — 베트맨 편향 분석 (기획서 6.2.3)")
buckets=[(1.0,1.3),(1.3,1.6),(1.6,2.0),(2.0,2.6),(2.6,3.5),(3.5,5.0),(5.0,8.0),(8.0,99)]
agg={b:[0.0,0,0.0] for b in buckets}
for r in R:
    pt=dc.devig_power(r["close"]); bo=betman_odds(dc.devig_power(r["open"]))
    for i in range(3):
        for b in buckets:
            if b[0]<=bo[i]<b[1]:
                agg[b][0]+=pt[i]*bo[i]-1; agg[b][1]+=1
                agg[b][2]+= (bo[i]-1 if r["y"]==i else -1)
                break
for b in buckets:
    s,n,ret=agg[b]
    if n>40: print("  %5.1f~%-5.1f  n=%5d  평균EV %+7.2f%%   실현ROI %+7.2f%%" % (b[0],b[1],n,100*s/n,100*ret/n))
