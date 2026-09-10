-- ════════════════════════════════════════════════════════════
--  토토스캐너 — Supabase 스키마
--  대시보드 › SQL Editor › New query 에 통째로 붙여넣고 Run
-- ════════════════════════════════════════════════════════════

-- ── 1. 회원 (가입은 누구나, 승인은 주인만) ──────────────────
create table if not exists public.profiles (
  id         uuid primary key references auth.users on delete cascade,
  email      text,
  name       text,
  approved   boolean not null default false,
  role       text    not null default 'member',   -- 'owner' 면 승인 권한
  created_at timestamptz not null default now()
);

-- 가입하면 프로필 행이 자동으로 생긴다 (승인 대기 상태)
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email, name)
  values (new.id, new.email, coalesce(new.raw_user_meta_data->>'name', ''))
  on conflict (id) do nothing;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- 승인 여부를 재귀 없이 확인하는 헬퍼
create or replace function public.is_approved()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles
                 where id = auth.uid() and approved) $$;

create or replace function public.is_owner()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles
                 where id = auth.uid() and role = 'owner') $$;

-- ── 2. 회차 데이터 (수집기가 넣고, 승인된 사람만 읽는다) ─────
create table if not exists public.rounds (
  id           text primary key,          -- 'current' 또는 회차번호
  gm_ts        bigint,
  round_no     integer,
  captured_at  timestamptz not null default now(),
  sale_end     bigint,
  payload      jsonb not null,            -- {matches:[...], oddsChanges:[...]}
  updated_at   timestamptz not null default now()
);

-- ── 3. 픽 기록 (승인된 사람끼리 공유) ───────────────────────
create table if not exists public.picks (
  id            text primary key,
  "savedAt"     timestamptz not null default now(),
  owner_id      uuid references auth.users on delete set null,
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

-- ── 4. 행 수준 보안 ─────────────────────────────────────────
alter table public.profiles enable row level security;
alter table public.rounds   enable row level security;
alter table public.picks    enable row level security;

-- 프로필: 자기 것은 늘 보인다(승인 대기 화면용). 주인은 전부 보고 고칠 수 있다.
drop policy if exists "self read"     on public.profiles;
drop policy if exists "owner read"    on public.profiles;
drop policy if exists "owner update"  on public.profiles;
create policy "self read"    on public.profiles for select using (id = auth.uid());
create policy "owner read"   on public.profiles for select using (public.is_owner());
create policy "owner update" on public.profiles for update using (public.is_owner())
                                                  with check (public.is_owner());

-- 회차·픽: 승인된 사람만. 승인 안 된 사람에겐 아예 없는 것처럼 보인다.
drop policy if exists "approved read"   on public.rounds;
create policy "approved read"   on public.rounds for select using (public.is_approved());

drop policy if exists "approved read"   on public.picks;
drop policy if exists "approved insert" on public.picks;
drop policy if exists "approved update" on public.picks;
drop policy if exists "approved delete" on public.picks;
create policy "approved read"   on public.picks for select using (public.is_approved());
create policy "approved insert" on public.picks for insert with check (public.is_approved());
create policy "approved update" on public.picks for update using (public.is_approved())
                                                 with check (public.is_approved());
create policy "approved delete" on public.picks for delete using (public.is_approved());

-- 수집기는 service_role 키로 rounds 에 쓴다. service_role 은 RLS 를 통과하므로
-- 별도 정책이 필요 없다. 그 키는 절대 저장소에 올리지 마라 (.gitignore 처리됨).

-- ════════════════════════════════════════════════════════════
--  ⚠ 마지막 단계: 가입한 뒤 아래를 한 번 실행해 '주인'이 돼라.
--     이메일은 네가 가입한 주소로 바꾼다.
-- ════════════════════════════════════════════════════════════
-- update public.profiles set approved = true, role = 'owner'
--   where email = 'minchwen0205@gmail.com';
