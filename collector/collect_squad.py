#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""선수단·부상·라인업 이력 수집 (API-Football).

    python3 collect_squad.py --check     키가 붙는지만 확인
    python3 collect_squad.py             오늘 예산만큼 받아서 캐시에 쌓고 squads.json 을 다시 만든다
    python3 collect_squad.py --build     받지 않고 이미 받은 캐시로만 다시 만든다 (0회)
    python3 collect_squad.py --daily 40  오늘은 40회만 쓴다

무료 100회/일이라 두 시즌 라인업(3천 경기 남짓)은 한 번에 못 받는다.
날마다 조금씩 쌓이고, 이번 회차에 나오는 팀부터 먼저 채운다.
"""
import json, os, sys, datetime as dt
import apifoot as AF
from apifoot import Budget

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IMPORT = os.path.join(HERE, "latest_import.json")
OUT = os.path.join(ROOT, "docs", "data", "squads.json")
RATINGS = os.path.join(ROOT, "engine", "ratings.json")

sys.path.insert(0, HERE)
from collect_odds_live import _score as _sc, league_teams as _lt   # 이름 대조기 재사용

SEASONS = None   # 아래 main 에서 [올해, 작년] 으로 채운다


# ═══════════ 1. 팀 이름 대조 ═══════════
def roster(div):
    """football-data 기준 그 리그 팀 목록 — 우리가 이미 갖고 있는 이름들."""
    try:
        r = json.load(open(RATINGS, encoding="utf-8"))
    except Exception:
        return []
    t = ((r.get("leagues") or {}).get(div) or {}).get("teams") or {}
    return sorted(t.keys())


def assign(api_names, ours):
    """API 이름 20개 ↔ 우리 이름 20개를 통째로 짝지어준다.

    이름 하나씩 따로 임계값으로 재면 'Manchester City' 가 'Man United' 와 헷갈려 버려진다.
    양쪽이 같은 20팀이라는 걸 알고 있으니, 점수가 높은 짝부터 차례로 확정하고
    쓴 이름은 빼는 식으로 전체를 맞추면 그런 충돌이 저절로 풀린다.
    """
    ov = {}
    try:
        ov = json.load(open(os.path.join(HERE, "apifoot_aliases.json"), encoding="utf-8"))
    except Exception:
        pass
    out, used_a, used_b = {}, set(), set()
    for a in api_names:                      # 손으로 적어둔 짝이 있으면 그게 먼저다
        b = ov.get(a)
        if b and b in ours:
            out[a] = (b, 1.0); used_a.add(a); used_b.add(b)
    pairs = sorted(((_sc(a, b), a, b) for a in api_names for b in ours), reverse=True)
    for sc, a, b in pairs:
        # 남은 것끼리 억지로 이어붙이면 엉뚱한 팀이 붙는다 (Burnley 가 Hull 이 되는 식).
        # 확실하지 않으면 비워두고 이름을 찍어주는 편이 낫다.
        if sc < 0.55 or a in used_a or b in used_b:
            continue
        out[a] = (b, sc); used_a.add(a); used_b.add(b)
    left = [a for a in api_names if a not in used_a]
    return out, left


def sync_teams(cl, seasons):
    """API 팀 id ↔ 우리 팀 이름. 리그-시즌당 1회."""
    tm = AF.cload("teams.json") or {}
    changed = False
    for div, lid in AF.LEAGUE_ID.items():
        cands = roster(div)
        if not cands:
            continue
        for season in seasons:
            tag = "%s|%d" % (div, season)
            if tag in tm.get("_done", []):
                continue
            try:
                resp = cl.get("teams", league=lid, season=season)
            except Budget:
                raise
            except Exception as e:
                _check_locked(e)
                print("  팀 목록 %s %s: %s" % (div, season, e))
                continue
            ids = {}
            for row in resp:
                t = row.get("team") or {}
                if t.get("name") and t.get("id"):
                    ids[t["name"]] = t["id"]
            paired, left = assign(list(ids), cands)
            hit = len(paired); miss = len(left)
            for nm, (ours, sc) in paired.items():
                tm.setdefault("map", {})["%s|%s" % (div, ours)] = ids[nm]
                tm.setdefault("rev", {})[str(ids[nm])] = "%s|%s" % (div, ours)
            for nm in left:
                print("     매칭 실패: %s (%s) — apifoot_aliases.json 에 적어주면 된다" % (nm, div))
            tm.setdefault("_done", []).append(tag)
            changed = True
            print("  %s %d: %d팀 연결%s" % (div, season, hit, (", %d 실패" % miss) if miss else ""))
    if changed:
        AF.csave(tm, "teams.json")
    return tm


# ═══════════ 2. 선수단 (사진·포지션) ═══════════
SQUAD_TTL = 60      # 이적시장이 지나면 명단이 바뀐다 — 두 달마다 다시 받는다


def sync_squads(cl, tmap, want, stale_ok=False):
    """팀당 1회. want = 우선으로 받을 팀 키 목록.

    stale_ok=False 면 아직 한 번도 안 받은 팀만 (라인업 예산을 먹지 않게).
    True 면 오래된 명단도 갱신한다 — 예산이 남았을 때만 부른다.
    """
    got = AF.cload("player_squads.json") or {}
    at = AF.cload("player_squads_at.json") or {}
    today = dt.date.today().isoformat()
    cut = (dt.date.today() - dt.timedelta(days=SQUAD_TTL)).isoformat()
    order = [k for k in want if k in tmap] + [k for k in tmap if k not in want]
    n = 0
    for k in order:
        fresh = k in got and (at.get(k, "") >= cut or not stale_ok)
        if fresh:
            continue
        if cl.left <= 0:
            break
        try:
            resp = cl.get("players/squads", team=tmap[k])
        except Budget:
            break
        except Exception as e:
            print("  선수단 %s: %s" % (k, e)); continue
        players = (resp[0].get("players") if resp else []) or []
        got[k] = [{"id": p.get("id"), "n": p.get("name"), "num": p.get("number"),
                   "pos": (p.get("position") or "")[:1], "ph": p.get("photo")}
                  for p in players if p.get("id")]
        at[k] = today
        n += 1
    if n:
        AF.csave(got, "player_squads.json"); AF.csave(at, "player_squads_at.json")
        print("  선수단 %d팀 %s (누적 %d/%d)"
              % (n, "갱신" if stale_ok else "새로 받음", len(got), len(tmap)))
    return got


# ═══════════ 3. 부상 ═══════════
def sync_injuries(cl, season):
    """리그당 1회. 매번 새로 받는다 — 이게 제일 빨리 낡는 정보다."""
    out = {}
    for div, lid in AF.LEAGUE_ID.items():
        if cl.left <= 0:
            break
        try:
            resp = cl.get("injuries", league=lid, season=season)
        except Budget:
            break
        except Exception as e:
            _check_locked(e)
            print("  부상 %s: %s" % (div, e)); continue
        for row in resp:
            tid = ((row.get("team") or {}).get("id"))
            p = row.get("player") or {}
            if not tid or not p.get("id"):
                continue
            out.setdefault(str(tid), {})[str(p["id"])] = {
                "n": p.get("name"), "t": p.get("type"), "r": p.get("reason"),
                "d": ((row.get("fixture") or {}).get("date") or "")[:10]}
    if out:
        out["_asof"] = dt.date.today().isoformat()
        AF.csave(out, "injuries.json")
        print("  부상자 %d팀분" % (len(out) - 1))
    return AF.cload("injuries.json") or {}


# ═══════════ 4. 경기 목록 ═══════════
def sync_fixtures(cl, seasons):
    """리그-시즌당 1회. 지난 시즌은 한 번 받으면 끝, 이번 시즌은 일주일마다."""
    fx = AF.cload("fixtures.json") or {}
    today = dt.date.today().isoformat()
    for div, lid in AF.LEAGUE_ID.items():
        for season in seasons:
            tag = "%s|%d" % (div, season)
            cur = fx.get(tag)
            stale = (not cur) or (season == seasons[0] and
                                  (cur.get("_at", "") < (dt.date.today() - dt.timedelta(days=6)).isoformat()))
            if not stale or cl.left <= 0:
                continue
            try:
                resp = cl.get("fixtures", league=lid, season=season)
            except Budget:
                return fx
            except Exception as e:
                _check_locked(e)
                print("  경기목록 %s: %s" % (tag, e)); continue
            rows = []
            for r in resp:
                f = r.get("fixture") or {}
                t = r.get("teams") or {}
                st = ((f.get("status") or {}).get("short") or "")
                if st not in ("FT", "AET", "PEN"):     # 끝난 경기만 (라인업이 확정된 것)
                    continue
                rows.append({"id": f.get("id"), "d": (f.get("date") or "")[:10],
                             "h": ((t.get("home") or {}).get("id")),
                             "a": ((t.get("away") or {}).get("id"))})
            fx[tag] = {"_at": today, "rows": [r for r in rows if r["id"] and r["h"] and r["a"]]}
            print("  %s: 끝난 경기 %d개" % (tag, len(fx[tag]["rows"])))
    AF.csave(fx, "fixtures.json")
    return fx


# ═══════════ 5. 라인업 (제일 비싼 단계) ═══════════
TARGET = 45      # 팀당 이만큼 모이면 충분하다 — 그 뒤로는 더 받지 않는다


def backfill_lineups(cl, fx, priority_ids):
    """경기 하나당 1회. 어느 팀이든 빨리 쓸 만해지도록 고르게 퍼뜨린다.

    리그 순서대로 쭉 받으면 마지막 리그는 한 달 뒤에야 쓸 수 있다. 그래서
    '두 팀 중 자료가 더 적은 쪽'이 가장 부족한 경기부터 받는다. 이번 회차에
    나오는 팀은 그보다도 먼저다.
    """
    done = AF.cload("lineups.json") or {}
    have = {}                       # 팀 id → 이미 받은 경기 수
    fixt = {}                       # 경기 id → (날짜, 홈, 원정)
    for tag, blk in fx.items():
        if tag.startswith("_"):
            continue
        for r in blk.get("rows", []):
            fixt[str(r["id"])] = (r["d"], r["h"], r["a"])
    for fid in done:
        f = fixt.get(fid)
        if f:
            have[f[1]] = have.get(f[1], 0) + 1
            have[f[2]] = have.get(f[2], 0) + 1

    pend = [(fid, f) for fid, f in fixt.items() if fid not in done]
    n = 0
    while cl.left > 0 and pend:
        def rank(item):
            fid, (d, h, a) = item
            hot = 0 if (h in priority_ids or a in priority_ids) else 1
            need = min(TARGET - have.get(h, 0), TARGET - have.get(a, 0))
            # 부족한 팀이 낀 경기부터, 그 안에서는 최근 경기부터
            return (hot, -need, [-ord(c) for c in d])
        pend.sort(key=rank)
        fid, (d, h, a) = pend[0]
        if have.get(h, 0) >= TARGET and have.get(a, 0) >= TARGET:
            break                   # 남은 건 전부 충분히 채워진 팀들이다
        pend.pop(0)
        try:
            resp = cl.get("fixtures/lineups", fixture=int(fid))
        except Budget:
            break
        except Exception as e:
            print("  라인업 %s: %s" % (fid, e)); continue
        rec = []
        for side in resp:
            t = (side.get("team") or {}).get("id")
            xi = [[(p.get("player") or {}).get("id"), (p.get("player") or {}).get("grid") or "",
                   ((p.get("player") or {}).get("pos") or "")[:1]]
                  for p in (side.get("startXI") or []) if (p.get("player") or {}).get("id")]
            if t and xi:
                rec.append({"t": t, "f": side.get("formation") or "", "xi": xi})
        # 응답이 비어도 기록한다 — 안 그러면 같은 경기를 영원히 다시 부른다
        done[fid] = {"d": d, "s": rec}
        have[h] = have.get(h, 0) + 1; have[a] = have.get(a, 0) + 1
        n += 1
        if n % 25 == 0:
            AF.csave(done, "lineups.json")
    if n:
        AF.csave(done, "lineups.json")
    ready = sum(1 for t in have if have[t] >= 8)
    print("  라인업 %d경기 새로 받음 — 누적 %d경기 · 예상 라인업이 서는 팀 %d개"
          % (n, len(done), ready))
    return done


# ═══════════ 6. 이번 회차 팀 뽑기 ═══════════
def round_teams(tmap):
    """latest_import.json 에 들어 있는 팀 = 이번에 실제로 볼 경기."""
    try:
        d = json.load(open(IMPORT, encoding="utf-8"))
    except Exception:
        return [], set()
    keys = []
    for m in d.get("matches", []):
        for side in ("home", "away"):
            k = "%s|%s" % (m.get("league"), m.get(side))
            if k in tmap and k not in keys:
                keys.append(k)
    return keys, {tmap[k] for k in keys}


class SeasonLocked(Exception):
    """무료 요금제가 이 시즌을 막았다. 리그마다 똑같이 터지므로 즉시 멈춘다."""


def locked_note(e):
    print("\n  \033[33m이 요금제로는 이번 시즌 선수 자료를 못 받는다.\033[0m")
    print("  %s" % e)
    print("  무료 플랜은 2022~2024 시즌까지만 열려 있다. 예상 라인업·부상자는")
    print("  이번 시즌 자료라야 쓸모가 있어서, 요금제를 올리기 전까지는 이 구역이 안 나온다.")
    print("  앱의 나머지 기능(배당 비교 · EV · 등급)은 그대로 돈다.")


def _check_locked(e):
    if "do not have access to this season" in str(e):
        raise SeasonLocked(str(e))


def main():
    args = sys.argv[1:]
    daily = AF.DAILY_DEFAULT
    if "--daily" in args:
        daily = int(args[args.index("--daily") + 1])
    build_only = "--build" in args

    if not AF.key():
        print("footballApiKey 가 없다 — 선수단·부상·라인업은 건너뛴다.")
        print("  받으려면: '선수정보 키 등록.command' 를 더블클릭해라 (유료 요금제 필요)")
        return 3        # 0 이 아니어야 실행 스크립트가 Transfermarkt 로 넘어간다

    s0 = AF.season_now()
    seasons = [s0, s0 - 1]      # 이번·지난 두 시즌 (스쿼드가 크게 안 바뀌는 구간)
    cl = AF.Client(daily=daily)

    if "--check" in args:
        try:
            r = cl.get("status")
            acc = (r or {}).get("subscription") or {}
            print("연결 OK — 요금제 %s, 오늘 %s/%s 사용"
                  % (acc.get("plan"), ((r or {}).get("requests") or {}).get("current"),
                     ((r or {}).get("requests") or {}).get("limit_day")))
            return 0
        except Exception as e:
            print("연결 실패: %s" % e); return 1

    tm = AF.cload("teams.json") or {}
    if not build_only:
        print("오늘 남은 호출: %d회" % cl.left)
        try:
            tm = sync_teams(cl, seasons)
        except SeasonLocked as e:
            locked_note(e); return 3
        except Budget:
            print("  예산 소진 — 다음 실행에서 이어받는다")
    tmap = tm.get("map", {})
    if not tmap:
        print("팀 연결이 아직 없다. 내일 다시 실행하면 이어서 받는다.")
        return 3

    want, want_ids = round_teams(tmap)
    if want:
        print("이번 회차 팀 %d개를 먼저 채운다" % len(want))

    if build_only:
        squads = AF.cload("player_squads.json") or {}
        inj = AF.cload("injuries.json") or {}
        fx = AF.cload("fixtures.json") or {}
        lu = AF.cload("lineups.json") or {}
    else:
        try:
            inj = sync_injuries(cl, s0)
            squads = sync_squads(cl, tmap, want)
            fx = sync_fixtures(cl, seasons)
            lu = backfill_lineups(cl, fx, want_ids)
            if cl.left > 15:            # 라인업을 다 채우고도 남으면 명단을 새로 고친다
                squads = sync_squads(cl, tmap, want, stale_ok=True)
        except SeasonLocked as e:
            locked_note(e); return 3
        except Budget as e:
            print("  예산 소진: %s — 다음 실행에서 이어받는다" % e)
            squads = AF.cload("player_squads.json") or {}
            inj = AF.cload("injuries.json") or {}
            fx = AF.cload("fixtures.json") or {}
            lu = AF.cload("lineups.json") or {}
        print("오늘 %d회 썼다" % cl.b.get("used", 0))

    import build_squads
    build_squads.build(tm, squads, inj, fx, lu, OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
