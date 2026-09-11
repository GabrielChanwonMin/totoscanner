-- ════════════════════════════════════════════════════════════
--  베팅 전표(조합) 기록용 표 — 나중에 추가된 것
--  SQL Editor › New query 에 붙여넣고 Run
-- ════════════════════════════════════════════════════════════

create table if not exists public.slips (
  id          text primary key,
  created_at  timestamptz not null default now(),
  owner_id    uuid references auth.users on delete set null,
  owner_name  text,
  round       text,
  style       text,                     -- '안정형' / '가치형' / '균형형' / '직접'
  legs        jsonb not null,           -- [{no,league,home,away,market,line,sel,selName,odds,p,kick}]
  odds        numeric,                  -- 조합 배당 (각 픽 배당의 곱)
  prob        double precision,         -- 조합 적중 확률
  ev          double precision,
  ev_lo       double precision,
  stake       numeric default 1000,     -- 건 금액
  result      text default '',          -- '' 미정 / 'W' 적중 / 'L' 미적중 / 'V' 무효
  settled_at  timestamptz,
  detail      jsonb                     -- 정산 결과 (레그별 적중 여부, 스코어)
);

create index if not exists slips_created_idx on public.slips (created_at desc);

alter table public.slips enable row level security;

drop policy if exists "approved read"   on public.slips;
drop policy if exists "approved insert" on public.slips;
drop policy if exists "approved update" on public.slips;
drop policy if exists "approved delete" on public.slips;
create policy "approved read"   on public.slips for select using (public.is_approved());
create policy "approved insert" on public.slips for insert with check (public.is_approved());
create policy "approved update" on public.slips for update using (public.is_approved())
                                                 with check (public.is_approved());
create policy "approved delete" on public.slips for delete using (public.is_approved());
