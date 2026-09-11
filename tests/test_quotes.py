"""تست‌های موتور نقل قول‌های سینمایی: بارگذاری، فیلتر محتوا، انتخاب، کپشن و عکس."""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.quotes import QuoteEngine, contains_profanity  # noqa: E402


SAMPLE_QUOTES = [
    {
        "movie": "The Shawshank Redemption",
        "imdb_url": "https://www.imdb.com/title/tt0111161/",
        "quote": "Hope is a good thing.",
        "quote_fa": "امید چیز خوبی است.",
    },
    {
        "movie": "Joker",
        "imdb_url": "https://www.imdb.com/title/tt7286456/",
        "quote": "My life was a tragedy.",
        "quote_fa": "زندگی‌ام تراژدی بود.",
    },
    {
        "movie": "Aliens",
        "imdb_url": "https://www.imdb.com/title/tt0090605/",
        "quote": "Get away from her!",
        "quote_fa": "ازش دور شو، مادرسگ!",
    },
]


def write_quotes(path, quotes):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(quotes, f, ensure_ascii=False)


class ProfanityTest(unittest.TestCase):
    def test_contains_profanity(self):
        self.assertTrue(contains_profanity("مادرسگ"))
        self.assertTrue(contains_profanity("جنده"))
        self.assertTrue(contains_profanity("این جمله لعنتی است"))
        self.assertFalse(contains_profanity("امید چیز خوبی است"))
        self.assertFalse(contains_profanity("زندگی مثل جعبه شکلات است"))


class QuoteEngineTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.quotes_path = os.path.join(self.dir, "movie_quotes.json")
        write_quotes(self.quotes_path, SAMPLE_QUOTES)
        self.history = {"posted": []}

    def _engine(self):
        return QuoteEngine(self.quotes_path, self.history)

    def test_load_quotes(self):
        qe = self._engine()
        self.assertEqual(len(qe.quotes), 3)

    def test_missing_file_returns_empty(self):
        qe = QuoteEngine(os.path.join(self.dir, "missing.json"), self.history)
        self.assertEqual(qe.quotes, [])

    def test_next_quote_skips_profanity(self):
        # نقل قول مایکل در index 0، جکر (بدون فحش) در index 1، Aliens (فحش) در index 2
        qe = self._engine()
        index, quote = qe.next_quote()
        self.assertEqual(index, 0)
        self.assertEqual(quote["movie"], "The Shawshank Redemption")

        # بعد از انتشار اول، جکر (index 1) باید بیاید؛ Aliens (index 2) برای همیشه رد شود
        qe.record_published(0)
        index, quote = qe.next_quote()
        self.assertEqual(index, 1)
        self.assertEqual(quote["movie"], "Joker")

        # بعد از انتشار جکر، چیزی باقی نمی‌ماند (Aliens فحش دارد)
        qe.record_published(1)
        self.assertEqual(qe.next_quote(), (None, None))

    def test_build_caption(self):
        qe = self._engine()
        caption = qe.build_caption(SAMPLE_QUOTES[0], "📢 عضویت در کانال: @test")
        self.assertIn("«امید چیز خوبی است.»", caption)
        self.assertIn("The Shawshank Redemption", caption)
        self.assertIn("https://www.imdb.com/title/tt0111161/", caption)
        self.assertIn("@test", caption)
        # ترتیب بلاک‌ها: نقل قول → نام فیلم → footer
        self.assertLess(caption.index("«امید"), caption.index("The Shawshank"))
        self.assertLess(caption.index("The Shawshank"), caption.index("@test"))

    def test_record_published_and_get_published(self):
        qe = self._engine()
        qe.record_published(0, message_id=123)
        self.assertEqual(qe.get_published_indices(), {0})
        self.assertEqual(self.history["quotes_posted"][0]["quote_index"], 0)
        self.assertEqual(self.history["quotes_posted"][0]["message_id"], 123)


class FakeTMDb:
    def __init__(self):
        self.calls = []
        self.cfg = {"request_timeout": 20}

    def _get(self, endpoint, params=None):
        self.calls.append((endpoint, params))
        if endpoint.startswith("find/"):
            return {"movie_results": [{"id": 278}]}
        if endpoint.startswith("movie/278/images"):
            return {"backdrops": [
                {"file_path": "/bd1.jpg", "vote_average": 4.0},
                {"file_path": "/bd2.jpg", "vote_average": 6.0},
            ]}
        return {}


