#!/bin/bash
# API-Football 키를 secrets.json 에 넣어준다. (예상 라인업·부상자·선수 사진)
cd "$(dirname "$0")/collector" || exit 1
printf '\033[1m선수 정보 키 등록\033[0m — 예상 라인업 · 부상자 · 선수 사진\n'
printf '─────────────────────────────────────────\n'
printf 'dashboard.api-football.com 에서 무료 가입하면 바로 키가 나온다.\n'
printf '하루 100회 무료. 우리는 하루 90회까지만 쓰고 나머지는 남겨둔다.\n\n'
printf '\033[1mAPI 키\033[0m\n> '
read -r K
K="$(printf '%s' "$K" | tr -d '[:space:]')"
if [ ${#K} -lt 20 ]; then printf '\n\033[31m키가 너무 짧다.\033[0m\n'; exit 1; fi

printf '\n확인 중…\n'
OUT=$(curl -s -m 25 -w '\n%{http_code}' -H "x-apisports-key: $K" \
  "https://v3.football.api-sports.io/status")
CODE=$(printf '%s' "$OUT" | tail -1)
BODY=$(printf '%s' "$OUT" | sed '$d')
if [ "$CODE" != "200" ]; then
  printf '\033[31m키가 거부됐다 (HTTP %s)\033[0m\n' "$CODE"
  printf '%s\n' "$(printf '%s' "$BODY" | head -c 200)"
  exit 1
fi
printf '%s' "$BODY" | /usr/bin/python3 - <<'PY'
import json, sys
d = json.load(sys.stdin).get("response") or {}
if not d:
    print("\033[31m  응답이 비었다 — 키를 다시 확인해라\033[0m"); sys.exit(1)
sub = d.get("subscription") or {}; req = d.get("requests") or {}
print("\033[32m  ✓ 키가 통한다 — 요금제 %s, 오늘 %s/%s 사용\033[0m"
      % (sub.get("plan"), req.get("current"), req.get("limit_day")))
PY
[ $? -ne 0 ] && exit 1

if [ ! -f secrets.json ]; then
  printf '\n\033[31msecrets.json 이 없다.\033[0m 먼저 "Supabase 연결.command" 를 실행해라.\n'; exit 1
fi
/usr/bin/python3 - "$K" <<'PY'
import json, sys
p = "secrets.json"
d = json.load(open(p, encoding="utf-8"))
d["footballApiKey"] = sys.argv[1]
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("  secrets.json 에 저장했다 (저장소에는 올라가지 않는다)")
PY

printf '\n\033[1m다음\033[0m\n'
printf '  이제 토토스캐너 실행을 돌릴 때마다 선수 자료가 조금씩 쌓인다.\n'
printf '  하루 100회 제한이 있어서 두 시즌 라인업은 한 번에 못 받는다.\n'
printf '  이번 회차에 나오는 팀부터 먼저 채우니, 며칠 돌리면 쓸 만해진다.\n'
printf '  진행률은 실행 창에 %% 로 찍힌다.\n'
printf '\n이 창은 닫아도 된다.\n'
