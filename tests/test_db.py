# tests/test_db.py
# -*- coding: utf-8 -*-
import os, unittest

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

if __name__ == "__main__":
    unittest.main()
