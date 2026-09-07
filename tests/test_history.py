"""تست‌های History / حافظه: شمارش، streak، آخرین استفاده، duplicate detection."""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.history import HistoryMemory, counts_in_window, max_consecutive  # noqa: E402
from tests.helpers import base_config, base_history  # noqa: E402


def _post(i, profile="درام‌های جایزه‌گرفته", genres=(18,), director="دنی ویلنوو", era="2010s"):
    return {
        "id": i,
        "title": f"Film{i}",
        "profile": profile,
        "genres": list(genres),
        "director": director,
        "era": era,
        "posted_at": f"2026-09-{i:02d}T10:00:00+00:00",
    }


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.config = base_config()

    def test_genre_counts_in_window(self):
        history = base_history([
            _post(1, genres=(18,)),
            _post(2, genres=(28,)),
            _post(3, genres=(18,)),
        ])
        mem = HistoryMemory(history, self.config)
        counts = mem.genre_counts(5)
        self.assertEqual(counts.get(18), 2)
        self.assertEqual(counts.get(28), 1)

    def test_director_counts(self):
        history = base_history([
            _post(1, director="نولان"),
            _post(2, director="نولان"),
            _post(3, director="ویلنوو"),
        ])
        mem = HistoryMemory(history, self.config)
        self.assertEqual(mem.director_counts(5).get("نولان"), 2)

    def test_max_consecutive_dimension(self):
        posts = [_post(1, profile="A"), _post(2, profile="A"),
                 _post(3, profile="B"), _post(4, profile="A")]
        # از انتهای لیست: A شمارش می‌شود تا اولین مقدار متفاوت
        self.assertEqual(max_consecutive(posts, "profile", "A"), 1)
        # B در انتها نیست
        self.assertEqual(max_consecutive(posts, "profile", "B"), 0)
        # طول بلندترین رشته‌ی کلی: A-A = 2
        self.assertEqual(max_consecutive(posts, "profile"), 2)

    def test_is_published(self):
        history = base_history([_post(1)])
        mem = HistoryMemory(history, self.config)
        self.assertTrue(mem.is_published(1))
        self.assertFalse(mem.is_published(2))

    def test_last_use(self):
        history = base_history([
            _post(5, profile="A"),
            _post(6, profile="B"),
        ])
        mem = HistoryMemory(history, self.config)
        self.assertEqual(mem.last_use("profile", "B"), "2026-09-06T10:00:00+00:00")
        self.assertIsNone(mem.last_use("profile", "C"))


if __name__ == "__main__":
    unittest.main()