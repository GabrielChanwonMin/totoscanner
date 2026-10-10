#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transfermarkt 읽기 — 부상·출전정지, 선수단, 출전 시간.

API-Football 무료 요금제가 이번 시즌을 막아서(2022~2024만 열림) 여기로 왔다.
transfermarkt.com/robots.txt 는 `User-agent: * / Allow: /` 로 전체 허용이다.
그래도 남의 서버라 페이지 사이에 간격을 두고, 받은 건 전부 캐시해서 두 번 안 받는다.

여기서만 얻는 것: **출전정지**. API-Football 은 부상만 준다.
"""
import contextlib, json, os, re, html, time, signal, urllib.request, urllib.error, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "tm_cache")
BASE = "https://www.transfermarkt.com/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
DELAY = 1.5          # 페이지 사이 간격 (초)
# 2.5초면 한 회차에 11분이 걸려서 멈춘 줄 안다. 1.5초여도 분당 40쪽이라
# 큰 사이트엔 부담이 아니다. robots.txt 가 우리 쪽에 Crawl-delay 를 걸지도 않았다.
COMP = {"E0": ("GB1", "premier-league"), "SP1": ("ES1", "laliga"),
        "I1": ("IT1", "serie-a"), "D1": ("L1", "bundesliga"), "F1": ("FR1", "ligue-1")}

_last = [0.0]
HARD = 25.0          # 요청 하나에 쓸 수 있는 전체 시간 (초)


class Hang(Exception):
    """서버가 연결만 잡아두고 응답을 안 줄 때."""


@contextlib.contextmanager
def _deadline(seconds):
    """urlopen 의 timeout 은 '읽기 한 번'에만 걸린다.

    서버가 몇 초마다 1바이트씩 흘려보내면 그 timeout 은 영원히 안 터진다 —
    실제로 그렇게 멈췄다(연결은 ESTABLISHED, 2분 넘게 진행 없음).
    그래서 요청 전체에 알람을 걸어 통째로 끊는다. DNS 가 늦어지는 경우도 같이 잡힌다.
    """
    try:
        def boom(sig, frm):
            raise Hang("응답 %g초 초과" % seconds)
        old = signal.signal(signal.SIGALRM, boom)
        signal.setitimer(signal.ITIMER_REAL, seconds)
    except ValueError:        # 메인 스레드가 아니면 알람을 못 건다
        yield
        return
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def season_now(today=None):
    d = today or dt.date.today()
    return d.year if d.month >= 7 else d.year - 1


def fetch(path, ttl_hours=24, label=None):
    """캐시에 신선한 게 있으면 그걸 쓰고, 없을 때만 받는다."""
    os.makedirs(CACHE, exist_ok=True)
    key = re.sub(r"[^A-Za-z0-9]+", "_", path)[:120] + ".html"
    fp = os.path.join(CACHE, key)
    if os.path.exists(fp):
        age = (time.time() - os.path.getmtime(fp)) / 3600.0
        if age < ttl_hours:
            return open(fp, encoding="utf-8").read()
    req = urllib.request.Request(BASE + path, headers={
        "User-Agent": UA, "Accept-Language": "en",
        "Accept": "text/html,application/xhtml+xml"})
    last = None
    for attempt in range(3):
        wait = DELAY - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            with _deadline(HARD):
                with urllib.request.urlopen(req, timeout=20) as r:
                    body = r.read().decode("utf-8", "replace")
            _last[0] = time.time()
            open(fp, "w", encoding="utf-8").write(body)
            return body
        except Exception as e:
            _last[0] = time.time()
            last = e
            if attempt < 2:
                time.sleep(3 * (attempt + 1))      # 조금 물러섰다 다시
    raise last


# ---------- 표 파싱 ----------
def _rows(page):
    """odd/even 행을 시작 위치로 잘라낸다. 중첩 <tr> 에 속지 않는 유일한 방법이다."""
    st = [m.start() for m in re.finditer(r'<tr class="(?:odd|even)">', page)]
    return [page[a:b] for a, b in zip(st, st[1:] + [len(page)])]


def _txt(x):
    return re.sub(r"\s+", " ", html.unescape(re.sub("<[^>]+>", " ", x or ""))).strip()


def _cells(row):
    flat = re.sub(r'<table class="inline-table".*?</table>', " ", row, flags=re.S)
    return [_txt(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", flat, re.S)]


def _pid(row):
    m = re.search(r"/profil/spieler/(\d+)", row)
    return int(m.group(1)) if m else None


def _name(row):
    """페이지마다 링크 모양이 다르다 — 결장자 표는 title 속성, 선수단 표는 링크 글자다."""
    m = re.search(r'<a title="([^"]+)"[^>]*href="/[^"]*/profil/spieler/', row)
    if m:
        return html.unescape(m.group(1))
    m = re.search(r'<a href="/[^"]*/profil/spieler/\d+"[^>]*>(.*?)</a>', row, re.S)
    if m:
        t = _txt(m.group(1))
        if t:
            return t
    inner = re.search(r'<table class="inline-table".*?</table>', row, re.S)
    if inner:
        parts = [_txt(t) for t in re.findall(r"<td[^>]*>(.*?)</td>", inner.group(0), re.S)]
        parts = [x for x in parts if x]
        if parts:
            return parts[0]
    return None


def _photo(row):
    m = re.search(r'(?:data-)?src="(https://img\.a\.transfermarkt\.technology/portrait/[^"]+)"', row)
    return m.group(1) if m else None


def _detail_pos(row):
    """이름 바로 아래 줄에 세부 포지션이 온다 (Centre-Back, Left Winger …)."""
    inner = re.search(r'<table class="inline-table".*?</table>', row, re.S)
    if not inner:
        return None
    parts = [_txt(t) for t in re.findall(r"<td[^>]*>(.*?)</td>", inner.group(0), re.S)]
    parts = [p for p in parts if p]
    return parts[-1] if len(parts) >= 2 else None


# ---------- 공개 함수 ----------
def league_clubs(div, season=None):
    """리그 페이지 1장 → {구단명: (id, slug)}."""
    code, slug = COMP[div]
    season = season or season_now()
    page = fetch("%s/startseite/wettbewerb/%s/plus/?saison_id=%d" % (slug, code, season),
                 ttl_hours=24 * 14)
    out = {}
    for m in re.finditer(r'<a\s+title="([^"]+)"\s+href="/([a-z0-9\-]+)/startseite/verein/(\d+)', page):
        nm = html.unescape(m.group(1))
        out.setdefault(nm, (int(m.group(3)), m.group(2)))
    return out


def absences(club_id, slug, ttl_hours=6):
    """부상 + 출전정지. 이게 제일 빨리 낡는 정보라 짧게 잡는다."""
    page = fetch("%s/sperrenundverletzungen/verein/%d" % (slug, club_id), ttl_hours=ttl_hours)
    out = []
    for r in _rows(page):
        pid, nm = _pid(r), _name(r)
        if not pid:
            continue
        c = _cells(r)
        # [나이, 사유, 시작일, 복귀예정, 결장경기수] 순으로 온다 (선수 칸은 걷어냈다)
        vals = [x for x in c if x]
        reason = vals[1] if len(vals) > 1 else ""
        out.append({"id": pid, "n": nm, "r": reason,
                    "since": vals[2] if len(vals) > 2 else "",
                    "until": vals[3] if len(vals) > 3 else "",
                    "miss": vals[4] if len(vals) > 4 else "",
                    "ph": _photo(r),
                    "t": "SUSP" if re.search(r"suspend|ban|card", reason, re.I) else "INJ"})
    return out


def squad(club_id, slug, season=None, ttl_hours=24 * 21):
    """선수단 — 등번호, 세부 포지션, 사진. 이적시장 열릴 때 말고는 안 바뀌어서 3주 캐시."""
    season = season or season_now()
    page = fetch("%s/kader/verein/%d/saison_id/%d/plus/1" % (slug, club_id, season),
                 ttl_hours=ttl_hours)
    out = []
    for r in _rows(page):
        pid = _pid(r)
        if not pid:
            continue
        num = re.search(r"<div class=rn_nummer>(.*?)</div>", r)
        out.append({"id": pid, "n": _name(r), "num": _txt(num.group(1)) if num else "",
                    "pos": _detail_pos(r), "ph": _photo(r)})
    return out


def minutes(club_id, slug, div, season=None, ttl_hours=20):
    """이번 시즌 리그 출전 시간. 마지막 칸이 분(') 이다."""
    season = season or season_now()
    code = COMP[div][0]
    page = fetch("%s/leistungsdaten/verein/%d/reldata/%s%%26%d/plus/1"
                 % (slug, club_id, code, season), ttl_hours=ttl_hours)
    out = {}
    for r in _rows(page):
        pid = _pid(r)
        if not pid:
            continue
        c = _cells(r)
        mins = 0
        if c:
            m = re.match(r"([\d.']+)", c[-1].replace(",", "").replace(".", ""))
            if m:
                mins = int(re.sub(r"\D", "", m.group(1)) or 0)
        # 칸 순서: [등번호, , 나이, , 스쿼드포함, 출전, …, 평점, 출전시간]
        # 앞에서부터 첫 숫자를 집으면 등번호를 출전수로 착각한다.
        apps = 0
        if len(c) > 5 and c[5].isdigit():
            apps = int(c[5])
        out[pid] = {"min": mins, "app": apps}
    return out
