#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""API-Football(v3) 얇은 클라이언트 — 하루 호출량을 지켜가며 캐시에 쌓는다.

무료 요금제가 하루 100회다. 라인업은 경기 하나당 1회라 5대 리그 두 시즌이면 3천 회가 넘는다.
그래서 한 번에 다 받지 않고, 날마다 예산만큼만 받아서 디스크에 쌓아두는 구조로 간다.
같은 것을 두 번 받지 않으니 하루만 기다리면 그만큼 쌓인다.

키는 secrets.json 의 "footballApiKey" 에 넣는다 (dashboard.api-football.com 무료 가입).
"""
import json, os, time, datetime as dt, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
SEC = os.path.join(HERE, "secrets.json")
CACHE = os.path.join(HERE, "squad_cache")
BUDGET = os.path.join(CACHE, "_budget.json")

HOST = "https://v3.football.api-sports.io"
LEAGUE_ID = {"E0": 39, "SP1": 140, "I1": 135, "D1": 78, "F1": 61}
ID_LEAGUE = {v: k for k, v in LEAGUE_ID.items()}

DAILY_DEFAULT = 90          # 무료 100회 중 10회는 여유분으로 남긴다


class Budget(Exception):
    """오늘 몫을 다 썼다. 에러가 아니라 정상적인 멈춤이다."""


def key():
    try:
        return (json.load(open(SEC, encoding="utf-8")).get("footballApiKey") or "").strip()
    except Exception:
        return ""


def _budget_state():
    today = dt.date.today().isoformat()
    try:
        b = json.load(open(BUDGET, encoding="utf-8"))
    except Exception:
        b = {}
    if b.get("date") != today:
        b = {"date": today, "used": 0, "remaining": None}
    return b


def _budget_save(b):
    os.makedirs(CACHE, exist_ok=True)
    json.dump(b, open(BUDGET, "w", encoding="utf-8"))


def used_today():
    return _budget_state().get("used", 0)


class Client:
    def __init__(self, daily=DAILY_DEFAULT, verbose=True):
        self.k = key()
        self.daily = daily
        self.verbose = verbose
        self.b = _budget_state()

    @property
    def left(self):
        return max(0, self.daily - self.b.get("used", 0))

    def get(self, path, **params):
        """한 번 호출. 예산을 넘으면 Budget 을 올린다."""
        if not self.k:
            raise RuntimeError("footballApiKey 가 secrets.json 에 없다")
        if self.left <= 0:
            raise Budget("오늘 %d회를 다 썼다" % self.daily)
        q = "&".join("%s=%s" % (a, b) for a, b in sorted(params.items()) if b is not None)
        url = "%s/%s%s" % (HOST, path, ("?" + q) if q else "")
        req = urllib.request.Request(url, headers={"x-apisports-key": self.k,
                                                   "Accept": "application/json"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=25) as r:
                    raw = json.loads(r.read().decode("utf-8"))
                    rem = r.headers.get("x-ratelimit-requests-remaining")
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:      # 분당 제한 — 잠깐 쉬었다 다시
                    time.sleep(7); continue
                raise
            except urllib.error.URLError:
                if attempt < 2:
                    time.sleep(3); continue
                raise
        self.b["used"] = self.b.get("used", 0) + 1
        if rem is not None:
            try:
                self.b["remaining"] = int(rem)
            except ValueError:
                pass
        _budget_save(self.b)

        errs = raw.get("errors")
        # errors 는 빈 리스트이거나, 문제가 있으면 dict 로 온다
        if isinstance(errs, dict) and errs:
            msg = "; ".join("%s: %s" % kv for kv in errs.items())
            raise RuntimeError("API-Football: " + msg)
        return raw.get("response", [])

    def paged(self, path, **params):
        """paging 이 있는 엔드포인트를 끝까지. 페이지마다 1회씩 먹는다."""
        out, page, total = [], 1, 1
        while page <= total:
            if self.left <= 0:
                raise Budget("페이지 도중 예산 소진")
            p = dict(params); p["page"] = page
            # paged 는 raw 가 필요해서 get 을 쓰지 않고 직접 처리
            resp = self.get(path, **p)
            out.extend(resp)
            # 대부분의 엔드포인트가 1페이지로 끝난다. 안전하게 100개 미만이면 종료
            if len(resp) < 20:
                break
            page += 1
            if page > 6:
                break
        return out


# ---------- 캐시 ----------
def cpath(*parts):
    p = os.path.join(CACHE, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def cload(*parts):
    try:
        return json.load(open(cpath(*parts), encoding="utf-8"))
    except Exception:
        return None


def csave(obj, *parts):
    json.dump(obj, open(cpath(*parts), "w", encoding="utf-8"), ensure_ascii=False)


def season_now(today=None):
    """유럽 시즌 표기 — 8월부터 새 시즌."""
    d = today or dt.date.today()
    return d.year if d.month >= 7 else d.year - 1
