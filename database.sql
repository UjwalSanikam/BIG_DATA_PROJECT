-- Run once in your Supabase project's SQL editor. Browser clients get no direct table access.
create table if not exists public.lab_rooms (
 id uuid primary key,
 invite_hash text not null,
 version bigint not null default 0,
 state jsonb not null,
 created_at timestamptz not null default now()
);
create table if not exists public.lab_evidence (
 id uuid primary key,
 room_id uuid not null references public.lab_rooms(id) on delete cascade,
 step_id text not null,
 name text not null,
 at timestamptz not null,
 mime text not null check (mime in ('image/png','image/jpeg','image/webp')),
 data text not null check (length(data) <= 1398104)
);
create index if not exists lab_evidence_room on public.lab_evidence(room_id);
alter table public.lab_rooms enable row level security;
alter table public.lab_evidence enable row level security;
revoke all on public.lab_rooms, public.lab_evidence from anon, authenticated;
grant select, insert, update, delete on public.lab_rooms, public.lab_evidence to service_role;
