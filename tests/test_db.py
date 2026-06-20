# tests/test_db.py
# -*- coding: utf-8 -*-
import os, io, contextlib, unittest

class DbHelpersTest(unittest.TestCase):
    def setUp(self):
        self._old = {k: os.environ.get(k) for k in ("SUPABASE_URL", "SUPABASE_KEY")}
        for k in ("SUPABASE_URL", "SUPABASE_KEY"):
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _reload(self):
        import importlib, db
        return importlib.reload(db)

    def test_enabled_false_when_unset(self):
        db = self._reload()
        self.assertFalse(db.enabled())

    def test_enabled_false_when_only_one_set(self):
        os.environ["SUPABASE_URL"] = "https://x.supabase.co"
        db = self._reload()
        self.assertFalse(db.enabled())

    def test_enabled_true_when_both_set(self):
        os.environ["SUPABASE_URL"] = "https://x.supabase.co"
        os.environ["SUPABASE_KEY"] = "secret"
        db = self._reload()
        self.assertTrue(db.enabled())

    def test_base_url_strips_trailing_slash(self):
        os.environ["SUPABASE_URL"] = "https://x.supabase.co/"
        os.environ["SUPABASE_KEY"] = "secret"
        db = self._reload()
        self.assertEqual(db._base_url(), "https://x.supabase.co/rest/v1")

    def test_headers_contain_auth_and_prefer(self):
        os.environ["SUPABASE_URL"] = "https://x.supabase.co"
        os.environ["SUPABASE_KEY"] = "secret"
        db = self._reload()
        h = db._headers(prefer="resolution=merge-duplicates")
        self.assertEqual(h["apikey"], "secret")
        self.assertEqual(h["Authorization"], "Bearer secret")
        self.assertEqual(h["Content-Type"], "application/json")
        self.assertEqual(h["Prefer"], "resolution=merge-duplicates")

    def test_headers_no_prefer_key_when_none(self):
        os.environ["SUPABASE_URL"] = "https://x.supabase.co"
        os.environ["SUPABASE_KEY"] = "secret"
        db = self._reload()
        self.assertNotIn("Prefer", db._headers())

    def test_build_query_encodes_and_keeps_operators(self):
        db = self._reload()
        q = db._build_query({"select": "url", "miasto": "eq.Poznań"})
        self.assertIn("select=url", q)
        self.assertIn("miasto=eq.Pozna", q)  # ń zakodowane procentowo
        self.assertNotIn(" ", q)

    def test_build_query_empty(self):
        db = self._reload()
        self.assertEqual(db._build_query({}), "")

class DbPartialConfigWarningTest(unittest.TestCase):
    """Sprawdza, że ustawienie tylko jednej ze zmiennych wywołuje ostrzeżenie."""

    def setUp(self):
        self._old = {k: os.environ.get(k) for k in ("SUPABASE_URL", "SUPABASE_KEY")}
        for k in ("SUPABASE_URL", "SUPABASE_KEY"):
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _reload(self):
        import importlib, db
        return importlib.reload(db)

    def test_partial_config_warns_on_stderr(self):
        os.environ["SUPABASE_URL"] = "https://x.supabase.co"
        # SUPABASE_KEY celowo nie ustawiona
        db = self._reload()
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            result = db.enabled()
        self.assertFalse(result)
        self.assertIn("SUPABASE_URL", buf.getvalue())

class DbRequestTest(unittest.TestCase):
    def setUp(self):
        os.environ["SUPABASE_URL"] = "https://x.supabase.co"
        os.environ["SUPABASE_KEY"] = "secret"
        import importlib, db
        self.db = importlib.reload(db)
        self.calls = []
        def fake_do(method, url, headers, body=None):
            self.calls.append({"method": method, "url": url,
                               "headers": headers, "body": body})
            return 200, "[]"
        self.db._do = fake_do

    def tearDown(self):
        for k in ("SUPABASE_URL", "SUPABASE_KEY"):
            os.environ.pop(k, None)

    def test_select_builds_get_with_params(self):
        self.db.select("discord_sent", columns="url",
                       filters={"miasto": "eq.Poznań"})
        c = self.calls[0]
        self.assertEqual(c["method"], "GET")
        self.assertTrue(c["url"].startswith(
            "https://x.supabase.co/rest/v1/discord_sent?"))
        self.assertIn("select=url", c["url"])
        self.assertIn("miasto=eq.Pozna", c["url"])

    def test_select_includes_order(self):
        self.db.select("oferty", order="price.asc.nullslast")
        self.assertIn("order=price.asc.nullslast", self.calls[0]["url"])

    def test_upsert_sets_prefer_and_on_conflict(self):
        self.db.upsert("oferty", [{"otodom_id": 1}], on_conflict="otodom_id")
        c = self.calls[0]
        self.assertEqual(c["method"], "POST")
        self.assertIn("on_conflict=otodom_id", c["url"])
        self.assertEqual(c["headers"]["Prefer"], "resolution=merge-duplicates")
        import json
        self.assertEqual(json.loads(c["body"].decode("utf-8")), [{"otodom_id": 1}])

    def test_upsert_ignore_duplicates(self):
        self.db.upsert("discord_sent", [{"miasto": "a", "url": "u"}],
                       on_conflict="miasto,url", ignore_duplicates=True)
        self.assertEqual(self.calls[0]["headers"]["Prefer"],
                         "resolution=ignore-duplicates")

    def test_upsert_empty_rows_no_call(self):
        self.db.upsert("oferty", [], on_conflict="otodom_id")
        self.assertEqual(self.calls, [])

    def test_request_raises_on_http_error(self):
        self.db._do = lambda *a, **k: (409, "conflict detail")
        with self.assertRaises(RuntimeError) as ctx:
            self.db.select("oferty")
        self.assertIn("409", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
