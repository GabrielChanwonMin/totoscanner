#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""북메이커별 예측 정확도 비교 (기획서 §6.2.2).
"규모가 큰 곳이 잘 맞히나? 평균이 나은가? 가중치를 학습하면 더 나아지나?"
"""
import csv, glob, math, os, statistics
from collections import defaultdict
import dc

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
# (라벨, 컬럼 접두) — C 는 클로징(마감 직전), 없으면 오프닝
BOOKS = [("Bet365","B365C"), ("Pinnacle","PSC"), ("시장 최고배당","MaxC"), ("시장 평균","AvgC")]
OPEN  = [("Bet365","B365"), ("Bwin","BW"), ("Pinnacle","PS"), ("시장 최고배당","Max"), ("시장 평균","Avg")]

def f(r,k):
    v=(r.get(k) or "").strip()
    try:
        x=float(v); return x if x>1.0 else None
    except ValueError: return None

def load(cols):
    out=[]
    for path in sorted(glob.glob(os.path.join(DATA,"*.csv"))):
        for r in csv.DictReader(open(path,encoding="utf-8-sig")):
            if not r.get("HomeTeam"): continue
            try: hg,ag=int(r["FTHG"]),int(r["FTAG"])
            except (ValueError,KeyError,TypeError): continue
            row={}
            ok=True
            for lab,pre in cols:
                o=[f(r,pre+"H"),f(r,pre+"D"),f(r,pre+"A")]
                if None in o: ok=False; break
                row[lab]=o
            if not ok: continue
            row["y"]=0 if hg>ag else (1 if hg==ag else 2)
            out.append(row)
    return out

def metrics(probs, ys):
    n=len(ys)
    ll=sum(-math.log(max(p[y],1e-9)) for p,y in zip(probs,ys))/n
    rps=0.0
    for p,y in zip(probs,ys):
        c=0.0; s=0.0
        for i in range(2):
            c+=p[i]-(1.0 if y==i else 0.0); s+=c*c
        rps+=s/2
    rps/=n
    bins=[[0.0,0,0] for _ in range(10)]
    for p,y in zip(probs,ys):
        for i in range(3):
            b=min(9,int(p[i]*10)); bins[b][0]+=p[i]; bins[b][1]+=(1 if y==i else 0); bins[b][2]+=1
    t=sum(b[2] for b in bins)
    ece=sum(b[2]/t*abs(b[0]/b[2]-b[1]/b[2]) for b in bins if b[2])
    return ll,rps,ece

def report(title, cols):
    rows=load(cols)
    if not rows: print(f"\n{title}: 공통 표본 없음"); return None
    ys=[r["y"] for r in rows]
    print(f"\n{title}  (공통 표본 {len(rows):,}경기)")
    print("  %-14s %9s %9s %9s %9s" % ("소스","Log loss","RPS","ECE","마진"))
    res={}
    for lab,_ in cols:
        P=[dc.devig_power(r[lab]) for r in rows]
        ll,rps,ece=metrics(P,ys)
        ov=statistics.mean(sum(1/o for o in r[lab])-1 for r in rows)
        res[lab]=(P,ll,rps,ece)
        print("  %-14s %9.5f %9.5f %9.4f %8.1f%%" % (lab,ll,rps,ece,ov*100))
    return rows,ys,res

print("="*66)
print(" 북메이커별 예측 정확도 — 실경기로 측정")
print("="*66)
r1=report("[마감 직전 배당]", BOOKS)
r2=report("[초기 배당]", OPEN)

# 가중 학습: 로그-선형 풀링으로 최적 가중치 찾기 (§6.2.2)
if r1:
    rows,ys,res=r1
    labs=[l for l,_ in BOOKS]
    print("\n[여러 곳을 섞으면 더 나아지나] — 로그-선형 풀링")
    # 격자 탐색 (가중치 합=1)
    best=None
    step=0.1
    import itertools
    n=len(labs)
    grid=[w for w in itertools.product([i*step for i in range(11)],repeat=n) if abs(sum(w)-1)<1e-9]
    for w in grid:
        P=[dc.log_pool([res[l][0][i] for l in labs], list(w)) for i in range(len(rows))]
        ll,rps,ece=metrics(P,ys)
        if best is None or ll<best[0]: best=(ll,rps,ece,w)
    print("  최적 가중치: " + ", ".join("%s %.0f%%"%(l,w*100) for l,w in zip(labs,best[3]) if w>0))
    print("  Log loss %.5f · RPS %.5f · ECE %.4f" % (best[0],best[1],best[2]))
    solo=min((res[l][1],l) for l in labs)
    print("  단독 최고: %s %.5f" % (solo[1],solo[0]))
    gain=(solo[0]-best[0])/solo[0]*100
    print("  → 섞어서 얻는 이득: %.3f%% (%s)" % (gain, "의미 있음" if gain>0.3 else "무시할 수준"))
