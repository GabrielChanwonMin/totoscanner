#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""베트맨 프로토 승부식 수집기.

기획서 §5 P0. Playwright 없이 순수 HTTP 2회로 회차 전체를 가져온다.
  1) gameSlip 페이지 GET  → JSESSIONID 획득
  2) /buyPsblGame/gameInfoInq.do POST (Content-Type: application/json)
       본문 {"gmId","gmTs","gameYear","_sbmInfo":{"debugMode":"false"}}

사용법:
    python3 collect_betman.py                 # 현재 발매중/예정 회차 자동 탐색
    python3 collect_betman.py 260108          # 특정 회차
    python3 collect_betman.py 260108 --all    # 5대 리그 외 종목까지 전부

출력: snapshots/betman_<회차>_<시각>.json  (append-only 스냅샷)
      latest_import.txt                      (토토스캐너 앱 붙여넣기용)
"""
import json, os, sys, time, datetime as dt, urllib.request, urllib.error, http.cookiejar
try:
    import match_teams
except ImportError:
    match_teams = None

BASE = "https://www.betman.co.kr"
GM_ID = "G101"                     # 프로토 승부식
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "snapshots")
POLITE_DELAY = 5.0                 # 요청 간 최소 간격 (기획서 CLAUDE.md 규칙)

# 앱이 아는 5대 리그
BIG5 = {"잉글랜드 프리미어리그": "E0", "스페인 라리가": "SP1", "이탈리아 세리에A": "I1",
        "독일 분데스리가": "D1", "프랑스 리그1": "F1"}
# 베트맨 betNm → 앱 마켓코드. betTypNm이 아니라 betNm을 봐야
# '축구 승무패'와 '축구 전반 승무패'가 구분된다 (전반은 정산 기준이 90분이 아님 → 제외).
MARKET = {"축구 승무패": "1X2", "축구 핸디캡": "HANDICAP",
          "축구 언더오버": "OU", "축구 SUM": "SUM"}
SKIP_NOTE = {"축구 소수핸디캡": "소수핸디캡(무승부 없는 2지선다, 앱 미지원)"}


def _opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA), ("Accept-Language", "ko-KR,ko;q=0.9")]
    return op


def _retry(fn, tries=4, base=3.0):
    """일시적 네트워크 오류에 지수 백오프로 재시도."""
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            if i == tries - 1:
                raise
            wait = base * (2 ** i)
            print(f"    재시도 {i+1}/{tries-1} ({type(e).__name__}) — {wait:.0f}초 후", flush=True)
            time.sleep(wait)


def fetch_round(gm_ts, year=None):
    """한 회차의 원본 JSON을 가져온다."""
    year = year or str(gm_ts)[:2].join(["20", ""]) if False else ("20" + str(gm_ts)[:2])
    op = _opener()
    page = f"{BASE}/main/mainPage/gamebuy/gameSlip.do?gmId={GM_ID}&year={year}&gmTs={gm_ts}"
    def _page():
        with op.open(page, timeout=30) as r:  # 1) 세션 쿠키
            r.read()
    _retry(_page)
    time.sleep(POLITE_DELAY)
    body = json.dumps({"gmId": GM_ID, "gmTs": int(gm_ts), "gameYear": year,
                       "_sbmInfo": {"debugMode": "false"}}).encode()
    req = urllib.request.Request(f"{BASE}/buyPsblGame/gameInfoInq.do", data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=UTF-8")
    req.add_header("X-Requested-With", "XMLHttpRequest")
    req.add_header("Referer", page)
    def _api():
        with op.open(req, timeout=30) as r:   # 2) 데이터
            return r.read().decode("utf-8", "replace")
    raw = _retry(_api)
    if raw.lstrip().startswith("<"):
        raise RuntimeError(f"{gm_ts}: JSON 대신 HTML이 왔다 (회차가 없거나 요청 형식 변경)")
    return json.loads(raw)


def parse(doc, big5_only=True):
    """columnar compSchedules → 경기 리스트."""
    cs = doc.get("compSchedules") or {}
    if not cs.get("datas"):
        return []
    ix = {n: i for i, n in enumerate(cs["keys"])}
    g = lambda row, k: row[ix[k]] if k in ix else None
    out, skipped = [], {}
    for row in cs["datas"]:
        if g(row, "itemCode") != "SC":                      # 축구만
            continue
        lg = g(row, "leagueName")
        if big5_only and lg not in BIG5:
            continue
        bet_nm = g(row, "betNm") or ""
        mk = MARKET.get(bet_nm)
        if not mk:
            skipped[SKIP_NOTE.get(bet_nm, bet_nm)] = skipped.get(SKIP_NOTE.get(bet_nm, bet_nm), 0) + 1
            continue
        odds = [g(row, "winAllot"), g(row, "drawAllot"), g(row, "loseAllot")]
        odds = [float(o or 0) for o in odds]
        if mk in ("OU", "SUM"):                              # 2지선다는 무 자리를 뺀다
            odds = [odds[0], odds[2]]
        kick = g(row, "gameDate")
        out.append({
            "no": g(row, "matchSeq"),
            "league": BIG5.get(lg, lg), "leagueKo": lg,
            "home": g(row, "homeName"), "away": g(row, "awayName"),
            "homeId": g(row, "homeId"), "awayId": g(row, "awayId"),
            "market": mk,
            "line": g(row, "winHandi"),
            "handiCode": g(row, "handi"),
            "odds": odds,
            "published": all(o > 1 for o in odds),
            "kickoff": dt.datetime.utcfromtimestamp(kick / 1000 + 9 * 3600).strftime("%Y-%m-%dT%H:%M")
                       if kick else None,
            "single": str(g(row, "sgl")),
            "stadium": g(row, "meetStadiumFullName"),
        })
    out.sort(key=lambda m: (m["no"] or 0))
    return out, skipped


def odds_changes(doc):
    """tooltipList = 베트맨이 공개하는 배당 변동 이력 (§6.2.4 지연배당 탐지용)."""
    ch = []
    for t in doc.get("tooltipList") or []:
        ch.append({"no": t.get("GM_SEQ"), "at": t.get("CHG_DTM", "")[:14],
                   "before": [t.get("BCHG_W_ODDS"), t.get("BCHG_D_ODDS"), t.get("BCHG_L_ODDS")],
                   "after": [t.get("ACHG_W_ODDS"), t.get("ACHG_D_ODDS"), t.get("ACHG_L_ODDS")],
                   "lineBefore": t.get("BCHG_W_HANDI_RT"), "lineAfter": t.get("ACHG_W_HANDI_RT")})
    return ch


def _last_collected():
    """snapshots/ 에 남은 가장 큰 회차 번호. 없으면 None."""
    if not os.path.isdir(SNAP):
        return None
    ts = []
    for f in os.listdir(SNAP):
        m = f.split("_")
        if len(m) > 1 and m[0] == "betman" and m[1].isdigit():
            ts.append(int(m[1]))
    return max(ts) if ts else None


def find_current():
    """지금 발매중인 승부식 회차를 찾는다 (요청 1회).
    메인의 '구매가능 게임' 목록에 G101이 있으면 그게 현재 회차다.
    없으면(=발매 전) 마지막 회차 다음 번호를 시도한다."""
    op = _opener()
    def _go():
        with op.open(f"{BASE}/", timeout=30) as r:
            r.read()
        time.sleep(2)
        body = json.dumps({"_sbmInfo": {"debugMode": "false"}}).encode()
        req = urllib.request.Request(f"{BASE}/buyPsblGame/inqCacheBuyAbleGameInfoList.do",
                                     data=body, method="POST")
        req.add_header("Content-Type", "application/json; charset=UTF-8")
        req.add_header("X-Requested-With", "XMLHttpRequest")
        req.add_header("Referer", BASE + "/")
        with op.open(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    try:
        d = _retry(_go)
        for g in (d.get("protoGames") or []):
            if g.get("gmId") == GM_ID:
                return int(g["gmTs"]), None
    except Exception as e:
        print(f"  (구매가능 목록 조회 실패: {e})")
    # 발매 전이면, 마지막으로 수집한 회차부터 앞으로 훑는다 (날짜 추정보다 확실하다)
    last = _last_collected()
    if last is None:
        raise RuntimeError(
            "발매중 회차가 없고 기준 회차도 없다.\n"
            "  betman.co.kr 에서 '프로토 승부식 NNN회차'를 확인하고 직접 지정해라:\n"
            "  python3 collect_betman.py 260109      (2026년 109회차)")
    for ts in range(last, last + 5):
        try:
            doc = fetch_round(ts)
        except Exception:
            continue
        cl = doc.get("currentLottery") or {}
        if cl.get("saleStatus") in ("SaleProgress", "SaleBefore"):
            return ts, doc
        time.sleep(POLITE_DELAY)
    raise RuntimeError("발매중 회차를 못 찾았다. 직접 지정해라: python3 collect_betman.py 260108")


def to_import_text(matches):
    """토토스캐너 앱 '한 번에 붙여넣기' 형식으로 변환."""
    LG = {"E0": "EPL", "SP1": "라리가", "I1": "세리에A", "D1": "분데스", "F1": "리그1"}
    MK = {"1X2": "일반", "HANDICAP": "핸디", "OU": "언오버", "SUM": "SUM"}
    lines = []
    for m in matches:
        if not m["published"] or m["league"] not in LG:
            continue
        parts = [str(m["no"]), LG[m["league"]], m["home"].replace(" ", ""), m["away"].replace(" ", ""), MK[m["market"]]]
        if m["market"] in ("HANDICAP", "OU"):
            parts.append(str(m["line"]))
        parts += [f"{o:.2f}" for o in m["odds"]]
        lines.append(" ".join(parts))
    return "\n".join(lines)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    big5_only = "--all" not in sys.argv
    os.makedirs(SNAP, exist_ok=True)

    if args:
        gm_ts = int(args[0]); doc = fetch_round(gm_ts)
    else:
        print("발매중 회차 탐색 중…")
        gm_ts, doc = find_current()
        if doc is None:
            time.sleep(POLITE_DELAY); doc = fetch_round(gm_ts)

    cl = doc.get("currentLottery") or {}
    fmt = lambda v: dt.datetime.utcfromtimestamp(v / 1000 + 9 * 3600).strftime("%m-%d %H:%M") if v else "—"
    matches, skipped = parse(doc, big5_only)
    changes = odds_changes(doc)
    pub = [m for m in matches if m["published"]]

    print(f"\n프로토 승부식 {cl.get('gmOsidTs')}회차  ({cl.get('saleStatus')})")
    print(f"  발매 {fmt(cl.get('saleStartDate'))} ~ {fmt(cl.get('saleEndDate'))} KST")
    print(f"  {'5대 리그' if big5_only else '축구 전체'} {len(matches)}행 · 배당 공시된 것 {len(pub)}행")
    print(f"  배당 변동 이력 {len(changes)}건")
    if skipped:
        print("  제외: " + ", ".join(f"{k} {v}행" for k, v in sorted(skipped.items(), key=lambda x: -x[1])[:4]))

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    path = os.path.join(SNAP, f"betman_{gm_ts}_{stamp}.json")
    json.dump({"gmTs": gm_ts, "capturedAt": dt.datetime.now().isoformat(timespec="seconds"),
               "round": {"no": cl.get("gmOsidTs"), "saleStatus": cl.get("saleStatus"),
                         "saleStart": cl.get("saleStartDate"), "saleEnd": cl.get("saleEndDate")},
               "matches": matches, "oddsChanges": changes},
              open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n  스냅샷 저장: {os.path.relpath(path, HERE)}")

    # 팀명 → 영문 레이팅 키 매칭 (§7)
    if match_teams and big5_only:
        matches, _ = match_teams.resolve(matches)

    # 앱이 그대로 먹는 JSON
    app = {"source": "betman", "gmTs": gm_ts, "round": cl.get("gmOsidTs"),
           "capturedAt": dt.datetime.now().isoformat(timespec="seconds"),
           "saleEnd": cl.get("saleEndDate"),
           # 팀명은 영문 키만 넣는다. 앱이 한글 이름을 알고 있고,
           # 파일을 순수 ASCII로 유지해야 클립보드 복사가 어디서나 안전하다.
           "matches": [{"no": m["no"], "league": m["league"], "home": m["homeEn"],
                        "away": m["awayEn"],
                        "market": m["market"], "line": m["line"], "betman": m["odds"],
                        "kick": m["kickoff"], "single": m["single"]}
                       for m in matches if m["published"] and m.get("homeEn") and m.get("awayEn")],
           "oddsChanges": changes}
    # 경기가 하나도 없으면 직전에 잘 받아둔 파일을 덮어쓰지 않는다.
    # (5대 리그가 편성되지 않은 회차가 실제로 있다 — A매치 휴식기 등)
    out_json = os.path.join(HERE, "latest_import.json")
    if app["matches"]:
        json.dump(app, open(out_json, "w", encoding="utf-8"), ensure_ascii=False)
    else:
        print("\n  이 회차엔 배당이 붙은 5대 리그 경기가 없다 — latest_import.json 은 그대로 둔다.")
    if pub and app["matches"]:
        txt = to_import_text(matches)
        open(os.path.join(HERE, "latest_import.txt"), "w", encoding="utf-8").write(txt)
        print(f"\n  ▸ 앱 불러오기용: latest_import.json  ({len(app['matches'])}행)")
        print(f"  ▸ 텍스트 버전:   latest_import.txt   ({len(txt.splitlines())}줄)")
        print("\n  ── 미리보기 ──")
        for l in txt.splitlines()[:6]:
            print("   " + l)
    else:
        print("\n  아직 배당이 공시되지 않았다 (발매 시작 시각 이후 다시 실행해라).")
        print(f"  경기 목록만 저장했다: latest_import.json ({len(matches)}행, 배당 0)")


if __name__ == "__main__":
    main()