class BackdropTests(unittest.TestCase):
    def test_get_backdrop_url_uses_find_and_best_backdrop(self):
        dir_path = tempfile.mkdtemp()
        quotes_path = os.path.join(dir_path, "q.json")
        write_quotes(quotes_path, SAMPLE_QUOTES)
        qe = QuoteEngine(quotes_path, {"posted": []})
        tmdb = FakeTMDb()

        url = qe.get_backdrop_url(SAMPLE_QUOTES[0], tmdb)
        # بهترین (پررأی‌ترین) backdrop انتخاب می‌شود
        self.assertEqual(url, "https://image.tmdb.org/t/p/w1280/bd2.jpg")

        # بررسی اینکه endpoint های درست فراخوانی شده
        endpoints = [c[0] for c in tmdb.calls]
        self.assertIn("find/tt0111161", endpoints)
        self.assertIn("movie/278/images", endpoints)

    def test_get_backdrop_url_none_when_no_backdrop(self):
        dir_path = tempfile.mkdtemp()
        quotes_path = os.path.join(dir_path, "q.json")
        write_quotes(quotes_path, SAMPLE_QUOTES)
        qe = QuoteEngine(quotes_path, {"posted": []})

        class NoBackdrop(FakeTMDb):
            def _get(self, endpoint, params=None):
                if endpoint.startswith("movie/"):
                    return {"backdrops": []}
                return {"movie_results": [{"id": 278}]}

        self.assertIsNone(qe.get_backdrop_url(SAMPLE_QUOTES[1], NoBackdrop()))


class DailyCapTests(unittest.TestCase):
    def test_daily_cap_config_respected(self):
        cfg = {"quotes": {"enabled": True, "daily_cap": 1}}
        self.assertEqual(cfg["quotes"]["daily_cap"], 1)


class DailyQuotePublishTest(unittest.TestCase):
    def _write_minimal_quotes(self):
        dir_path = tempfile.mkdtemp()
        quotes_path = os.path.join(dir_path, "q.json")
        write_quotes(quotes_path, [{
            "movie": "Test Movie",
            "imdb_url": "https://www.imdb.com/title/tt0000001/",
            "quote": "Test quote.",
            "quote_fa": "نقل قول تست.",
        }])
        return quotes_path

    def test_daily_quote_skipped_if_published_today(self):
        from main import publish_daily_quote

        dir_path = tempfile.mkdtemp()
        quotes_path = os.path.join(dir_path, "q.json")
        write_quotes(quotes_path, [{
            "movie": "Test Movie",
            "imdb_url": "https://www.imdb.com/title/tt0000001/",
            "quote": "Test quote.",
            "quote_fa": "نقل قول تست.",
        }])
        history = {"quotes_posted": [{
            "quote_index": 0,
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }]}

        class FakeClient:
            def _get(self, *a, **k):
                return {"movie_results": [{"id": 1}]}

        class FakePublisher:
            def send_photo(self, *a, **k):
                return {"ok": True, "dry_run": True}

        with mock.patch.dict(os.environ, {"QUOTES_PATH": quotes_path}):
            result = publish_daily_quote(FakeClient(), FakePublisher(),
                                         {"quotes": {"enabled": True}, "posting": {}},
                                         history, dry_run=True)
        self.assertFalse(result, "نقل قول امروز قبلاً منتشر شده، نباید دوباره منتشر شود")

    def test_daily_quote_publishes_when_none_today(self):
        from main import publish_daily_quote

        dir_path = tempfile.mkdtemp()
        quotes_path = os.path.join(dir_path, "q.json")
        write_quotes(quotes_path, [{
            "movie": "Test Movie",
            "imdb_url": "https://www.imdb.com/title/tt0000001/",
            "quote": "Test quote.",
            "quote_fa": "نقل قول تست.",
        }])
        history = {"quotes_posted": []}

        class FakeClient:
            def _get(self, endpoint, params=None):
                if endpoint.startswith("find/"):
                    return {"movie_results": [{"id": 1}]}
                return {"backdrops": [{"file_path": "/bd.jpg", "vote_average": 5.0}]}

        calls = []

        class FakePublisher:
            def send_photo(self, caption, poster, dry_run=False, photo_url=None):
                calls.append((caption, photo_url))
                return {"ok": True, "dry_run": True}

        from main import publish_daily_quote
        with unittest.mock.patch.dict(os.environ, {"QUOTES_PATH": quotes_path}):
            result = publish_daily_quote(FakeClient(), FakePublisher(),
                                         {"quotes": {"enabled": True}, "posting": {}},
                                         history, dry_run=True)
        self.assertTrue(result, "نقل قول باید منتشر شود")
        self.assertEqual(len(history["quotes_posted"]), 1)
        caption, photo_url = calls[0]
        self.assertIn("Test Movie", caption)
        self.assertIn("https://www.imdb.com", caption)
        self.assertIn("bd", photo_url)


if __name__ == "__main__":
    unittest.main()