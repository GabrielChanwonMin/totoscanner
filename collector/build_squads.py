#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""캐시 → docs/data/squads.json.

핵심은 '상대가 나보다 센 팀이냐 약한 팀이냐'로 그 팀의 라인업 이력을 나눠 보는 것이다.
같은 팀도 강팀 상대로는 수비적으로, 약팀 상대로는 공격적으로 내는 경우가 많아서
이번 상대가 어느 쪽인지에 맞춰 뽑아야 예상 라인업이 맞는다.
"""
import json, os, math, datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RATINGS = os.path.join(ROOT, "engine", "ratings.json")

HALFLIFE = 210.0      # 라인업 최신성 반감기 (하루 단위) — 7개월이면 절반 무게


def strengths():
    """팀 키 → (세기, 한국어 이름)."""
    try:
        r = json.load(open(RATINGS, encoding="utf-8"))
    except Exception:
        return {}, {}
    st, ko = {}, {}
    for div, lg in (r.get("leagues") or {}).items():
        for name, t in (lg.get("teams") or {}).items():
            k = "%s|%s" % (div, name)
            st[k] = (t.get("att") or 0.0) + (t.get("def") or 0.0)
            ko[k] = t.get("ko") or name
    return st, ko


def cuts_for(oppstr):
    """그 팀이 실제로 만난 상대들을 세기 순으로 줄 세워 3등분한 경계.

    '강팀/약팀'을 리그 전체 기준 고정선으로 자르면 아스널한테는 모두가 약팀이 되고
    승격팀한테는 모두가 강팀이 돼서 구분이 사라진다. 그래서 각 팀이 만난 상대들
    안에서 상대적으로 나눈다 — 아스널의 '강팀'은 맨시티·리버풀 쪽이 된다.
    """
    v = sorted(x for x in oppstr if x is not None)
    if len(v) < 6:
        return None
    lo = v[int(len(v) * 0.34)]
    hi = v[int(len(v) * 0.66)]
    if hi - lo < 0.06:          # 만난 상대들이 다 고만고만하면 나눌 의미가 없다
        return None
    return [round(lo, 4), round(hi, 4)]


def tier(cuts, opp):
    """상대 하나를 그 경계에 대고 분류."""
    if not cuts or opp is None:
        return "all"
    return "strong" if opp >= cuts[1] else ("weak" if opp <= cuts[0] else "even")


def _w(datestr, today):
    try:
        d = dt.date.fromisoformat(datestr)
    except Exception:
        return 0.3
    return 0.5 ** (max(0, (today - d).days) / HALFLIFE)


def _slot(grid, pos):
    """grid 는 '행:열'. 없으면 포지션 글자로 대충 줄을 잡는다."""
    if grid and ":" in grid:
        return grid
    return {"G": "1:1", "D": "2:1", "M": "3:1", "F": "4:1"}.get(pos or "", "3:1")


def expected_xi(hist, injured, squad_ids):
    """한 티어의 라인업 이력 → (포메이션, 11자리, 각 자리의 선수와 확신도).

    자리별로 '그 자리에 제일 자주 선 선수'를 뽑되, 부상자면 다음 사람으로 내린다.
    """
    if not hist:
        return None
    fvote, slotvote, minutes = {}, {}, {}
    for h in hist:
        w = h["w"]
        if h["f"]:
            fvote[h["f"]] = fvote.get(h["f"], 0.0) + w
        for pid, grid, pos in h["xi"]:
            s = _slot(grid, pos)
            bucket = slotvote.setdefault(s, {})   # 한 줄로 쓰면 오른쪽이 먼저 평가돼서 터진다
            bucket[pid] = bucket.get(pid, 0.0) + w
            minutes[pid] = minutes.get(pid, 0.0) + w
    if not slotvote:
        return None
    form = max(fvote.items(), key=lambda x: x[1])[0] if fvote else ""
    # 가장 표가 많은 자리 11개
    slots = sorted(slotvote.items(), key=lambda x: -sum(x[1].values()))[:11]
    taken, xi = set(), []
    for s, votes in sorted(slots, key=lambda x: x[0]):
        tot = sum(votes.values()) or 1.0
        rank = sorted(votes.items(), key=lambda x: -x[1])
        pick = None
        for pid, v in rank:
            if pid in taken:
                continue
            if pid in injured:
                continue
            if squad_ids and pid not in squad_ids:   # 이적한 선수는 뺀다
                continue
            pick = (pid, v / tot); break
        if pick is None:
            for pid, v in rank:
                if pid not in taken:
                    pick = (pid, v / tot); break
        if pick is None:
            continue
        taken.add(pick[0])
        xi.append({"g": s, "id": pick[0], "c": round(pick[1], 2)})
    if len(xi) < 8:
        return None
    return {"f": form, "n": len(hist), "xi": xi}


def build(tm, squads, inj, fx, lu, out_path):
    st, ko = strengths()
    rev = tm.get("rev", {})            # api team id → "DIV|Name"
    tmap = tm.get("map", {})
    today = dt.date.today()

    # 팀별 라인업 이력 모으기
    hist = {}                          # 팀키 → [{f, xi, w, tier}]
    for fid, blk in lu.items():
        if fid.startswith("_"):
            continue
        sides = blk.get("s") or []
        if len(sides) < 2:
            continue
        w = _w(blk.get("d", ""), today)
        if w < 0.02:
            continue
        for i, side in enumerate(sides):
            me, you = side.get("t"), sides[1 - i].get("t")
            mk, yk = rev.get(str(me)), rev.get(str(you))
            if not mk:
                continue
            hist.setdefault(mk, []).append({
                "f": side.get("f") or "", "xi": side.get("xi") or [], "w": w,
                "os": st.get(yk) if yk else None})

    teams = {}
    for k, tid in tmap.items():
        sq = squads.get(k) or []
        sq_ids = {p["id"] for p in sq if p.get("id")}
        injured = {}
        for pid, v in (inj.get(str(tid)) or {}).items():
            try:
                injured[int(pid)] = v
            except ValueError:
                pass
        h = hist.get(k, [])
        cuts = cuts_for([x["os"] for x in h])
        forms = {}
        if cuts:
            for t in ("strong", "even", "weak"):
                sub = [x for x in h if tier(cuts, x["os"]) == t]
                r = expected_xi(sub, set(injured), sq_ids) if len(sub) >= 4 else None
                if r:                       # 4경기도 안 되는 칸은 만들지 않는다
                    forms[t] = r
        allr = expected_xi(h, set(injured), sq_ids)
        if allr:
            forms["all"] = allr
        if not sq and not forms and not injured:
            continue
        teams[k] = {"id": tid, "ko": ko.get(k), "str": round(st.get(k), 4) if st.get(k) is not None else None,
                    "cuts": cuts,
                    "sq": [p for p in sq if p.get("id")],
                    "inj": [{"id": int(pid), **v} for pid, v in injured.items()],
                    "form": forms, "nLu": len(h)}

    # 사진 주소는 대부분 '접두사 + 선수id + .png' 꼴이라, 틀만 남기고 지운다.
    # 96팀 x 24명 분량이면 이것만으로 파일이 절반 가까이 준다 (매 실행마다 커밋되는 파일이다).
    pre = suf = None
    for t in teams.values():
        for pl in t["sq"]:
            u = pl.get("ph") or ""
            k = str(pl["id"])
            i = u.rfind(k)
            if i <= 0:
                continue
            a, b2 = u[:i], u[i + len(k):]
            if pre is None:
                pre, suf = a, b2
            elif (a, b2) != (pre, suf):
                pre = suf = None
                break
        if pre is None:
            break
    phfmt = None
    if pre:
        phfmt = [pre, suf]
        for t in teams.values():
            for pl in t["sq"]:
                if pl.get("ph") == pre + str(pl["id"]) + suf:
                    pl.pop("ph", None)          # 틀로 되살릴 수 있으면 안 들고 간다

    total_fx = sum(len(b.get("rows", [])) for kk, b in fx.items() if not kk.startswith("_"))
    doc = {"asof": today.isoformat(), "src": "API-Football", "phFmt": phfmt,
           "cover": {"fixtures": total_fx, "lineups": len([k for k in lu if not k.startswith("_")]),
                     "teams": len(teams), "squads": len(squads)},
           "injAsof": (inj.get("_asof") or ""),
           "teams": teams}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(doc, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    kb = os.path.getsize(out_path) / 1024.0
    withxi = sum(1 for t in teams.values() if t["form"])
    print("  squads.json — 팀 %d개(라인업 있는 팀 %d개), %.0fKB"
          % (len(teams), withxi, kb))
    return doc
