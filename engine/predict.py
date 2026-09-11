#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""앱과 동일한 예측을 파이썬으로 계산한다 (브라우저 없이 회차 예측을 남기기 위함).

앱(JS)과 수식이 같아야 하므로 parity_check.py 로 대조한다.
  경기당 스코어행렬 1개 → 모든 마켓 파생 → EV → 등급
"""
import json, math, os
import dc

HERE = os.path.dirname(os.path.abspath(__file__))
Z80 = 1.2816
MARKET_N = {"1X2": 3, "HANDICAP": 3, "OU": 2, "SUM": 2}

_R = None
def ratings():
    global _R
    if _R is None:
        _R = json.load(open(os.path.join(HERE, "ratings.json"), encoding="utf-8"))
    return _R

clamp = lambda x, a, b: a if x < a else (b if x > b else x)
def logit(p): p = clamp(p, 1e-9, 1-1e-9); return math.log(p/(1-p))
sig = lambda z: 1/(1+math.exp(-z))
def norm(a): s = sum(a); return [x/s for x in a]

# ── 마켓 파생 (dc.score_matrix 결과에서) ──
def mk_1x2(M): return dc.probs_1x2(M)
def mk_handicap(M, k):
    W = D = L = 0.0
    for h, row in enumerate(M):
        for a, p in enumerate(row):
            d = h + k - a
            if d > 1e-9: W += p
            elif abs(d) < 1e-9: D += p
            else: L += p
    return [W, D, L]
def mk_ou(M, line):
    u = o = 0.0
    for h, row in enumerate(M):
        for a, p in enumerate(row):
            if h + a < line: u += p
            elif h + a > line: o += p
    return norm([u, o])
def mk_sum(M, zero_even=True):
    od = ev = 0.0
    for h, row in enumerate(M):
        for a, p in enumerate(row):
            t = h + a
            if t == 0: (ev if zero_even else od)
            if t == 0:
                if zero_even: ev += p
                else: od += p
            elif t % 2: od += p
            else: ev += p
    return [od, ev]

def probs_for(market, line, M, zero_even=True):
    if market == "1X2": return mk_1x2(M)
    if market == "HANDICAP": return mk_handicap(M, float(line or 0))
    if market == "OU": return mk_ou(M, float(line or 2.5))
    return mk_sum(M, zero_even)

# ── 행렬 재구성 (KL 최소화, 앱의 nelderMead 와 동일 목적) ──
def _kl(t, p): return sum(v*math.log(v/max(p[i], 1e-12)) for i, v in enumerate(t) if v > 1e-9)

def reconstruct(goals, seed):
    gs = [g for g in goals if g and g.get("target")]
    has_full = any(len(g["target"]) >= 3 for g in gs)
    anchor = 0.0 if has_full else 0.05
    l0, n0 = math.log(seed["lam"]), math.log(seed["nu"])

    def obj(x):
        a, b = clamp(x[0], -3, 2), clamp(x[1], -3, 2)
        M = dc.score_matrix(math.exp(a), math.exp(b), seed["rho"])
        e = anchor*((a-l0)**2 + (b-n0)**2)
        for g in gs:
            e += g.get("w", 1) * _kl(g["target"], g["project"](M))
        return e

    # Nelder-Mead (2차원)
    S = [[l0, n0], [l0+.12, n0], [l0, n0+.12]]
    F = [obj(p) for p in S]
    for _ in range(220):
        idx = sorted(range(3), key=lambda i: F[i])
        S = [S[i] for i in idx]; F = [F[i] for i in idx]
        if abs(F[2]-F[0]) < 1e-11: break
        c = [(S[0][j]+S[1][j])/2 for j in range(2)]
        ref = [c[j]+(c[j]-S[2][j]) for j in range(2)]; fr = obj(ref)
        if fr < F[0]:
            ex = [c[j]+2*(c[j]-S[2][j]) for j in range(2)]; fe = obj(ex)
            S[2], F[2] = (ex, fe) if fe < fr else (ref, fr)
        elif fr < F[1]:
            S[2], F[2] = ref, fr
        else:
            co = [c[j]+.5*(S[2][j]-c[j]) for j in range(2)]; fc = obj(co)
            if fc < F[2]: S[2], F[2] = co, fc
            else:
                for i in (1, 2):
                    S[i] = [S[0][j]+.5*(S[i][j]-S[0][j]) for j in range(2)]; F[i] = obj(S[i])
    x = S[0]
    return {"lam": math.exp(clamp(x[0], -3, 2)), "nu": math.exp(clamp(x[1], -3, 2)), "rho": seed["rho"]}

def lambdas_of(lg, home, away):
    R = ratings()["leagues"].get(lg)
    if not R: return None
    H, A = R["teams"].get(home), R["teams"].get(away)
    if not H or not A: return None
    return {"lam": math.exp(R["mu"]+R["gamma"]+H["att"]-A["def"]),
            "nu": math.exp(R["mu"]+A["att"]-H["def"]),
            "rho": R["rho"], "new": bool(H.get("new") or A.get("new"))}

def build_matrix(rows, lg, home, away, devig=dc.devig_power):
    seed = lambdas_of(lg, home, away)
    if not seed: return {"error": "no rating"}
    ok = lambda r, n: r and len(r) == n and all(float(x) > 1 for x in r)
    r1 = next((m for m in rows if m["market"] == "1X2" and ok(m.get("ref"), 3)), None)
    rh = next((m for m in rows if m["market"] == "HANDICAP" and ok(m.get("ref"), 3)), None)
    ro = next((m for m in rows if m["market"] == "OU" and ok(m.get("ref"), 2)), None)
    goals = []
    if r1: goals.append({"target": devig([float(x) for x in r1["ref"]]), "project": mk_1x2, "w": 1})
    elif rh: goals.append({"target": devig([float(x) for x in rh["ref"]]),
                           "project": (lambda L: (lambda M: mk_handicap(M, L)))(float(rh.get("line") or 0)), "w": 1})
    if ro: goals.append({"target": devig([float(x) for x in ro["ref"]]),
                         "project": (lambda L: (lambda M: mk_ou(M, L)))(float(ro.get("line") or 2.5)), "w": .7})
    modelM = dc.score_matrix(seed["lam"], seed["nu"], seed["rho"])
    if not goals:
        return {"M": modelM, "seed": seed, "source": "model", "modelM": modelM}
    c = reconstruct(goals, seed)
    return {"M": dc.score_matrix(c["lam"], c["nu"], c["rho"]), "seed": seed,
            "source": "market", "modelM": modelM}

def evaluate(m, B, unc, devig=dc.devig_power, zero_even=True):
    if B.get("error"): return None
    n = MARKET_N[m["market"]]
    pf = probs_for(m["market"], m.get("line"), B["M"], zero_even)
    pm = probs_for(m["market"], m.get("line"), B["modelM"], zero_even) if B.get("modelM") else None
    has_ref = m.get("ref") and len(m["ref"]) == n and all(float(x) > 1 for x in m["ref"])
    base = unc["sdLogitModelVsMarket"] if B["source"] == "model" else unc["sdLogitMarketMove"]
    dis = [abs(logit(pm[i]) - logit(pf[i]))*0.4 for i in range(n)] if (pm and B["source"] != "model") else [0.0]*n
    derived = (not has_ref) and B["source"] != "model"
    p2 = pf
    if derived:
        bias = unc.get("derivedBias", {}).get(m["market"])
        if bias:
            p2 = norm([sig(logit(p) + (bias if i == 1 else -bias)) for i, p in enumerate(pf)])
    dsd = (unc.get("derivedSd", {}).get(m["market"], 0.08) if derived else 0.0)
    plo = [sig(logit(p) - Z80*math.sqrt(base**2 + dis[i]**2 + dsd**2)) for i, p in enumerate(p2)]
    bet = [float(x) for x in (m.get("betman") or [])]
    gradable = B["source"] != "model"
    picks = []
    for i, p in enumerate(p2):
        o = bet[i] if i < len(bet) else 0
        if not o > 1:
            picks.append({"i": i, "p": p, "pLo": plo[i], "fair": 1/p, "odds": None,
                          "ev": None, "evLo": None, "grade": "NODATA"}); continue
        ev, evlo = p*o-1, plo[i]*o-1
        picks.append({"i": i, "p": p, "pLo": plo[i], "fair": 1/p, "odds": o, "ev": ev, "evLo": evlo,
                      "grade": ("NOREF" if not gradable else "REC" if evlo > 0 else "WATCH" if ev > 0 else "INFO")})
    return {"picks": picks, "source": B["source"], "derived": derived,
            "pModel": pm, "pRef": (devig([float(x) for x in m["ref"]]) if has_ref else None),
            "isNew": bool(B["seed"].get("new"))}

def predict_round(app):
    """수집기 JSON → 예측 목록."""
    unc = ratings()["uncertainty"]
    groups = {}
    for m in app["matches"]:
        k = (m["league"], m["home"], m["away"], (m.get("kick") or "")[:10])
        groups.setdefault(k, []).append(m)
    out = []
    for (lg, home, away, day), rows in groups.items():
        B = build_matrix(rows, lg, home, away)
        for m in rows:
            r = evaluate(m, B, unc)
            if not r: continue
            for p in r["picks"]:
                if p["odds"] is None: continue
                out.append({"no": m["no"], "league": lg, "home": home, "away": away,
                            "kick": m.get("kick"), "market": m["market"], "line": m.get("line"),
                            "sel": p["i"], "p": round(p["p"], 5), "pLo": round(p["pLo"], 5),
                            "fair": round(p["fair"], 3), "odds": p["odds"],
                            "ev": round(p["ev"], 5), "evLo": round(p["evLo"], 5),
                            "grade": p["grade"], "source": r["source"], "derived": r["derived"],
                            "pModel": round(r["pModel"][p["i"]], 5) if r["pModel"] else None,
                            "pRef": round(r["pRef"][p["i"]], 5) if r["pRef"] else None,
                            "isNew": r["isNew"]})
    return out
