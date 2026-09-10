"""walk-forward 백테스트 (기획서 6.7). 모델 / 시장 / 앙상블 비교."""
import datetime as dt, math, sys, json
import dc

def rps(p, y):
    c = 0.0; s = 0.0
    for i in range(2):
        c += p[i] - (1.0 if y == i else 0.0)
        s += c * c
    return s / 2.0

def metrics(preds):
    n = len(preds)
    ll = sum(-math.log(max(p[y], 1e-9)) for p, y in preds) / n
    r = sum(rps(p, y) for p, y in preds) / n
    br = sum(sum((p[i] - (1.0 if y == i else 0.0)) ** 2 for i in range(3)) for p, y in preds) / n
    # ECE (10 bins, 모든 결과 확률 대상)
    bins = [[0.0, 0.0, 0] for _ in range(10)]
    for p, y in preds:
        for i in range(3):
            b = min(9, int(p[i] * 10))
            bins[b][0] += p[i]; bins[b][1] += (1.0 if y == i else 0.0); bins[b][2] += 1
    tot = sum(b[2] for b in bins)
    ece = sum(b[2] / tot * abs(b[0] / b[2] - b[1] / b[2]) for b in bins if b[2] > 0)
    return dict(n=n, logloss=ll, rps=r, brier=br, ece=ece)

def run(test_seasons, xi, kappa, refit_days=7, window_days=1100, verbose=True):
    ms = dc.load()
    out = {"model": [], "market": [], "blend": {}}
    raw = []   # (p_model, p_market, y, div, season)
    for div in dc.LEAGUES:
        lm = [m for m in ms if m["div"] == div]
        test = [m for m in lm if m["season"] in test_seasons and m["close"]]
        if not test: continue
        f = None; next_fit = dt.date(1900, 1, 1)
        for m in test:
            if m["date"] >= next_fit:
                lo = m["date"] - dt.timedelta(days=window_days)
                tr = [x for x in lm if lo <= x["date"] < m["date"]]
                f = dc.fit_dc(tr, m["date"], xi=xi, kappa=kappa, warm=f)
                next_fit = m["date"] + dt.timedelta(days=refit_days)
            if f is None: continue
            L = dc.lambdas(f, m["home"], m["away"])
            if L is None: continue
            pm = dc.probs_1x2(dc.score_matrix(L[0], L[1], f.rho))
            pk = dc.devig_power(m["close"])
            y = 0 if m["hg"] > m["ag"] else (1 if m["hg"] == m["ag"] else 2)
            raw.append((pm, pk, y, div, m["season"]))
    return raw

def evaluate(raw, wgrid=None):
    res = {}
    res["model"] = metrics([(p, y) for p, k, y, d, s in raw])
    res["market"] = metrics([(k, y) for p, k, y, d, s in raw])
    best = None
    for w in (wgrid or [i / 20 for i in range(21)]):
        pr = [(dc.log_pool([p, k], [1 - w, w]), y) for p, k, y, d, s in raw]
        mt = metrics(pr); mt["w_mkt"] = w
        if best is None or mt["rps"] < best["rps"]: best = mt
    res["blend"] = best
    return res

if __name__ == "__main__":
    import time
    t0 = time.time()
    best = None
    for xi in (0.0012, 0.0018, 0.0025, 0.0035):
        for kappa in (3.0, 6.0, 10.0):
            raw = run(("2425", "2526"), xi, kappa)
            r = evaluate(raw)
            tag = "xi=%.4f k=%.1f" % (xi, kappa)
            print("%s  n=%d  model RPS %.5f LL %.5f | market RPS %.5f LL %.5f | blend w=%.2f RPS %.5f LL %.5f"
                  % (tag, r["model"]["n"], r["model"]["rps"], r["model"]["logloss"],
                     r["market"]["rps"], r["market"]["logloss"],
                     r["blend"]["w_mkt"], r["blend"]["rps"], r["blend"]["logloss"]), flush=True)
            if best is None or r["blend"]["rps"] < best[0]: best = (r["blend"]["rps"], xi, kappa, r)
    print("\nBEST xi=%.4f kappa=%.1f" % (best[1], best[2]))
    print(json.dumps(best[3], indent=1))
    print("elapsed %.0fs" % (time.time() - t0))
