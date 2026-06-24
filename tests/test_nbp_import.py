# tests/test_nbp_import.py
# -*- coding: utf-8 -*-
import unittest
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


if __name__ == "__main__":
    unittest.main()
