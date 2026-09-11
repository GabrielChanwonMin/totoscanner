#!/bin/bash
# 더블클릭: 지금 이 순간의 배당을 수집 → 사이트에 반영 → 브라우저로 연다.
cd "$(dirname "$0")" || exit 1
ROOT="$PWD"
ARTIFACT_URL="https://claude.ai/code/artifact/bdeadccc-4ea3-47de-b703-f5415bc1fe2e"

printf '\033[1m토토스캐너\033[0m — 지금 배당을 받아온다\n'
printf '─────────────────────────────────────────\n\n'

cd collector || exit 1
printf '\033[1m[1/5]\033[0m 베트맨 회차·배당\n'
if ! /usr/bin/python3 collect_betman.py "$@"; then
  printf '\n\033[33m베트맨 수집 실패.\033[0m 회차가 발매 전이거나 일시적 오류다.\n'
  printf '  회차를 직접 찍으려면: python3 collect_betman.py 260109\n'
fi

printf '\n\033[1m[2/5]\033[0m 해외 컨센서스 배당\n'
/usr/bin/python3 collect_odds.py

printf '\n\033[1m[3/5]\033[0m 이번 회차 예측 기록\n'
(cd collector && /usr/bin/python3 predict_round.py)

printf '\n\033[1m[4/5]\033[0m 지난 회차 자동 채점\n'
(cd collector && /usr/bin/python3 settle.py)

printf '\n\033[1m[5/5]\033[0m 회차 데이터 올리기\n'
cd "$ROOT" || exit 1
PUSHED=0
if [ -f collector/secrets.json ]; then
  if (cd collector && /usr/bin/python3 push_round.py); then PUSHED=1; fi
fi
if [ "$PUSHED" = "0" ]; then
  # Supabase 가 없으면 예전 방식 — 정적 파일로 배포
  if [ -s collector/latest_import.json ]; then
    mkdir -p docs/data && cp collector/latest_import.json docs/data/latest.json
    printf '  Supabase 미설정 → docs/data/latest.json 으로 대체한다\n'
    printf '  \033[33m이 파일은 공개된다. 감추려면 setup/설치.md 의 B 단계를 마쳐라.\033[0m\n'
  else
    printf '  올릴 데이터가 없다.\n'
  fi
fi

printf '\n\033[1m사이트 열기\033[0m\n'
REMOTE=$(git remote get-url origin 2>/dev/null)
if [ -n "$REMOTE" ]; then
  # 앱 코드가 바뀐 경우에만 푸시한다 (회차 데이터는 Supabase 로 갔다)
  git add -A >/dev/null 2>&1
  if ! git diff --cached --quiet 2>/dev/null; then
    git commit -q -m "갱신 $(date '+%Y-%m-%d %H:%M')" 2>/dev/null
    if git push -q 2>/dev/null; then printf '  코드 변경분을 푸시했다\n'
    else printf '  \033[33m푸시 실패\033[0m — 직접: cd "%s" && git push\n' "$ROOT"; fi
  fi
  URL=$(printf '%s' "$REMOTE" | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##' \
        | awk -F/ '{print "https://" $1 ".github.io/" $2 "/"}')
  printf '  %s\n' "$URL"
  open "$URL"
else
  printf '  \033[33mGitHub 저장소 미연결.\033[0m 클립보드로 넘긴다.\n'
  if [ -s collector/latest_import.json ]; then
    pbcopy < collector/latest_import.json
    COPIED=$(pbpaste 2>/dev/null | wc -c | tr -d ' '); SRC=$(wc -c < collector/latest_import.json | tr -d ' ')
    [ "$COPIED" = "$SRC" ] && printf '  ✓ 클립보드에 담았다 — 앱에서 ⌘V\n' \
                           || printf '  복사 실패: %s/collector/latest_import.json\n' "$ROOT"
  fi
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
