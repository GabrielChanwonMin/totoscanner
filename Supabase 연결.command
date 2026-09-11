#!/bin/bash
# Supabase 키를 물어보고 설정 파일 두 개를 대신 만들어준다.
cd "$(dirname "$0")" || exit 1

printf '\033[1mSupabase 연결\033[0m\n'
printf '─────────────────────────────────────────\n'
printf 'Supabase 대시보드에서 세 개를 복사해 온다. 붙여넣고 Enter.\n'
printf '  · Project URL  → Settings › \033[1mData API\033[0m 맨 위\n'
printf '  · 키 두 개      → Settings › \033[1mAPI Keys\033[0m › \033[1mLegacy anon, service_role\033[0m 탭\n'
printf '취소하려면 Control+C.\n\n'

printf '\033[1m1) Project URL\033[0m (https://...supabase.co)\n> '
read -r SB_URL
# 앞뒤 공백 제거
SB_URL="$(printf '%s' "$SB_URL" | tr -d '[:space:]')"
# Data API 페이지는 .../rest/v1/ 까지 붙여서 보여준다 → 뒷부분을 잘라낸다
SB_URL="$(printf '%s' "$SB_URL" | sed -E 's#(https://[A-Za-z0-9-]+\.supabase\.co).*#\1#')"
# 대시보드 주소를 붙여넣은 경우도 살려준다
case "$SB_URL" in
  *supabase.com/dashboard/project/*)
    REF="$(printf '%s' "$SB_URL" | sed -E 's#.*/project/([A-Za-z0-9]+).*#\1#')"
    SB_URL="https://$REF.supabase.co" ;;
esac
case "$SB_URL" in
  https://*.supabase.co) printf '   → %s\n' "$SB_URL" ;;
  *) printf '\n\033[31m주소를 알아보지 못했다.\033[0m 받은 값: %s\n' "$SB_URL"
     printf '  https://무언가.supabase.co 형태여야 한다.\n'; exit 1;;
esac

printf '\n\033[1m2) anon 키\033[0m (Legacy 탭 · 웹페이지에 들어간다)\n> '
read -r SB_ANON
printf '\n\033[1m3) service_role 키\033[0m (Legacy 탭 · 저장소에 안 올라간다)\n> '
read -r SB_SVC

