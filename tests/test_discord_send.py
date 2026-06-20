# tests/test_discord_send.py
# -*- coding: utf-8 -*-
import unittest
import discord_send as ds

class DiscordSupabaseTest(unittest.TestCase):
    def setUp(self):
        self.sent_urls = []
        self.upserts = []
        self._orig = ds.db
        outer = self
        class FakeDb:
            @staticmethod
            def enabled():
                return True
            @staticmethod
            def select(table, columns="*", order=None, filters=None):
                return [{"url": u} for u in outer.sent_urls]
            @staticmethod
            def upsert(table, rows, on_conflict, ignore_duplicates=False):
                outer.upserts.append({"table": table, "rows": rows,
                                      "on_conflict": on_conflict,
                                      "ignore": ignore_duplicates})
        ds.db = FakeDb

    def tearDown(self):
        ds.db = self._orig

    def test_filter_new_drops_already_sent_and_dupes(self):
        self.sent_urls = ["http://a"]
        offers = [{"url": "http://a"}, {"url": "http://b"}, {"url": "http://b"}]
        new = ds.filter_new("Poznań", offers)
        self.assertEqual([o["url"] for o in new], ["http://b"])

    def test_mark_sent_upserts_ignore_duplicates(self):
        ds.mark_sent("Poznań", [{"url": "http://b"}])
        up = self.upserts[0]
        self.assertEqual(up["table"], "discord_sent")
        self.assertEqual(up["on_conflict"], "miasto,url")
        self.assertTrue(up["ignore"])
        self.assertEqual(up["rows"][0]["miasto"], "Poznań")
        self.assertEqual(up["rows"][0]["url"], "http://b")

if __name__ == "__main__":
    unittest.main()
