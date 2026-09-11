#!/bin/bash
# Supabase 키를 물어보고 설정 파일 두 개를 대신 만들어준다.
cd "$(dirname "$0")" || exit 1

printf '\033[1mSupabase 연결\033[0m\n'
printf '─────────────────────────────────────────\n'
printf 'Supabase 대시보드 › Project Settings › API 에서 세 개를 복사해 온다.\n'
printf '붙여넣고 Enter. 취소하려면 Control+C.\n\n'

printf '\033[1m1) Project URL\033[0m (https://...supabase.co)\n> '
read -r SB_URL
SB_URL="${SB_URL%/}"
case "$SB_URL" in
  https://*.supabase.co) ;;
  *) printf '\n\033[31m주소 형식이 이상하다.\033[0m https://무언가.supabase.co 여야 한다.\n'; exit 1;;
esac

printf '\n\033[1m2) anon public 키\033[0m (웹페이지에 들어간다)\n> '
read -r SB_ANON
printf '\n\033[1m3) service_role 키\033[0m (수집기 전용 · 저장소에 안 올라간다)\n> '
read -r SB_SVC

for K in "$SB_ANON" "$SB_SVC"; do
  if [ ${#K} -lt 40 ]; then
    printf '\n\033[31m키가 너무 짧다.\033[0m 통째로 복사했는지 확인해라.\n'; exit 1
  fi
done
if [ "$SB_ANON" = "$SB_SVC" ]; then
  printf '\n\033[31m두 키가 같다.\033[0m anon 과 service_role 은 다른 키다.\n'; exit 1
fi

mkdir -p docs collector
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
