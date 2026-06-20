# db.py
# -*- coding: utf-8 -*-
"""Warstwa Supabase (PostgREST) przez bibliotekę standardową — bez zależności.

Włącza się tylko gdy ustawione są zmienne SUPABASE_URL i SUPABASE_KEY
(na Vercelu). Lokalnie pozostają puste, więc warstwa danych używa SQLite.
"""
import os, json, urllib.parse, urllib.request, urllib.error


def _url():
    return (os.environ.get("SUPABASE_URL") or "").strip()


def _key():
    return (os.environ.get("SUPABASE_KEY") or "").strip()


def enabled():
    return bool(_url() and _key())


def _base_url():
    return _url().rstrip("/") + "/rest/v1"


def _headers(prefer=None):
    h = {
        "apikey": _key(),
        "Authorization": "Bearer " + _key(),
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _build_query(params):
    if not params:
        return ""
    # quote_via=quote_plus koduje spacje jako '+'; wartości typu 'eq.x' zachowane.
    return urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
