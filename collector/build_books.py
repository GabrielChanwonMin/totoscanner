#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""북메이커별 배당 비교표 → docs/data/books.json.

collect_odds_live.py 가 남긴 원본(odds_raw.json)만 읽는다. API 를 다시 부르지 않는다.
지금까지는 여러 북메이커 배당을 받아서 평균만 쓰고 개별 값은 버리고 있었다.
그걸 그대로 살려서 "어느 사이트가 이 픽에 제일 좋은 값을 주는가"를 보여준다.
"""
import json, os, sys, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(HERE, "odds_raw.json")
SRC = os.path.join(HERE, "latest_import.json")
OUT = os.path.join(ROOT, "docs", "data", "books.json")

sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))
from collect_odds_live import match_team, norm
from dc import devig_power

# 북메이커 홈페이지. 없는 곳은 링크 없이 이름만 나온다.
SITE = {
    "Pinnacle": "https://www.pinnacle.com/", "Betfair": "https://www.betfair.com/exchange/",
    "Betfair Sportsbook": "https://www.betfair.com/sport/", "Smarkets": "https://smarkets.com/",
    "Matchbook": "https://www.matchbook.com/", "1xBet": "https://1xbet.com/",
    "William Hill": "https://sports.williamhill.com/", "Ladbrokes": "https://sports.ladbrokes.com/",
    "Coral": "https://sports.coral.co.uk/", "Paddy Power": "https://www.paddypower.com/",
    "Sky Bet": "https://m.skybet.com/", "Betway": "https://betway.com/",
    "888sport": "https://www.888sport.com/", "Unibet (UK)": "https://www.unibet.co.uk/",
    "Unibet (FR)": "https://www.unibet.fr/", "Unibet (NL)": "https://www.unibet.nl/",
    "Unibet (SE)": "https://www.unibet.se/", "Betsson": "https://www.betsson.com/",
    "LeoVegas": "https://www.leovegas.com/", "LeoVegas (SE)": "https://www.leovegas.se/",
    "Winamax (FR)": "https://www.winamax.fr/", "Winamax (DE)": "https://www.winamax.de/",
    "Betclic (FR)": "https://www.betclic.fr/", "PMU (FR)": "https://www.pmu.fr/",
    "Marathon Bet": "https://www.marathonbet.com/", "Tipico": "https://www.tipico.de/",
    "BoyleSports": "https://www.boylesports.com/", "Betfred (UK)": "https://www.betfred.com/",
    "Bet Victor": "https://www.betvictor.com/", "Betano (UK)": "https://www.betano.co.uk/",
    "Virgin Bet": "https://www.virginbet.com/", "LiveScore Bet": "https://www.livescorebet.com/",
    "Grosvenor": "https://www.grosvenorsport.com/", "Casumo": "https://www.casumo.com/",
    "Nordic Bet": "https://www.nordicbet.com/", "Coolbet": "https://www.coolbet.com/",
    "Everygame": "https://www.everygame.eu/", "BetOnline.ag": "https://www.betonline.ag/",
    "MyBookie.ag": "https://www.mybookie.ag/", "GTbets": "https://www.gtbets.eu/",
    "Codere (IT)": "https://www.codere.it/", "BetAnything": "",
}
# 호가를 양쪽으로 받는 교환소 — 마진 구조가 달라서 따로 표시한다
EXCHANGE = {"Betfair", "Smarkets", "Matchbook"}


def main():
    if not os.path.exists(RAW):
        print("  원본이 없다 — collect_odds_live.py 를 먼저 돌려라."); return 1
    raw = json.load(open(RAW, encoding="utf-8"))
    app = json.load(open(SRC, encoding="utf-8"))

    # 우리 경기 색인 (리그, 홈, 원정) → 베트맨 배당
    betman = {}
    for m in app.get("matches", []):
        k = (m["league"], norm(m["home"]), norm(m["away"]))
        slot = betman.setdefault(k, {"home": m["home"], "away": m["away"],
                                     "kick": (m.get("kick") or "")[:16], "no": m.get("no")})
        if m["market"] == "1X2" and m.get("betman"):
            slot["bm"] = [float(x) for x in m["betman"]]
        if m["market"] == "OU" and m.get("betman"):
            slot.setdefault("bmou", {})[str(m.get("line"))] = [float(x) for x in m["betman"]]

    names, idx = [], {}
    def bid(title):
        if title not in idx:
            idx[title] = len(names); names.append(title)
        return idx[title]

    out, matched = {}, 0
    for lg, events in (raw.get("leagues") or {}).items():
        for ev in events:
            h, a = ev.get("home_team"), ev.get("away_team")
            if not h or not a:
                continue
            mh, _ = match_team(h, lg, {})
            ma, _ = match_team(a, lg, {})
            if not mh or not ma:
                continue
            key = (lg, norm(mh), norm(ma))
            # 베트맨 회차에 없는 경기도 담는다. 베트맨은 보통 킥오프 며칠 전에야
            # 배당을 걸기 때문에, 그때까지 비교표가 비어 있으면 쓸모가 없다.
            ours = betman.get(key) or {}
            rec = {"lg": lg, "h": mh, "a": ma,
                   "kick": ours.get("kick") or (ev.get("commence_time") or "")[:16],
                   "no": ours.get("no"), "bm": ours.get("bm"), "h2h": {}, "ou": {}}
            for b in ev.get("bookmakers", []):
                t = b.get("title")
                if not t:
                    continue
                for mk in b.get("markets", []):
                    os_ = {o.get("name"): o.get("price") for o in mk.get("outcomes", [])}
                    if mk.get("key") == "h2h":
                        tri = [os_.get(h), os_.get("Draw"), os_.get(a)]
                        if all(x and x > 1 for x in tri):
                            rec["h2h"][str(bid(t))] = [round(x, 2) for x in tri]
                    elif mk.get("key") == "totals":
                        pts = {}
                        for o in mk.get("outcomes", []):
                            p, nm_, pr = o.get("point"), (o.get("name") or "").lower(), o.get("price")
                            if p is None or not pr or pr <= 1:
                                continue
                            pts.setdefault(str(p), {})[nm_[:1]] = round(pr, 2)
                        for line, uo in pts.items():
                            if "u" in uo and "o" in uo:
                                rec["ou"].setdefault(line, {})[str(bid(t))] = [uo["u"], uo["o"]]
            if len(rec["h2h"]) >= 3:
                rec["bmou"] = ours.get("bmou")
                # 적정배당은 북메이커 평균을 마진 제거해서 낸다.
                # 백테스트에서 '여러 곳 단순 평균'이 가장 잘 맞았다 (ECE 0.0034).
                tri = list(zip(*rec["h2h"].values()))
                avg = [sum(c) / len(c) for c in tri]
                fair = devig_power(avg)
                rec["fair"] = [round(1.0 / p, 3) for p in fair]
                rec["nb"] = len(rec["h2h"])
                out["%s|%s|%s" % (lg, mh, ma)] = rec
                matched += 1

    doc = {"asof": raw.get("at") or dt.datetime.now().isoformat(timespec="seconds"),
           "regions": raw.get("regions"),
           "books": [{"n": n, "u": SITE.get(n, ""), "x": n in EXCHANGE} for n in names],
           "matches": out}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(doc, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    avg = sum(len(v["h2h"]) for v in out.values()) / max(1, len(out))
    print("  books.json — %d경기 · 북메이커 %d곳 (경기당 평균 %.0f곳) · %.0fKB"
          % (matched, len(names), avg, os.path.getsize(OUT) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
