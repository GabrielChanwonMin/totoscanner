#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transfermarkt → docs/data/squads.json (예상 선발 · 결장자 · 선수 사진).

    python3 collect_tm.py            이번 회차 팀만 (보통 40팀 남짓, 3~4분)
    python3 collect_tm.py --all      5대 리그 전체 (98팀, 10분 넘는다)
    python3 collect_tm.py --build    받지 않고 캐시로만 다시 만든다

예상 선발은 **이번 시즌 리그 출전 시간 상위 11명**이다. 결장자로 잡힌 선수는 빼고
다음 순번을 올린다. 상대가 강팀이냐 약팀이냐로 나누는 건 경기별 라인업 이력이
있어야 하는데, 그건 유료 API 몫이라 여기선 못 한다.
"""
import json, os, re, sys, datetime as dt
import transfermarkt as T

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IMPORT = os.path.join(HERE, "latest_import.json")
OUT = os.path.join(ROOT, "docs", "data", "squads.json")
RATINGS = os.path.join(ROOT, "engine", "ratings.json")
MAP = os.path.join(T.CACHE, "_clubs.json")

sys.path.insert(0, HERE)
from collect_squad import assign          # 전역 짝짓기 재사용

# 세부 포지션 → (줄, 좌우). 줄 1=골키퍼, 4=최전방. 좌우 0=왼쪽 1=중앙 2=오른쪽
POS = {
    "Goalkeeper": (1, 1),
    "Centre-Back": (2, 1), "Left-Back": (2, 0), "Right-Back": (2, 2), "Defender": (2, 1),
    "Defensive Midfield": (3, 1), "Central Midfield": (3, 1), "Midfielder": (3, 1),
    "Left Midfield": (3, 0), "Right Midfield": (3, 2), "Attacking Midfield": (3, 1),
    "Left Winger": (4, 0), "Right Winger": (4, 2), "Centre-Forward": (4, 1),
    "Second Striker": (4, 1), "Attack": (4, 1),
}


def band(pos):
    if not pos:
        return (3, 1)
    if pos in POS:
        return POS[pos]
    p = pos.lower()
    lat = 0 if "left" in p else (2 if "right" in p else 1)
    if "keeper" in p: return (1, 1)
    if "back" in p or "defend" in p: return (2, lat)
    if "midfield" in p: return (3, lat)
    return (4, lat)


def ratings_teams():
    r = json.load(open(RATINGS, encoding="utf-8"))
    out = {}
    for div, lg in (r.get("leagues") or {}).items():
        for name, t in (lg.get("teams") or {}).items():
            out["%s|%s" % (div, name)] = t.get("ko") or name
    return out


def club_map(divs, refresh=False):
    """우리 팀 이름 ↔ Transfermarkt 구단 id. 리그 페이지 1장씩이면 끝난다."""
    try:
        m = json.load(open(MAP, encoding="utf-8"))
    except Exception:
        m = {}
    ko = ratings_teams()
    for div in divs:
        if not refresh and any(k.startswith(div + "|") for k in m):
            continue
        ours = sorted(k.split("|", 1)[1] for k in ko if k.startswith(div + "|"))
        try:
            clubs = T.league_clubs(div)
        except Exception as e:
            print("  %s 리그 목록 실패: %s" % (div, e)); continue
        paired, left = assign(list(clubs), ours)
        for tm_name, (our, sc) in paired.items():
            cid, slug = clubs[tm_name]
            m["%s|%s" % (div, our)] = {"id": cid, "slug": slug, "tm": tm_name}
        print("  %s: %d팀 연결%s" % (div, len(paired),
              (" · 실패 " + ", ".join(left)) if left else ""))
    os.makedirs(T.CACHE, exist_ok=True)
    json.dump(m, open(MAP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return m


# 실제로 쓰이는 형태의 범위. 출전 시간만 보면 수비수가 5명씩 뽑혀 5-2-3 같은 게 나온다.
SHAPE = {2: (3, 5), 3: (3, 5), 4: (1, 3)}      # 줄 → (최소, 최대)
# 중원 최소를 3으로 둔 이유: 공격형 미드필더까지 중원으로 세면 2명짜리 중원은 사실상 안 나온다.
# 2를 허용하면 윙어가 최전방으로 밀려서 5-2-3 같은 형태가 과하게 뽑힌다.


def build_xi(sq, mins, out_ids):
    """출전 시간 상위 11명. 결장자는 빼고, 줄별 인원은 실제 쓰이는 범위 안에서 고른다."""
    by = {p["id"]: p for p in sq}
    pool = {2: [], 3: [], 4: []}
    gk = None
    for pid, v in sorted(mins.items(), key=lambda x: -x[1].get("min", 0)):
        mn = v.get("min", 0)
        if mn <= 0 or pid in out_ids or pid not in by:
            continue
        r = band(by[pid].get("pos"))[0]
        if r == 1:
            if gk is None:
                gk = pid
        else:
            pool[r].append((mn, pid))
    if gk is None or sum(len(v) for v in pool.values()) < 9:
        return None

    # 줄별 인원 (D, M, A) 를 다 훑어서 출전 시간 합이 가장 큰 조합을 고른다.
    # 경우의 수가 서른 개도 안 돼서 전부 세어보는 게 제일 깔끔하다.
    best = None
    for d in range(SHAPE[2][0], SHAPE[2][1] + 1):
        for m3 in range(SHAPE[3][0], SHAPE[3][1] + 1):
            a4 = 10 - d - m3
            if not (SHAPE[4][0] <= a4 <= SHAPE[4][1]):
                continue
            if len(pool[2]) < d or len(pool[3]) < m3 or len(pool[4]) < a4:
                continue
            tot = (sum(x[0] for x in pool[2][:d]) + sum(x[0] for x in pool[3][:m3])
                   + sum(x[0] for x in pool[4][:a4]))
            if best is None or tot > best[0]:
                best = (tot, d, m3, a4)
    if best is None:                      # 범위를 못 맞추면 그냥 상위 10명으로
        flat = sorted([x for v in pool.values() for x in v], reverse=True)[:10]
        chosen = {2: [], 3: [], 4: []}
        for mn, pid in flat:
            chosen[band(by[pid].get("pos"))[0]].append((mn, pid))
    else:
        _, d, m3, a4 = best
        chosen = {2: pool[2][:d], 3: pool[3][:m3], 4: pool[4][:a4]}

    mx = max((v.get("min", 0) for v in mins.values()), default=1) or 1
    xi = []
    for r in (1, 2, 3, 4):
        line = ([(mins.get(gk, {}).get("min", 0), gk)] if r == 1 else chosen.get(r, []))
        if not line:
            continue
        line = sorted(line, key=lambda x: (band(by[x[1]].get("pos"))[1], -x[0]))
        for c, (mn, pid) in enumerate(line, start=1):
            xi.append({"g": "%d:%d" % (r, c), "id": pid, "c": round(min(1.0, mn / mx), 2)})
    form = "-".join(str(len(chosen[r])) for r in (2, 3, 4) if chosen.get(r))
    return {"f": form, "n": max((v.get("app", 0) for v in mins.values()), default=0), "xi": xi}


def round_keys(m):
    try:
        d = json.load(open(IMPORT, encoding="utf-8"))
    except Exception:
        return []
    ks = []
    for g in d.get("matches", []):
        for s in ("home", "away"):
            k = "%s|%s" % (g.get("league"), g.get(s))
            if k in m and k not in ks:
                ks.append(k)
    return ks


def main():
    args = sys.argv[1:]
    ko = ratings_teams()
    divs = list(T.COMP)
    m = club_map(divs) if "--build" not in args else json.load(open(MAP, encoding="utf-8"))

    keys = list(m) if "--all" in args else (round_keys(m) or list(m))
    print("대상 팀 %d개%s" % (len(keys), " (이번 회차)" if "--all" not in args else ""))

    cache_f = os.path.join(T.CACHE, "_built.json")
    try:
        built = json.load(open(cache_f, encoding="utf-8"))
    except Exception:
        built = {}

    done = 0
    for k in keys:
        c = m[k]; div = k.split("|", 1)[0]
        if "--build" in args:
            continue
        try:
            sq = T.squad(c["id"], c["slug"])
            mins = T.minutes(c["id"], c["slug"], div)
            ab = T.absences(c["id"], c["slug"])
        except Exception as e:
            print("  %s: %s" % (k, str(e)[:70])); continue
        built[k] = {"sq": sq, "min": {str(a): b for a, b in mins.items()}, "ab": ab}
        done += 1
        if done % 10 == 0:
            json.dump(built, open(cache_f, "w", encoding="utf-8"), ensure_ascii=False)
            print("    … %d/%d" % (done, len(keys)), flush=True)
    if done:
        json.dump(built, open(cache_f, "w", encoding="utf-8"), ensure_ascii=False)

    teams, withxi = {}, 0
    for k, b in built.items():
        sq = b["sq"]; mins = {int(a): v for a, v in b["min"].items()}
        out_ids = {a["id"] for a in b["ab"]}
        xi = build_xi(sq, mins, out_ids)
        if xi:
            withxi += 1
        keep = {x["id"] for x in (xi["xi"] if xi else [])} | {a["id"] for a in b["ab"]}
        teams[k] = {"ko": ko.get(k), "sq": [p for p in sq if p["id"] in keep],
                    "inj": [{"id": a["id"], "n": a["n"], "t": a["t"], "r": a["r"],
                             "until": a["until"], "miss": a["miss"]} for a in b["ab"]],
                    "form": ({"mins": xi} if xi else {}), "nLu": xi["n"] if xi else 0}

    doc = {"asof": dt.date.today().isoformat(), "src": "Transfermarkt", "phFmt": None,
           "basis": "mins", "injAsof": dt.date.today().isoformat(),
           "cover": {"teams": len(teams), "xi": withxi}, "teams": teams}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(doc, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("  squads.json — 팀 %d개, 예상 선발 %d개, %.0fKB"
          % (len(teams), withxi, os.path.getsize(OUT) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
