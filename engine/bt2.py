"""예측 캐시 생성: 모델확률 + 오프닝/클로징 배당 + 결과."""
import datetime as dt, json, math, sys
import dc

def build(xi=0.0018, kappa=6.0, refit_days=7, window_days=1100,
          test_seasons=("2324","2425","2526")):
    ms = dc.load()
    rows = []
    for div in dc.LEAGUES:
        lm = [m for m in ms if m["div"] == div]
        test = [m for m in lm if m["season"] in test_seasons]
        f = None; next_fit = dt.date(1900,1,1)
        for m in test:
            if m["date"] >= next_fit:
                lo = m["date"] - dt.timedelta(days=window_days)
                tr = [x for x in lm if lo <= x["date"] < m["date"]]
                f = dc.fit_dc(tr, m["date"], xi=xi, kappa=kappa, warm=f)
                next_fit = m["date"] + dt.timedelta(days=refit_days)
            if f is None: continue
            L = dc.lambdas(f, m["home"], m["away"])
            if L is None: continue
            M = dc.score_matrix(L[0], L[1], f.rho)
            y = 0 if m["hg"]>m["ag"] else (1 if m["hg"]==m["ag"] else 2)
            rows.append(dict(div=div, season=m["season"], date=m["date"].isoformat(),
                             home=m["home"], away=m["away"], y=y,
                             lam=L[0], nu=L[1], rho=f.rho,
                             pm=dc.probs_1x2(M), close=m["close"],
                             open=m.get("open"), hg=m["hg"], ag=m["ag"]))
    return rows

if __name__ == "__main__":
    xi = float(sys.argv[1]) if len(sys.argv)>1 else 0.0018
    kp = float(sys.argv[2]) if len(sys.argv)>2 else 6.0
    r = build(xi=xi, kappa=kp)
    json.dump(r, open("cache_preds.json","w"))
    print("rows", len(r))
