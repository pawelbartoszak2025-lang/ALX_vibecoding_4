# -*- coding: utf-8 -*-
"""Punkt wejścia dla Vercela.

Vercel uruchamia funkcje z katalogu /api. Tu nie powielamy logiki —
dokładamy katalog główny projektu do ścieżki importów i wystawiamy
istniejący serwer (server.Handler) jako funkcję bezserwerową.

Vercel oczekuje obiektu o nazwie `handler` będącego podklasą
BaseHTTPRequestHandler — dokładnie tym jest server.Handler.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import server  # noqa: E402  (import po ustawieniu sys.path)

handler = server.Handler
