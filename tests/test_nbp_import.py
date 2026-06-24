# tests/test_nbp_import.py
# -*- coding: utf-8 -*-
import unittest
import json
from datetime import date, timedelta
import nbp_import as nbp


class DateHelpersTest(unittest.TestCase):
    def test_months_back_simple(self):
        self.assertEqual(nbp.months_back(date(2026, 6, 24), 18), date(2024, 12, 24))

    def test_months_back_clamps_day(self):
        # 31 sierpnia minus 6 miesięcy -> luty nie ma 31 dni -> 28
        self.assertEqual(nbp.months_back(date(2026, 8, 31), 6), date(2026, 2, 28))

    def test_chunk_ranges_splits_18_months(self):
        start, end = date(2024, 12, 24), date(2026, 6, 24)
        chunks = nbp.chunk_ranges(start, end, max_days=367)
        # każdy kawałek <= 367 dni (włącznie)
        for s, e in chunks:
            self.assertLessEqual((e - s).days + 1, 367)
        # ciągłość: następny zaczyna się dzień po końcu poprzedniego
        for (s1, e1), (s2, e2) in zip(chunks, chunks[1:]):
            self.assertEqual(s2, e1 + timedelta(days=1))
        # pokrycie całego zakresu
        self.assertEqual(chunks[0][0], start)
        self.assertEqual(chunks[-1][1], end)

    def test_chunk_ranges_single_when_small(self):
        start, end = date(2026, 1, 1), date(2026, 1, 31)
        self.assertEqual(nbp.chunk_ranges(start, end), [(start, end)])

    def test_batches_divides(self):
        self.assertEqual(list(nbp.batches([1, 2, 3, 4, 5], 2)),
                         [[1, 2], [3, 4], [5]])

    def test_batches_empty(self):
        self.assertEqual(list(nbp.batches([], 2)), [])


class ParseTablesTest(unittest.TestCase):
    SAMPLE = [
        {
            "table": "A",
            "no": "120/A/NBP/2026",
            "effectiveDate": "2026-06-23",
            "rates": [
                {"currency": "dolar amerykański", "code": "USD", "mid": 4.0150},
                {"currency": "euro", "code": "EUR", "mid": 4.2500},
            ],
        },
        {
            "table": "A",
            "no": "121/A/NBP/2026",
            "effectiveDate": "2026-06-24",
            "rates": [
                {"currency": "dolar amerykański", "code": "USD", "mid": 4.0200},
            ],
        },
    ]

    def test_parse_tables_flattens_rows(self):
        rows = nbp.parse_tables(self.SAMPLE)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0], {"kod": "USD", "waluta": "dolar amerykański",
                                   "data": "2026-06-23", "kurs": 4.0150})
        self.assertEqual(rows[2], {"kod": "USD", "waluta": "dolar amerykański",
                                   "data": "2026-06-24", "kurs": 4.0200})

    def test_parse_tables_empty(self):
        self.assertEqual(nbp.parse_tables([]), [])


class FetchTableTest(unittest.TestCase):
    def setUp(self):
        self._orig_get = nbp._get
        self.calls = []

    def tearDown(self):
        nbp._get = self._orig_get

    def test_fetch_table_builds_url_and_parses(self):
        sample = json.dumps([
            {"effectiveDate": "2026-06-23",
             "rates": [{"currency": "euro", "code": "EUR", "mid": 4.25}]},
        ])
        def fake_get(url):
            self.calls.append(url)
            return 200, sample
        nbp._get = fake_get
        rows = nbp.fetch_table("A", "2026-06-01", "2026-06-23")
        self.assertEqual(self.calls[0],
            "https://api.nbp.pl/api/exchangerates/tables/A/2026-06-01/2026-06-23/?format=json")
        self.assertEqual(rows, [{"kod": "EUR", "waluta": "euro",
                                 "data": "2026-06-23", "kurs": 4.25}])

    def test_fetch_table_404_returns_empty(self):
        nbp._get = lambda url: (404, "404 NotFound - Not Found")
        self.assertEqual(nbp.fetch_table("B", "2024-12-25", "2024-12-26"), [])

    def test_fetch_table_raises_on_other_error(self):
        nbp._get = lambda url: (500, "server error")
        with self.assertRaises(RuntimeError) as ctx:
            nbp.fetch_table("A", "2026-06-01", "2026-06-23")
        self.assertIn("500", str(ctx.exception))


class DedupeRowsTest(unittest.TestCase):
    def test_dedupe_keeps_last_on_duplicate_key(self):
        rows = [
            {"kod": "USD", "waluta": "dolar", "data": "2026-06-23", "kurs": 4.0},
            {"kod": "USD", "waluta": "dolar", "data": "2026-06-23", "kurs": 4.1},
        ]
        out = nbp.dedupe_rows(rows)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["kurs"], 4.1)

    def test_dedupe_keeps_distinct_keys(self):
        rows = [
            {"kod": "USD", "waluta": "dolar", "data": "2026-06-23", "kurs": 4.0},
            {"kod": "EUR", "waluta": "euro", "data": "2026-06-23", "kurs": 4.25},
            {"kod": "USD", "waluta": "dolar", "data": "2026-06-24", "kurs": 4.02},
        ]
        out = nbp.dedupe_rows(rows)
        self.assertEqual(len(out), 3)


class RunTest(unittest.TestCase):
    def setUp(self):
        self._orig = (nbp.fetch_table, nbp.db.enabled, nbp.db.upsert)
        self.upserts = []

    def tearDown(self):
        nbp.fetch_table, nbp.db.enabled, nbp.db.upsert = self._orig

    def test_run_aborts_when_db_disabled(self):
        nbp.db.enabled = lambda: False
        called = []
        nbp.fetch_table = lambda *a, **k: called.append(a) or []
        self.assertEqual(nbp.run(today=date(2026, 6, 24)), 0)
        self.assertEqual(called, [])  # nie sięga do sieci

    def test_run_fetches_chunks_and_upserts(self):
        nbp.db.enabled = lambda: True
        def fake_fetch(letter, start, end):
            return [{"kod": "EUR", "waluta": "euro", "data": end, "kurs": 4.25}]
        nbp.fetch_table = fake_fetch
        def fake_upsert(table, rows, on_conflict):
            self.upserts.append((table, list(rows), on_conflict))
        nbp.db.upsert = fake_upsert

        total = nbp.run(today=date(2026, 6, 24))

        # 2 kawałki (18 mies. > 367 dni) x 2 tabele (A, B) = 4 wiersze
        self.assertEqual(total, 4)
        self.assertTrue(self.upserts)
        for table, rows, on_conflict in self.upserts:
            self.assertEqual(table, "kursy_walut")
            self.assertEqual(on_conflict, "kod,data")

    def test_run_continues_on_fetch_error(self):
        nbp.db.enabled = lambda: True
        calls = {"n": 0}
        def flaky_fetch(letter, start, end):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("NBP 500")
            return [{"kod": "EUR", "waluta": "euro", "data": end, "kurs": 4.25}]
        nbp.fetch_table = flaky_fetch
        nbp.db.upsert = lambda *a, **k: None
        total = nbp.run(today=date(2026, 6, 24))
        # 4 wywołania (2 kawałki x A,B); 1 padło -> 3 udane wiersze
        self.assertEqual(total, 3)


if __name__ == "__main__":
    unittest.main()