for K in "$SB_ANON" "$SB_SVC"; do
  if [ ${#K} -lt 30 ]; then
    printf '\n\033[31m키가 너무 짧다.\033[0m 통째로 복사했는지 확인해라.\n'; exit 1
  fi
done
if [ "$SB_ANON" = "$SB_SVC" ]; then
  printf '\n\033[31m두 키가 같다.\033[0m 공개용 키와 비밀 키는 서로 다른 값이다.\n'; exit 1
fi

# ── 실제로 통하는지 확인한다 (여기서 걸러야 나중에 헤매지 않는다) ──
printf '\n확인 중…\n'
CHK=$(/usr/bin/python3 - "$SB_URL" "$SB_ANON" "$SB_SVC" <<'PY'
import json, sys, urllib.request, urllib.error
url, anon, svc = sys.argv[1], sys.argv[2], sys.argv[3]

def probe(key, table):
    req = urllib.request.Request(f"{url}/rest/v1/{table}?select=*&limit=1")
    req.add_header("apikey", key); req.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read(200).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(300).decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)

problems = []
c, body = probe(anon, "profiles")
if c == 0:
    problems.append("URL_BAD:" + body[:80])
elif c == 401 or "Invalid API key" in body or "JWSError" in body:
    problems.append("ANON_BAD")

c2, body2 = probe(svc, "rounds")
if c2 == 401 or "Invalid API key" in body2 or "JWSError" in body2:
    problems.append("SVC_BAD")
elif c2 == 404 or "does not exist" in body2 or "PGRST205" in body2:
    problems.append("NO_TABLE")

# 비밀 키가 RLS 를 통과하는지 (=정말 service_role 인지)
if "SVC_BAD" not in problems and "NO_TABLE" not in problems:
    c3, b3 = probe(svc, "profiles")
    c4, b4 = probe(anon, "rounds")
    try:
        if c3 == 200 and c4 == 200 and json.loads(b3) == [] and json.loads(b4) == []:
            pass
    except Exception:
        pass
print("|".join(problems) if problems else "OK")
PY
)
case "$CHK" in
  OK) printf '\033[32m  ✓ 주소와 키가 모두 통한다\033[0m\n' ;;
  *URL_BAD*) printf '\n\033[31m주소에 연결되지 않는다.\033[0m Project URL 을 다시 확인해라.\n'
             printf '  Supabase 대시보드 › Settings › Data API 맨 위에 있다.\n'; exit 1 ;;
  *NO_TABLE*) printf '\n\033[31m테이블이 없다.\033[0m B-2 의 SQL 을 먼저 실행해라.\n'
              printf '  (SQL Editor 에서 실행하면 profiles / rounds / picks 가 생긴다)\n'; exit 1 ;;
  *ANON_BAD*) printf '\n\033[31m두 번째로 넣은 키(공개용)가 거부됐다.\033[0m\n'
              printf '  Legacy 탭의 \033[1manon\033[0m 키인지 확인해라.\n'; exit 1 ;;
  *SVC_BAD*)  printf '\n\033[31m세 번째로 넣은 키(비밀)가 거부됐다.\033[0m\n'
              printf '  Legacy 탭의 \033[1mservice_role\033[0m 키인지 확인해라.\n'; exit 1 ;;
  *) printf '\n\033[33m확인을 못 했다(%s). 그래도 계속한다.\033[0m\n' "$CHK" ;;
esac

mkdir -p docs collectormkdir -p docs collector
cat > docs/config.js <<CFG
// Supabase 연결 정보. anon 키는 공개돼도 되는 키이고, 접근 제어는 RLS 가 한다.
window.TS_CONFIG = {
  supabaseUrl: "$SB_URL",
  supabaseKey: "$SB_ANON"
};
CFG
cat > collector/secrets.json <<SEC
{
  "supabaseUrl": "$SB_URL",
  "serviceRoleKey": "$SB_SVC"
}
SEC
chmod 600 collector/secrets.json

printf '\n\033[32m✓ 설정 완료\033[0m\n'
printf '  docs/config.js         (anon 키 · 저장소에 올라감)\n'
printf '  collector/secrets.json (service_role 키 · \033[1m올라가지 않음\033[0m)\n'

# 혹시 모를 사고 방지: secrets.json 이 정말 제외되는지 확인
if git check-ignore -q collector/secrets.json 2>/dev/null; then
  printf '  → secrets.json 이 .gitignore 로 보호되는 것 확인했다\n'
else
  printf '\n\033[31m⚠ 경고: secrets.json 이 저장소에 올라갈 수 있다. 푸시하지 말고 알려라.\033[0m\n'; exit 1
fi

/usr/bin/python3 build_site.py >/dev/null 2>&1 && printf '  → 사이트 다시 빌드함\n'

printf '\n사이트에 반영하려면 Enter, 나중에 하려면 Control+C\n> '
read -r _
git add -A >/dev/null 2>&1
if git diff --cached --quiet 2>/dev/null; then
  printf '바뀐 게 없다.\n'
else
  git commit -q -m "Supabase 연결" && printf '커밋 완료\n'
  if git push -q 2>/dev/null; then
    printf '\033[32m푸시 완료 — 1~2분 뒤 사이트에 로그인 화면이 뜬다.\033[0m\n'
  else
    printf '\033[33m푸시 실패.\033[0m 터미널에서: cd ~/Desktop/토토스캐너 && git push\n'
  fi
fi
printf '\n이 창은 닫아도 된다.\n'
