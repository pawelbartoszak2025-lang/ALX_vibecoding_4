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


def _do(method, url, headers, body=None):
    """Jedyne miejsce realnego I/O — podmieniane w testach."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _request(method, path, *, params=None, body=None, prefer=None):
    url = _base_url() + "/" + path
    q = _build_query(params or {})
    if q:
        url += "?" + q
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    status, text = _do(method, url, _headers(prefer), data)
    if status >= 400:
        raise RuntimeError(f"Supabase {status}: {text}")
    return json.loads(text) if text else []


def select(table, *, columns="*", order=None, filters=None):
    params = {"select": columns}
    if order:
        params["order"] = order
    if filters:
        params.update(filters)
    return _request("GET", table, params=params)


def upsert(table, rows, *, on_conflict, ignore_duplicates=False):
    if not rows:
        return
    resolution = "ignore-duplicates" if ignore_duplicates else "merge-duplicates"
    _request("POST", table, params={"on_conflict": on_conflict},
             body=rows, prefer="resolution=" + resolution)
