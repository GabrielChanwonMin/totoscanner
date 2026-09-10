"""Dixon-Coles (기획서 6.3.1) 순수 파이썬 구현 + 배당 수학 (6.2.1)."""
import csv, glob, math, os, datetime as dt

SP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(SP, "data")
LEAGUES = {"E0": "EPL", "SP1": "라리가", "I1": "세리에A", "D1": "분데스리가", "F1": "리그1"}
MAXG = 10

# ---------- 데이터 로딩 ----------
def _f(row, key):
    v = (row.get(key) or "").strip()
    try:
        x = float(v)
        return x if x > 1.0 else None
    except ValueError:
        return None

def load():
    ms = []
    for path in sorted(glob.glob(os.path.join(DATA, "*.csv"))):
        base = os.path.basename(path)[:-4]
        season, div = base.split("_")
        for row in csv.DictReader(open(path, encoding="utf-8-sig")):
            if not row.get("HomeTeam") or not row.get("Date"):
                continue
            try:
                hg, ag = int(row["FTHG"]), int(row["FTAG"])
            except (ValueError, KeyError, TypeError):
                continue
            d = row["Date"].strip()
            fmt = "%d/%m/%Y" if len(d) == 10 else "%d/%m/%y"
            try:
                date = dt.datetime.strptime(d, fmt).date()
            except ValueError:
                continue
            # 클로징 배당: Pinnacle 우선, 없으면 시장 평균
            c = [_f(row, "PSCH"), _f(row, "PSCD"), _f(row, "PSCA")]
            if None in c:
                c = [_f(row, "AvgCH"), _f(row, "AvgCD"), _f(row, "AvgCA")]
            if None in c:
                c = [_f(row, "AvgH"), _f(row, "AvgD"), _f(row, "AvgA")]
            o = [_f(row,"PSH"), _f(row,"PSD"), _f(row,"PSA")]
            if None in o:
                o = [_f(row,"AvgH"), _f(row,"AvgD"), _f(row,"AvgA")]
            ms.append(dict(div=div, season=season, date=date, open=None if None in o else o,
                           home=row["HomeTeam"].strip(), away=row["AwayTeam"].strip(),
                           hg=hg, ag=ag, close=None if None in c else c))
    ms.sort(key=lambda m: m["date"])
    return ms

# ---------- 배당 수학 (6.2.1) ----------
def devig_power(odds):
    """파워법 마진 제거. p_i = implied_i^k, sum = 1 이 되도록 k 이분탐색."""
    imp = [1.0 / o for o in odds]
    lo, hi = 0.3, 3.0
    for _ in range(80):
        k = (lo + hi) / 2
        s = sum(i ** k for i in imp)
        if s > 1.0:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    p = [i ** k for i in imp]
    s = sum(p)
    return [x / s for x in p]

def devig_prop(odds):
    imp = [1.0 / o for o in odds]
    s = sum(imp)
    return [i / s for i in imp]

def devig_shin(odds):
    """Shin(1993) 내부자 비율 z 추정."""
    imp = [1.0 / o for o in odds]
    s = sum(imp)
    lo, hi = 0.0, 0.4
    for _ in range(80):
        z = (lo + hi) / 2
        p = [(math.sqrt(z * z + 4 * (1 - z) * (i * i) / s) - z) / (2 * (1 - z)) for i in imp]
        if sum(p) > 1.0:
            lo = z
        else:
            hi = z
    z = (lo + hi) / 2
    p = [(math.sqrt(z * z + 4 * (1 - z) * (i * i) / s) - z) / (2 * (1 - z)) for i in imp]
    t = sum(p)
    return [x / t for x in p]

def log_pool(dists, weights):
    """로그-선형 풀링 (6.2.2)."""
    n = len(dists[0])
    out = []
    for i in range(n):
        acc = 0.0
        for d, w in zip(dists, weights):
            acc += w * math.log(max(d[i], 1e-12))
        out.append(math.exp(acc))
    s = sum(out)
    return [x / s for x in out]

# ---------- Dixon-Coles ----------
def tau(h, a, lam, nu, rho):
    if h == 0 and a == 0: return 1.0 - lam * nu * rho
    if h == 0 and a == 1: return 1.0 + lam * rho
    if h == 1 and a == 0: return 1.0 + nu * rho
    if h == 1 and a == 1: return 1.0 - rho
    return 1.0

def dtau(h, a, lam, nu, rho):
    """(∂τ/∂λ, ∂τ/∂ν, ∂τ/∂ρ)"""
    if h == 0 and a == 0: return (-nu * rho, -lam * rho, -lam * nu)
    if h == 0 and a == 1: return (rho, 0.0, lam)
    if h == 1 and a == 0: return (0.0, rho, nu)
    if h == 1 and a == 1: return (0.0, 0.0, -1.0)
    return (0.0, 0.0, 0.0)

class Fit:
    __slots__ = ("teams", "idx", "att", "df", "mu", "gamma", "rho", "anew", "dnew", "new", "n")

