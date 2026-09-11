#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""해외 북메이커 실시간 배당 수집 — The Odds API.

football-data 의 fixtures.csv 는 그쪽이 올려줄 때까지 기다려야 해서 회차 마감보다 늦을 수 있다.
이건 북메이커가 지금 걸어둔 배당을 직접 가져온다.

    python3 collect_odds_live.py            # latest_import.json 에 병합
    python3 collect_odds_live.py --check    # 붙는지만 확인 (파일 안 고침)

키는 collector/secrets.json 의 "oddsApiKey" 에 넣는다 (the-odds-api.com 무료 가입).
무료 500회/월 · 5대 리그 한 번 갱신에 5회 소모.
"""
import json, os, re, sys, urllib.request, urllib.error, datetime as dt
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SEC = os.path.join(HERE, "secrets.json")
SRC = os.path.join(HERE, "latest_import.json")
ALIAS = os.path.join(HERE, "odds_api_aliases.json")
RATINGS = os.path.join(os.path.dirname(HERE), "engine", "ratings.json")

SPORTS = {"soccer_epl": "E0", "soccer_spain_la_liga": "SP1", "soccer_italy_serie_a": "I1",
          "soccer_germany_bundesliga": "D1", "soccer_france_ligue_one": "F1"}
BASE = "https://api.the-odds-api.com/v4"

# 팀 이름을 리그별 후보 목록에 대고 점수로 맞춘다.
# 단순 정규화는 위험하다 — "Manchester United" 와 "Manchester City" 가 같아져 버린다.
NOISE = ["football club", "fc", "afc", "cf", "sc", "ss", "us", "rc", "cd", "ud", "sd",
         "and hove", "olympique", "stade", "racing", "club", "de", "the", "calcio", "bc"]
ABBR = {"ath": "atletico athletic", "sg": "saintgermain", "nott m": "nottingham",
        "m gladbach": "monchengladbach", "rb": "rasenballsport"}


def _tok(s):
    s = (s or "").lower()
    s = s.replace("'", " ").replace("-", " ").replace(".", " ")
    s = re.sub(r"[^a-z\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for d in NOISE:
        s = re.sub(r"(?:^|\s)" + re.escape(d) + r"(?:\s|$)", " ", s)
    return [t for t in s.split() if t]


def norm(s):
    return "".join(_tok(s))


def _score(a, b):
    """a=API 이름, b=우리 이름. 0~1."""
    import difflib
    ta, tb = _tok(a), _tok(b)
    na, nb = "".join(ta), "".join(tb)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    best = difflib.SequenceMatcher(None, na, nb).ratio()
    # 토큰 단위 포함 (Borussia Dortmund ↔ Dortmund)
    sa, sb = set(ta), set(tb)
    if sa & sb:
        best = max(best, len(sa & sb) / max(len(sa), len(sb)) * 0.95)
    # 접두 일치 (Wolverhampton ↔ Wolves)
    for x, y in ((na, nb), (nb, na)):
        k = 0
        while k < min(len(x), len(y)) and x[k] == y[k]:
            k += 1
        if k >= 5:
            best = max(best, 0.80 + min(k, 10) / 100)
    # 축약어 (Ath Madrid ↔ Atletico Madrid)
    for t in tb:
        if t in ABBR and any(w.startswith(t) or w in ABBR[t].split() for w in ta):
            best = max(best, 0.86)
    return best


_TEAMS = None
def league_teams(lg):
    global _TEAMS
    if _TEAMS is None:
        R = json.load(open(RATINGS, encoding="utf-8"))
        _TEAMS = {d: list(L["teams"].keys()) for d, L in R["leagues"].items()}
    return _TEAMS.get(lg, [])


def match_team(api_name, lg, alias):
    """→ (우리이름, 점수). 확실하지 않으면 (None, 점수)."""
    k = lg + "|" + api_name
    if k in alias:
        return alias[k], 1.0
    cands = league_teams(lg)
    if not cands:
        return None, 0.0
    scored = sorted(((_score(api_name, c), c) for c in cands), reverse=True)
    top, second = scored[0], (scored[1] if len(scored) > 1 else (0.0, None))
    # 1등이 충분히 높고 2등과 벌어져야 채택한다 (오매칭 방지)
    if top[0] >= 0.72 and top[0] - second[0] >= 0.08:
        return top[1], top[0]
    return None, top[0]


def load_key():
    if not os.path.exists(SEC):
        return None
    try:
        return (json.load(open(SEC, encoding="utf-8")).get("oddsApiKey") or "").strip() or None
    except Exception:
        return None


def fetch(sport, key, markets="h2h,totals"):
    """요청 1회 비용 = 지역 수 x 마켓 수. eu(1) x h2h,totals(2) = 2회.
    5대 리그면 한 번 돌릴 때 10회 소모된다."""
    url = (f"{BASE}/sports/{sport}/odds/?apiKey={key}&regions=eu&markets={markets}"
           f"&oddsFormat=decimal&dateFormat=iso")
    req = urllib.request.Request(url, headers={"User-Agent": "totoscanner/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return (json.loads(r.read().decode("utf-8")),
                r.headers.get("x-requests-remaining"),
                r.headers.get("x-requests-used"))


def consensus(event, market_key, want=None):
    """여러 북메이커 배당의 평균을 낸다 (한 곳에 의존하지 않게)."""
    buckets = {}
    for bk in event.get("bookmakers", []):
        for mk in bk.get("markets", []):
            if mk.get("key") != market_key:
                continue
            if want is not None and market_key == "totals":
                pts = {o.get("point") for o in mk.get("outcomes", [])}
                if want not in pts:
                    continue
            for o in mk.get("outcomes", []):
                if market_key == "totals" and want is not None and o.get("point") != want:
                    continue
                nm = o.get("name")
                pr = o.get("price")
                if nm and pr and pr > 1:
                    buckets.setdefault(nm, []).append(pr)
    return {k: sum(v) / len(v) for k, v in buckets.items() if v}, \
           max((len(v) for v in buckets.values()), default=0)


def build_index(app):
    """우리 경기 → 찾기 쉽게"""
    idx = {}
    for m in app["matches"]:
        idx.setdefault((m["league"], norm(m["home"]), norm(m["away"])), []).append(m)
    return idx


def main():
    check = "--check" in sys.argv
    # --cheap : 승무패만 받아 소모를 절반(5회)으로 줄인다.
    #           언더오버 배당은 못 받지만, 같은 경기 승무패에서 파생되므로 등급은 나온다.
    markets = "h2h" if "--cheap" in sys.argv else "h2h,totals"
    key = load_key()
    if not key:
        print("  The Odds API 키가 없다 (collector/secrets.json 의 oddsApiKey).")
        return 2
    if not os.path.exists(SRC):
        print("  수집 데이터가 없다. collect_betman.py 를 먼저 돌려라.")
        return 1
    app = json.load(open(SRC, encoding="utf-8"))
    if not app.get("matches"):
        print("  경기가 없다."); return 1

    alias = json.load(open(ALIAS, encoding="utf-8")) if os.path.exists(ALIAS) else {}
    idx = build_index(app)
    ours = {}
    for m in app["matches"]:
        if m["market"] == "1X2":
            ours.setdefault(m["league"], []).append(m)

    hit = 0; miss = []; remain = None; used = None
    for sport, lg in SPORTS.items():
        if lg not in ours:
            continue
        try:
            events, remain, used = fetch(sport, key, markets)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:160]
            print(f"  {lg}: 요청 실패 {e.code} {body}")
            if e.code == 401:
                return 2
            continue
        except Exception as e:
            print(f"  {lg}: 요청 실패 {e}"); continue

        # 이벤트를 우리 경기에 붙인다
        for ev in events:
            h, a = ev.get("home_team"), ev.get("away_team")
            if not h or not a:
                continue
            kh = alias.get(lg + "|" + h) or h
            ka = alias.get(lg + "|" + a) or a
            k = (lg, norm(kh), norm(ka))
            rows = idx.get(k)
            if not rows:
                continue
            h2h, nbk = consensus(ev, "h2h")
            if len(h2h) >= 3:
                # 홈/무/원정 순서로 정렬
                draw = next((v for kk, v in h2h.items() if kk.lower() == "draw"), None)
                ph = h2h.get(h); pa = h2h.get(a)
                if ph and pa and draw:
                    for m in rows:
                        if m["market"] == "1X2":
                            m["ref"] = [round(ph, 2), round(draw, 2), round(pa, 2)]
                            m["refBooks"] = nbk
                            hit += 1
            # 언더오버: 우리가 쓰는 기준선에 맞는 것만
            for m in rows:
                if m["market"] != "OU":
                    continue
                line = float(m.get("line") or 2.5)
                tot, nb2 = consensus(ev, "totals", want=line)
                u = next((v for kk, v in tot.items() if kk.lower().startswith("under")), None)
                o = next((v for kk, v in tot.items() if kk.lower().startswith("over")), None)
                if u and o:
                    m["ref"] = [round(u, 2), round(o, 2)]; m["refBooks"] = nb2

        got = {(norm(e.get("home_team")), norm(e.get("away_team"))) for e in events}
        for m in ours[lg]:
            if not m.get("ref"):
                miss.append((lg, m["home"], m["away"]))

    n1 = sum(len(v) for v in ours.values())
    print(f"  승무패 {n1}경기 중 {hit}경기에 실시간 해외 배당을 붙였다.")
    if "--cheap" in sys.argv:
        print("  (--cheap: 승무패만 받아 소모를 절반으로 줄였다)")
    if remain is not None:
        try:
            rm = int(remain)
            runs = rm // 10
            bar = "남음 %s회" % remain + (f" (이번 달 {used}회 사용)" if used else "")
            if rm < 60:
                print(f"  \033[31m⚠ 이번 달 요청이 거의 소진됐다 — {bar}\033[0m")
                print(f"    앞으로 {runs}번쯤 더 돌릴 수 있다. 다음 달 1일에 초기화된다.")
            elif rm < 150:
                print(f"  \033[33m이번 달 {bar} · 약 {runs}번 더 가능\033[0m")
            else:
                print(f"  이번 달 {bar} · 약 {runs}번 더 가능")
        except ValueError:
            print(f"  이번 달 남은 요청: {remain}")
    if miss:
        print(f"  ⚠ 못 붙인 {len(miss)}경기 — 이름이 다를 수 있다:")
        for lg, h, a in miss[:10]:
            print(f"     {lg}  {h} vs {a}")
        print(f"     (odds_api_aliases.json 에 \"{miss[0][0]}|API쪽이름\": \"{miss[0][1]}\" 형태로 넣으면 된다)")

    if check:
        print("  --check 모드라 파일은 고치지 않았다."); return 0
    app["refSource"] = "the-odds-api (live)"
    app["refFetchedAt"] = dt.datetime.now().isoformat(timespec="seconds")
    json.dump(app, open(SRC, "w"), ensure_ascii=True)
    print(f"  저장: latest_import.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
