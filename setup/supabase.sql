-- 토토스캐너 기록 공유용 테이블
-- Supabase 대시보드 › SQL Editor 에 통째로 붙여넣고 Run 하면 된다.

create table if not exists public.picks (
  id            text primary key,
  "savedAt"     timestamptz not null default now(),
  round         text,
  league        text,
  home          text,
  away          text,
  market        text,
  line          numeric,
  no            integer,
  "selIdx"      integer,
  sel           text,
  odds          numeric,
  p             double precision,
  ev            double precision,
  "evLo"        double precision,
  grade         text,
  source        text,
  result        text,
  "closingOdds" jsonb,
  clv           double precision
);

create index if not exists picks_saved_at_idx on public.picks ("savedAt" desc);

-- 행 수준 보안을 켜고, anon 키로 읽기·쓰기를 허용한다.
-- ⚠ anon 키는 웹페이지에 공개된다. 저장소를 찾아낸 사람은 이 표를 보거나 고칠 수 있다.
--    들어가는 건 픽 기록뿐이고 개인정보는 없다. 그래도 싫으면 config.js 를 비워두면
--    기록이 각자 브라우저에만 저장된다 (앱의 다른 기능은 전부 동일).
alter table public.picks enable row level security;

drop policy if exists "ts read"   on public.picks;
drop policy if exists "ts insert" on public.picks;
drop policy if exists "ts update" on public.picks;
drop policy if exists "ts delete" on public.picks;

create policy "ts read"   on public.picks for select using (true);
create policy "ts insert" on public.picks for insert with check (true);
create policy "ts update" on public.picks for update using (true) with check (true);
create policy "ts delete" on public.picks for delete using (true);
