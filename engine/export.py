import datetime as dt, json, math, statistics, dc

KO = json.load(open("teams_ko.json"))
ASOF = dt.date(2026, 9, 11)
XI, KAPPA, WIN = 0.0018, 6.0, 1100

ms = dc.load()
out = {"asof": ASOF.isoformat(), "leagues": {}}
for div, name in dc.LEAGUES.items():
    lm = [m for m in ms if m["div"] == div]
    cur = {t for m in lm if m["season"] == "2627" for t in (m["home"], m["away"])}
    tr = [m for m in lm if ASOF - dt.timedelta(days=WIN) <= m["date"] < ASOF]
    f = dc.fit_dc(tr, ASOF, xi=XI, kappa=KAPPA, iters=900)
    teams = {}
    for t in sorted(cur):
        i = f.idx.get(t)
        teams[t] = {"ko": KO.get(t, t),
                    "att": round(f.att[i], 4) if i is not None else round(f.anew, 4),
                    "def": round(f.df[i], 4) if i is not None else round(f.dnew, 4),
                    "new": bool(i is None or f.new[i])}
    out["leagues"][div] = {"name": name, "mu": round(f.mu, 4), "gamma": round(f.gamma, 4),
                           "rho": round(f.rho, 4), "teams": teams,
                           "lastMatch": max(m["date"] for m in lm).isoformat()}
    top = sorted(teams.items(), key=lambda kv: -(kv[1]["att"] + kv[1]["def"]))
    print("%-6s %2d팀 mu=%.3f gamma=%.3f rho=%+.3f | 최상 %s  최하 %s"
          % (name, len(teams), f.mu, f.gamma, f.rho, top[0][1]["ko"], top[-1][1]["ko"]))

# 불확실성 척도: 오프닝→클로징 로짓 이동량 (확률 추정이 얼마나 움직일 수 있는가)
R = [r for r in json.load(open("cache_preds.json")) if r["close"] and r["open"]]
def lg(x): return math.log(max(x,1e-6)/max(1-x,1e-6))
d = [lg(dc.devig_power(r["close"])[i]) - lg(dc.devig_power(r["open"])[i]) for r in R for i in range(3)]
sd_move = statistics.pstdev(d)
dm = [lg(r["pm"][i]) - lg(dc.devig_power(r["close"])[i]) for r in R for i in range(3)]
sd_model = statistics.pstdev(dm)
out["uncertainty"] = {
  "sdLogitMarketMove": round(sd_move, 4), "sdLogitModelVsMarket": round(sd_model, 4),
  # 파생 마켓(승무패 컨센서스에서 뽑아낸 핸디·언오버·SUM) 실측 보정.
  # 1,814경기로 측정 — 자세한 근거는 앱 방법론 탭 '파생 마켓 검증'.
  "derivedSd":   {"HANDICAP": 0.08, "OU": 0.19, "SUM": 0.12},
  "derivedBias": {"OU": 0.087, "SUM": -0.052},
  "derivedCheck": {"n": 1814,
    "handi": {"pred": [0.24, 0.198, 0.562], "act": [0.235, 0.198, 0.567], "ece": 0.0126},
    "ou":    {"ll": 0.67583, "llMarket": 0.67578, "sd": 0.1908},
    "sum":   {"pred": 0.486, "act": 0.473, "ece": 0.0135}}}
print("\n로짓 이동 표준편차: 시장 오프닝→클로징 %.3f | 모델 vs 시장 %.3f" % (sd_move, sd_model))

out["backtest"] = {
  "n": len(R), "seasons": "2023/24~2025/26", "leagues": 5,
  "devig": [{"m":"비례법","rps":0.19288,"ll":0.96392,"ece":0.0105},
            {"m":"파워법","rps":0.19274,"ll":0.96338,"ece":0.0060},
            {"m":"Shin","rps":0.19276,"ll":0.96344,"ece":0.0072}],
  "sources": [{"m":"DC 모델 단독","rps":0.19980,"ll":0.98655,"ece":0.0113},
              {"m":"시장 오프닝","rps":0.19328,"ll":0.96544,"ece":0.0079},
              {"m":"시장 클로징","rps":0.19274,"ll":0.96338,"ece":0.0060}],
  "wMkt": 1.00,
  "stale": [{"th":0,"n":3967,"roi":-0.63,"lo":-5.0,"hi":3.8},
            {"th":2,"n":2535,"roi":0.69,"lo":-5.1,"hi":6.3},
            {"th":5,"n":1283,"roi":2.76,"lo":-5.7,"hi":11.3},
            {"th":10,"n":404,"roi":14.41,"lo":-2.3,"hi":31.9}],
  "modelOnly": [{"th":0,"n":5705,"roi":-12.45},{"th":5,"n":4088,"roi":-14.96}],
  "betmanSim": [{"th":0,"n":513,"per":0.10,"odds":1.55,"roi":5.63,"lo":-0.3,"hi":11.7},
                {"th":2,"n":236,"per":0.05,"odds":1.53,"roi":8.47,"lo":-1.1,"hi":17.1},
                {"th":5,"n":64,"per":0.01,"odds":1.64,"roi":28.39,"lo":9.9,"hi":48.6}],
  "bias": [{"b":"1.00–1.30","n":377,"ev":-0.25,"roi":-0.57},
           {"b":"1.30–1.60","n":1377,"ev":-5.14,"roi":-3.89},
           {"b":"1.60–2.00","n":2020,"ev":-10.79,"roi":-8.98},
           {"b":"2.00–2.60","n":2777,"ev":-17.08,"roi":-18.37},
           {"b":"2.60–3.50","n":5718,"ev":-22.29,"roi":-20.61},
           {"b":"3.50–5.00","n":2267,"ev":-29.16,"roi":-33.38},
           {"b":"5.00–8.00","n":927,"ev":-37.38,"roi":-51.43},
           {"b":"8.00+","n":251,"ev":-44.42,"roi":-49.06}],
  "calib": [{"p":0.076,"a":0.065,"n":338},{"p":0.161,"a":0.142,"n":2007},{"p":0.252,"a":0.259,"n":6251},
            {"p":0.343,"a":0.327,"n":2737},{"p":0.449,"a":0.453,"n":1898},{"p":0.545,"a":0.547,"n":1304},
            {"p":0.644,"a":0.685,"n":758},{"p":0.744,"a":0.767,"n":326},{"p":0.832,"a":0.860,"n":86}]
}
json.dump(out, open("ratings.json","w"), ensure_ascii=False)
print("\nratings.json %.1f KB" % (len(json.dumps(out, ensure_ascii=False))/1024))
