# -*- coding: utf-8 -*-
"""Jednorazowy import kursów walut NBP (tabele A i B) do Supabase.

Pobiera średnie kursy wszystkich dostępnych walut za ostatnie 18 miesięcy
z api.nbp.pl i zapisuje do tabeli `kursy_walut`. Uruchamiany lokalnie:

    python nbp_import.py

Wymaga ustawionych SUPABASE_URL i SUPABASE_KEY (te same co aplikacja).
"""
import json, calendar, urllib.request, urllib.error
from datetime import date, timedelta

import db

NBP_BASE = "https://api.nbp.pl/api/exchangerates/tables"
MAX_DAYS = 367          # limit NBP na jedno zapytanie o zakres
MONTHS = 18             # ile miesięcy wstecz
BATCH = 500             # ile wierszy na jedną wysyłkę do Supabase


def months_back(d, n):
    """Cofa datę o n miesięcy, przycinając dzień do długości miesiąca docelowego."""
    m = d.month - 1 - n
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def chunk_ranges(start, end, max_days=MAX_DAYS):
    """Dzieli [start, end] (włącznie) na ciągłe kawałki <= max_days dni."""
    chunks, cur = [], start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=max_days - 1), end)
        chunks.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return chunks


def batches(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def parse_tables(tables):
    """Lista dni z NBP -> lista wierszy {kod, waluta, data, kurs}."""
    rows = []
    for t in tables:
        data = t.get("effectiveDate")
        for r in t.get("rates", []):
            rows.append({
                "kod": r.get("code"),
                "waluta": r.get("currency"),
                "data": data,
                "kurs": r.get("mid"),
            })
    return rows


def _get(url):
    """Jedyne miejsce realnego I/O sieciowego — podmieniane w testach."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        raise RuntimeError(f"NBP: błąd połączenia: {e.reason}")


def fetch_table(letter, start, end):
    """Pobiera tabelę letter (A/B) dla zakresu dat; 404 = brak danych -> []."""
    url = f"{NBP_BASE}/{letter}/{start}/{end}/?format=json"
    status, text = _get(url)
    if status == 404:
        return []
    if status >= 400:
        raise RuntimeError(f"NBP {letter} {start}..{end}: {status}: {text}")
    return parse_tables(json.loads(text))
