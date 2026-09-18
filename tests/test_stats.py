"""تست‌های src.stats (اسلأم ۴): توزیع‌ها، فیلتر پنجره‌ی زمانی و حالت‌های خالی."""

import sys
import os
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.stats import compute_stats, distribution, genre_names, render_text  # noqa: E402


def _days_ago_iso(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _post(i, days, profile="درام‌های جایزه‌گرفته", director="ویلنوو", era="2010s",
          genre_ids=(18,), gnames=("درام",), status="published"):
    return {
        "id": i, "title": f"F{i}", "profile": profile, "director": director,
        "era": era, "genres": list(genre_ids), "genre_names_fa": list(gnames),
        "status": status, "posted_at": _days_ago_iso(days),
    }


class StatsTests(unittest.TestCase):
    def test_compute_stats_window_counts(self):
        posts = [
            _post(1, 3, "A", "D1", "2010s", (18, 35), ("درام", "کمدی")),
            _post(2, 10, "A", "D1", "2010s", (18,), ("درام",)),
            _post(3, 40, "B", "D2", "1990s", (28,), ("اکشن",)),   # خارج از ۳۰ روز
            _post(4, 5, "B", "D2", "2010s", (35,), ("کمدی",),
                  status="publish_failed"),                       # منتشرنشده → حذف
        ]
        stats = compute_stats({"posted": posts, "monthly_lists": []})

        s30 = stats["30"]
        self.assertEqual(s30["count"], 2)          # فقط ۱ و ۲
        self.assertEqual(s30["genres"].get("درام"), 2)
        self.assertEqual(s30["genres"].get("کمدی"), 1)
        self.assertEqual(s30["categories"].get("A"), 2)
        self.assertEqual(s30["directors"].get("D1"), 2)

        s7 = stats["7"]
        self.assertEqual(s7["count"], 1)           # فقط ۱
        self.assertEqual(s7["genres"].get("درام"), 1)
        self.assertEqual(s7["categories"].get("A"), 1)

    def test_distribution_sort_desc(self):
        posts = [_post(1, 3, gnames=("درام",)), _post(2, 3, gnames=("کمدی",)),
                 _post(3, 3, gnames=("درام",))]
        dist = distribution(posts, lambda p: p["genre_names_fa"])
        self.assertEqual(list(dist.items()), [("درام", 2), ("کمدی", 1)])

    def test_distribution_skips_empty(self):
        posts = [_post(1, 3, director=None), _post(2, 3, director="X")]
        dist = distribution(posts, lambda p: [p["director"]])
        self.assertEqual(dist, {"X": 1})

    def test_genre_names_fallback_to_fa_map(self):
        entry = {"genres": [10749], "genre_names_fa": None}
        self.assertEqual(genre_names(entry), ["عاشقانه"])

    def test_render_text_readable(self):
        stats = compute_stats({"posted": [_post(1, 2)], "monthly_lists": []})
        text = render_text(stats)
        self.assertIn("ژانر", text)
        self.assertIn("آخرین 30 روز", text)
        self.assertIn("درام", text)


if __name__ == "__main__":
    unittest.main()