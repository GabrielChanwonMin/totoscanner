#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""팀명 매칭 엔진 (기획서 §7).

베트맨은 정식 클럽명을 쓴다 (AFC본머스, VfB슈투트가르트, 토트넘 홋스퍼…).
1) 클럽 접두/접미어와 창단연도 숫자를 제거해 정규화
2) 양방향 부분일치 → 3) 초성/편집거리 폴백
4) 확정된 매칭은 betman 팀ID 기준으로 team_aliases.json에 저장 (한 번 확정하면 영구 재사용)
"""
import json, os, re, difflib

HERE = os.path.dirname(os.path.abspath(__file__))
ALIAS_PATH = os.path.join(HERE, "team_aliases.json")
RATINGS = os.path.join(os.path.dirname(HERE), "engine", "ratings.json")

# 클럽 형태 접두어·접미어 (긴 것부터)
AFFIX = ["ACF","RCD","SSC","AFC","OGC","OSC","SCO","TSG","VfB","VfL","FSV","CFC","TSV","BSC",
         "UD","SD","CD","CF","SS","US","AC","AJ","AS","BC","RC","SC","FC","SV","VV"]
# 흔한 수식어 (제거해도 팀이 특정됨)
NOISE = ["홋스퍼","앨비언","&호브","호브","타운","시티","클럽","올랭피크","올랭피크드",
         "스타드","레알소시에다드" and "", "데포르티보"]

def norm(s):
    if not s: return ""
    s = s.strip()
    s = re.sub(r"\d{2,4}\b", "", s)                 # 창단연도: 마인츠05, 1899 호펜하임
    for a in AFFIX:                                  # 접두/접미 클럽형태 (릴OSC, 앙제SCO 처럼 뒤에 붙는 경우 포함)
        s = re.sub(r"%s(?![a-z])" % re.escape(a), "", s)
    s = re.sub(r"[\s·.'’&\-]+", "", s)
    return s.lower()

def strip_noise(s):
    for n in NOISE:
        if n and n in s and len(s.replace(n,"")) >= 1:
            s = s.replace(n,"")
    return s

def build_index(ratings):
    idx = {}
    for lg, L in ratings["leagues"].items():
        for en, v in L["teams"].items():
            idx.setdefault(lg, []).append((en, v["ko"], norm(v["ko"]), norm(en)))
    return idx

def match(league, betman_ko, idx):
    """→ (영문키, 방식, 점수) 또는 (None, 이유, 0)"""
    cands = idx.get(league) or []
    b = norm(betman_ko); bs = strip_noise(b)
    for form in (b, bs):
        for en, ko, nko, nen in cands:                       # 1) 완전일치
            if form and form in (nko, nen): return en, "exact", 1.0
    for form in (b, bs):                                     # 2) 양방향 부분일치
        best = None
        for en, ko, nko, nen in cands:
            if not form or not nko: continue
            if form in nko or nko in form:
                score = min(len(form), len(nko)) / max(len(form), len(nko))
                if len(min(form, nko, key=len)) >= 2 and (best is None or score > best[2]):
                    best = (en, "substr", score)
        if best and best[2] >= 0.45: return best
    names = [c[2] for c in cands]                            # 3) 편집거리 폴백
    for form in (b, bs):
        m = difflib.get_close_matches(form, names, n=1, cutoff=0.62)
        if m:
            en = next(c[0] for c in cands if c[2] == m[0])
            return en, "fuzzy", difflib.SequenceMatcher(None, form, m[0]).ratio()
    return None, "unmatched", 0.0

def load_aliases():
    if os.path.exists(ALIAS_PATH):
        return json.load(open(ALIAS_PATH, encoding="utf-8"))
    return {}

def save_aliases(a):
    json.dump(a, open(ALIAS_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)

def resolve(matches, ratings=None, verbose=True):
    """수집한 경기 리스트에 영문 팀키를 붙인다. 확정 매칭은 팀ID로 캐시."""
    ratings = ratings or json.load(open(RATINGS, encoding="utf-8"))
    idx = build_index(ratings); alias = load_aliases()
    stats = {"cached":0,"exact":0,"substr":0,"fuzzy":0,"unmatched":0}
    unresolved = []
    for m in matches:
        for side in ("home","away"):
            tid = m.get(side + "Id"); ko = m[side]
            key = "%s|%s" % (m["league"], tid or ko)
            if key in alias:
                m[side + "En"] = alias[key]; stats["cached"] += 1; continue
            en, how, sc = match(m["league"], ko, idx)
            m[side + "En"] = en
            stats[how if how in stats else "unmatched"] += 1
            if en:
                alias[key] = en
                alias.setdefault("_labels", {})[key] = ko
            else:
                unresolved.append((m["league"], ko, tid))
    save_aliases(alias)
    if verbose:
        print("  팀 매칭:", ", ".join("%s %d" % (k,v) for k,v in stats.items() if v))
        if unresolved:
            print("  ⚠ 미매칭 %d건 — team_aliases.json에 직접 넣어라:" % len(unresolved))
            for lg, ko, tid in sorted(set(unresolved))[:12]:
                print('     "%s|%s": "영문팀키",   // %s' % (lg, tid or ko, ko))
    return matches, unresolved