def fit_dc(matches, asof, xi=0.0022, kappa=6.0, iters=350, warm=None, new_cut=12):
    """시간가중 최우도 추정. matches는 asof 이전 경기만 들어온다고 가정."""
    teams = sorted({m["home"] for m in matches} | {m["away"] for m in matches})
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    cnt = [0.0] * n
    for m in matches:
        w = math.exp(-xi * (asof - m["date"]).days)
        cnt[idx[m["home"]]] += w; cnt[idx[m["away"]]] += w
    new = [1.0 if c < new_cut else 0.0 for c in cnt]

    att = [0.0] * n; df = [0.0] * n
    mu, gamma, rho_raw, anew, dnew = 0.05, 0.25, 0.0, 0.0, 0.0
    if warm:
        for t, i in idx.items():
            if t in warm.idx:
                j = warm.idx[t]; att[i] = warm.att[j]; df[i] = warm.df[j]
        mu, gamma, anew, dnew = warm.mu, warm.gamma, warm.anew, warm.dnew
        rho_raw = math.atanh(max(-0.9, min(0.9, warm.rho)))
        iters = max(90, iters // 4)

    rows = []
    for m in matches:
        w = math.exp(-xi * (asof - m["date"]).days)
        if w < 1e-4: continue
        rows.append((idx[m["home"]], idx[m["away"]], m["hg"], m["ag"], w))
    if not rows: return None

    # Adam
    P = 5 + 2 * n
    mom = [0.0] * P; vel = [0.0] * P
    b1, b2, eps, lr = 0.9, 0.999, 1e-8, 0.06
    for it in range(1, iters + 1):
        rho = math.tanh(rho_raw) * 0.25
        g_mu = g_gm = g_rho = 0.0
        g_att = [0.0] * n; g_df = [0.0] * n
        for hi, ai, h, a, w in rows:
            lam = math.exp(mu + gamma + att[hi] - df[ai])
            nu = math.exp(mu + att[ai] - df[hi])
            if h <= 1 and a <= 1:
                t = tau(h, a, lam, nu, rho)
                if t < 1e-6: t = 1e-6
                dl, dn, dr = dtau(h, a, lam, nu, rho)
                gl = (h - lam) + lam * dl / t
                gn = (a - nu) + nu * dn / t
                g_rho += w * dr / t
            else:
                gl = h - lam; gn = a - nu
            gl *= w; gn *= w
            g_mu += gl + gn; g_gm += gl
            g_att[hi] += gl; g_att[ai] += gn
            g_df[ai] -= gl; g_df[hi] -= gn
        # 릿지 (신규 승격팀은 anew/dnew 쪽으로 수축)
        g_an = g_dn = 0.0
        for i in range(n):
            ca = anew * new[i]; cd = dnew * new[i]
            g_att[i] -= kappa * (att[i] - ca)
            g_df[i] -= kappa * (df[i] - cd)
            if new[i]:
                g_an += kappa * (att[i] - ca); g_dn += kappa * (df[i] - cd)
        g_an -= 2.0 * anew; g_dn -= 2.0 * dnew
        g_rho -= 4.0 * rho_raw
        g_rho *= (1 - math.tanh(rho_raw) ** 2) * 0.25

        grads = [g_mu, g_gm, g_rho, g_an, g_dn] + g_att + g_df
        params = [mu, gamma, rho_raw, anew, dnew] + att + df
        for i in range(P):
            mom[i] = b1 * mom[i] + (1 - b1) * grads[i]
            vel[i] = b2 * vel[i] + (1 - b2) * grads[i] * grads[i]
            mh = mom[i] / (1 - b1 ** it); vh = vel[i] / (1 - b2 ** it)
            params[i] += lr * mh / (math.sqrt(vh) + eps)
        mu, gamma, rho_raw, anew, dnew = params[:5]
        att = params[5:5 + n]; df = params[5 + n:]
        ma = sum(att) / n; md = sum(df) / n
        att = [x - ma for x in att]; df = [x - md for x in df]
        mu += ma - md

    f = Fit()
    f.teams, f.idx, f.att, f.df = teams, idx, att, df
    f.mu, f.gamma, f.rho, f.anew, f.dnew, f.new, f.n = mu, gamma, math.tanh(rho_raw) * 0.25, anew, dnew, new, n
    return f

_LOGFACT = [0.0] * (MAXG + 2)
for _i in range(2, MAXG + 2):
    _LOGFACT[_i] = _LOGFACT[_i - 1] + math.log(_i)

def score_matrix(lam, nu, rho, maxg=MAXG):
    ph = [math.exp(-lam + h * math.log(lam) - _LOGFACT[h]) for h in range(maxg + 1)]
    pa = [math.exp(-nu + a * math.log(nu) - _LOGFACT[a]) for a in range(maxg + 1)]
    M = [[ph[h] * pa[a] for a in range(maxg + 1)] for h in range(maxg + 1)]
    M[0][0] *= 1 - lam * nu * rho
    M[0][1] *= 1 + lam * rho
    M[1][0] *= 1 + nu * rho
    M[1][1] *= 1 - rho
    s = sum(sum(r) for r in M)
    return [[x / s for x in r] for r in M]

def lambdas(f, home, away):
    if home not in f.idx or away not in f.idx: return None
    hi, ai = f.idx[home], f.idx[away]
    lam = math.exp(f.mu + f.gamma + f.att[hi] - f.df[ai])
    nu = math.exp(f.mu + f.att[ai] - f.df[hi])
    return lam, nu

def probs_1x2(M):
    H = D = A = 0.0
    for h, row in enumerate(M):
        for a, p in enumerate(row):
            if h > a: H += p
            elif h == a: D += p
            else: A += p
    return [H, D, A]
