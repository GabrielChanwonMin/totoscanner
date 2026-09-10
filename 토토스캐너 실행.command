#!/bin/bash
# 더블클릭: 지금 이 순간의 배당을 수집 → 사이트에 반영 → 브라우저로 연다.
cd "$(dirname "$0")" || exit 1
ROOT="$PWD"
ARTIFACT_URL="https://claude.ai/code/artifact/bdeadccc-4ea3-47de-b703-f5415bc1fe2e"

printf '\033[1m토토스캐너\033[0m — 지금 배당을 받아온다\n'
printf '─────────────────────────────────────────\n\n'

cd collector || exit 1
printf '\033[1m[1/4]\033[0m 베트맨 회차·배당\n'
if ! /usr/bin/python3 collect_betman.py "$@"; then
  printf '\n\033[33m베트맨 수집 실패.\033[0m 회차가 발매 전이거나 일시적 오류다.\n'
  printf '  회차를 직접 찍으려면: python3 collect_betman.py 260109\n'
fi

printf '\n\033[1m[2/4]\033[0m 해외 컨센서스 배당\n'
/usr/bin/python3 collect_odds.py

printf '\n\033[1m[3/4]\033[0m 사이트에 반영\n'
cd "$ROOT" || exit 1
if [ -s collector/latest_import.json ]; then
  mkdir -p docs/data
  cp collector/latest_import.json docs/data/latest.json
  N=$(/usr/bin/python3 -c "import json;print(len(json.load(open('docs/data/latest.json')).get('matches',[])))" 2>/dev/null || echo "?")
  printf '  %s행을 docs/data/latest.json 에 넣었다\n' "$N"
else
  printf '  \033[33m받아온 데이터가 없다.\033[0m 배당 공시 전일 수 있다.\n'
fi

printf '\n\033[1m[4/4]\033[0m 배포\n'
REMOTE=$(git remote get-url origin 2>/dev/null)
if [ -n "$REMOTE" ]; then
  git add -A docs >/dev/null 2>&1
  if git diff --cached --quiet 2>/dev/null; then
    printf '  바뀐 게 없다 (이미 최신)\n'
  else
    git commit -q -m "회차 데이터 갱신 $(date '+%Y-%m-%d %H:%M')" && printf '  커밋 완료\n'
    if git push -q 2>/dev/null; then
      printf '  \033[32m푸시 완료\033[0m — 사이트에 반영되기까지 30초쯤 걸린다\n'
    else
      printf '  \033[33m푸시 실패.\033[0m 이 창에 아래를 붙여넣어 직접 밀어라:\n'
      printf '    cd "%s" && git push\n' "$ROOT"
    fi
  fi
  # origin 주소에서 Pages 주소를 만든다
  URL=$(printf '%s' "$REMOTE" | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##' \
        | awk -F/ '{print "https://" $1 ".github.io/" $2 "/"}')
  printf '\n\033[1m사이트를 연다:\033[0m %s\n' "$URL"
  printf '  페이지를 열면 이번 회차가 자동으로 올라온다. 붙여넣기 필요 없다.\n\n'
  open "$URL"
else
  printf '  \033[33mGitHub 저장소가 아직 연결되지 않았다.\033[0m 클립보드로 넘긴다.\n'
  if [ -s collector/latest_import.json ]; then
    pbcopy < collector/latest_import.json
    COPIED=$(pbpaste 2>/dev/null | wc -c | tr -d ' '); SRC=$(wc -c < collector/latest_import.json | tr -d ' ')
    if [ "$COPIED" = "$SRC" ]; then printf '  ✓ 클립보드에 담았다 — 앱에서 ⌘V\n'
    else printf '  복사 실패. 파일을 직접 열어 전체 복사해라: %s/collector/latest_import.json\n' "$ROOT"; fi
  fi
  printf '\n'
  open "$ARTIFACT_URL"
fi

# 스냅샷은 최근 60개만 (용량 관리)
ls -1t collector/snapshots/*.json 2>/dev/null | tail -n +61 | xargs rm -f 2>/dev/null

# 레이팅 신선도
/usr/bin/python3 - <<'PY'
import json, os, datetime as dt
try:
    asof = dt.date.fromisoformat(json.load(open("engine/ratings.json", encoding="utf-8"))["asof"])
    d = (dt.date.today() - asof).days
    if d >= 30:
        print(f"\033[33m⚠ 팀 레이팅이 {d}일 지났다 ({asof}).\033[0m 재학습하려면:")
        print("    cd engine && python3 refresh_ratings.py")
except Exception:
    pass
PY
printf '\n이 창은 닫아도 된다.\n'
