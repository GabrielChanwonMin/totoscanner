#!/bin/bash
# The Odds API 키를 secrets.json 에 넣어준다.
cd "$(dirname "$0")/collector" || exit 1
printf '\033[1m실시간 해외 배당 키 등록\033[0m\n'
printf '─────────────────────────────────────────\n'
printf 'the-odds-api.com 에서 무료 가입하면 메일로 키가 온다.\n'
printf '월 500회 무료 · 5대 리그 한 번 갱신에 5회 쓴다.\n\n'
printf '\033[1mAPI 키\033[0m\n> '
read -r K
K="$(printf '%s' "$K" | tr -d '[:space:]')"
if [ ${#K} -lt 20 ]; then printf '\n\033[31m키가 너무 짧다.\033[0m\n'; exit 1; fi

printf '\n확인 중…\n'
OUT=$(curl -s -m 25 -w '\n%{http_code}' \
  "https://api.the-odds-api.com/v4/sports/soccer_epl/odds/?apiKey=$K&regions=eu&markets=h2h&oddsFormat=decimal")
CODE=$(printf '%s' "$OUT" | tail -1)
BODY=$(printf '%s' "$OUT" | sed '$d')
if [ "$CODE" != "200" ]; then
  printf '\033[31m키가 거부됐다 (HTTP %s)\033[0m\n' "$CODE"
  printf '%s\n' "$(printf '%s' "$BODY" | head -c 200)"
  exit 1
fi
N=$(printf '%s' "$BODY" | /usr/bin/python3 -c "import json,sys;print(len(json.load(sys.stdin)))" 2>/dev/null || echo "?")
printf '\033[32m  ✓ 키가 통한다 — EPL 경기 %s개가 잡힌다\033[0m\n' "$N"

if [ ! -f secrets.json ]; then
  printf '\n\033[31msecrets.json 이 없다.\033[0m 먼저 "Supabase 연결.command" 를 실행해라.\n'; exit 1
fi
/usr/bin/python3 - "$K" <<'PY'
import json, sys
p = "secrets.json"
d = json.load(open(p, encoding="utf-8"))
d["oddsApiKey"] = sys.argv[1]
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("  secrets.json 에 저장했다 (저장소에는 올라가지 않는다)")
PY
printf '\n이제 \033[1m토토스캐너 실행\033[0m 을 돌리면 실시간 해외 배당이 붙는다.\n'
printf '\n이 창은 닫아도 된다.\n'
