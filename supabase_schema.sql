-- supabase_schema.sql
-- Wklej całość w Supabase: SQL Editor -> New query -> Run. Uruchom raz.
-- Tabele odpowiadają tym z lokalnego SQLite (otodom.db).

create table if not exists oferty (
    id                  bigint generated always as identity primary key,
    miasto_wyszukiwania text,
    otodom_id           bigint unique,
    title               text,
    price               numeric,
    currency            text,
    price_per_m2        numeric,
    area_m2             numeric,
    rooms               text,
    floor               text,
    is_private_owner    boolean,
    location            text,
    url                 text
);

create table if not exists app_settings (
    key   text primary key,
    value text                  -- JSON przechowywany jako tekst (jak w SQLite)
);

create table if not exists discord_sent (
    miasto  text,
    url     text,
    sent_at timestamptz default now(),
    unique (miasto, url)
);

-- Bezpieczeństwo: włącz RLS na wszystkich tabelach. Aplikacja łączy się kluczem
-- service_role (po stronie serwera), który RLS omija, więc działa normalnie.
-- Brak policy = publiczny klucz anon nie ma dostępu do tych tabel.
alter table oferty       enable row level security;
alter table app_settings enable row level security;
alter table discord_sent enable row level security;
