"""تست End-to-End: کل pipeline (discover → score → select → angle → build → quality → publish dry-run → memory).

TMDb به‌صورت fake جایگزین می‌شود تا بدون شبکه و بدون کلید واقعی اجرا شود.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main as main_module  # noqa: E402

# --- Fake TMDb dataset ---


def _movie(id, title, fa_overview=True, rating=8.2, votes=4000, popularity=30.0,
           genre_id=18, year="2010", director="دنی ویلنوو", ex_id=None):
    return {
        "id": id, "title": title, "original_title": title, "release_date": f"{year}-01-01",
        "poster_path": f"/p{id}.jpg", "vote_average": rating, "vote_count": votes,
        "popularity": popularity,
        "genres": [{"id": genre_id, "name": "درام"}],
        "runtime": 130,
        "overview": f"خلاصه‌ی فارسی فیلم {title}." if fa_overview else "",
        "production_countries": [{"iso_3166_1": "CA", "name": "Canada"}],
        "credits": {"crew": [{"job": "Director", "name": director, "id": 1001}]},
        "external_ids": {"imdb_id": ex_id or f"tt{id}"},
    }


class FakeTMDbClient:
    def __init__(self, *a, **k):
        pass

    def discover(self, profile, language, page, sort_by="popularity.desc", exclude_adult="false"):
        # دو فیلم: یکی درام، یکی اکشن، یکی بدون overview فارسی
        return {
            "total_pages": 1,
            "results": [
                {"id": 1, "title": "درام یک", "release_date": "2010-01-01", "poster_path": "/p1.jpg"},
                {"id": 2, "title": "اکشن یک", "release_date": "2015-01-01", "poster_path": "/p2.jpg"},
                {"id": 3, "title": "بدون خلاصه", "release_date": "2012-01-01", "poster_path": "/p3.jpg"},
            ],
        }

    def movie_details(self, movie_id, language):
        if language != "fa-IR":
            return _movie(movie_id, f"EN{movie_id}", fa_overview=False, ex_id=f"tt{movie_id}")
        if movie_id == 3:
            return _movie(3, "بدون خلاصه", fa_overview=False)
        if movie_id == 1:
            return _movie(1, "درام یک", rating=8.9, votes=8000, genre_id=18, director="ویلنوو")
        return _movie(2, "اکشن یک", rating=8.0, votes=2500, genre_id=28, director="نولان")

    def movie_images(self, movie_id):
        return {"posters": [{"file_path": f"/pp{movie_id}.jpg", "vote_average": 5.0}]}

    def movie_keywords(self, movie_id):
        return ["شناخته_شده", "cannes"]

    def movie_trailer(self, movie_id):
        return f"trailer_{movie_id}"

    def movie_similar(self, movie_id, genres=None, language="en-US", limit=3):
        return [
            {"id": 900, "title": f"Similar {movie_id} A", "year": 2009},
            {"id": 901, "title": f"Similar {movie_id} B", "year": 2015},
        ]

    def trending(self, window="week", limit=15):
        return []

    def person_english_name(self, person_id):
        return "Denis Villeneuve"

    def person_birthday(self, person_id):
        return "1959-01-01"

    def person_imdb_id(self, person_id):
        return "nm0898288"


class PipelineTempEnvironment:
    """دایرکتوری temp با config و history برای هر تست."""

    def __init__(self):
        self.dir = tempfile.mkdtemp()

    def history_path(self):
        return os.path.join(self.dir, "posted.json")

    def write_config(self, cfg):
        with open(os.path.join(self.dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)


def real_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.env = PipelineTempEnvironment()

    def test_full_pipeline_publishes_and_records_memory(self):
        cfg = real_config()
        cfg["posting"]["dry_run"] = True
        self.env.write_config(cfg)

        with mock.patch.object(main_module, "TMDbClient", FakeTMDbClient):
            old_config = main_module.CONFIG_PATH
            old_history = main_module.HISTORY_PATH
            main_module.CONFIG_PATH = os.path.join(self.env.dir, "config.json")
            main_module.HISTORY_PATH = self.env.history_path()
            try:
                with mock.patch.dict(os.environ, {
                    "TMDB_API_KEY": "fake",
                    "TELEGRAM_BOT_TOKEN": "fake",
                    "TELEGRAM_CHANNEL_ID": "@fake",
                }, clear=False):
                    main_module.main()
            finally:
                main_module.CONFIG_PATH = old_config
                main_module.HISTORY_PATH = old_history

        with open(self.env.history_path(), encoding="utf-8") as f:
            history = json.load(f)
        self.assertEqual(len(history["posted"]), 1)
        entry = history["posted"][0]
        self.assertEqual(entry["status"], "published")
        self.assertTrue(entry["id"] in (1, 2, 3))
        self.assertIn("editorial_angle", entry)
        self.assertIn("score_breakdown", entry)
        self.assertIn("caption", entry)
        self.assertIn("genres", entry)
        self.assertIn("فیلم‌های شبیه به این", entry["caption"])

    def test_no_publish_when_all_rejected_by_quality(self):
        cfg = real_config()
        cfg["posting"]["dry_run"] = True
        # همه‌ی اعتبارات را پایین بگذار تا گیت کیفیت رد کند
        cfg["quality_gate"]["min_rating"] = 9.5
        self.env.write_config(cfg)

        with mock.patch.object(main_module, "TMDbClient", FakeTMDbClient):
            old_config = main_module.CONFIG_PATH
            old_history = main_module.HISTORY_PATH
            main_module.CONFIG_PATH = os.path.join(self.env.dir, "config.json")
            main_module.HISTORY_PATH = self.env.history_path()
            try:
                with mock.patch.dict(os.environ, {
                    "TMDB_API_KEY": "fake",
                    "TELEGRAM_BOT_TOKEN": "fake",
                    "TELEGRAM_CHANNEL_ID": "@fake",
                }, clear=False):
                    with self.assertRaises(SystemExit) as ctx:
                        main_module.main()
            finally:
                main_module.CONFIG_PATH = old_config
                main_module.HISTORY_PATH = old_history

        self.assertEqual(ctx.exception.code, 0)
        self.assertFalse(os.path.exists(self.env.history_path()), "چیزی publish نشده پس history نباید ساخته شود")

    def test_exits_cleanly_when_no_selection(self):
        cfg = real_config()
        cfg["posting"]["dry_run"] = True
        # کاندیداها را با unscorable داده پر کنیم (پس از عملیات diversity همه رد)
        self.env.write_config(cfg)

        class EmptyFake(FakeTMDbClient):
            def discover(self, *a, **k):
                return {"total_pages": 1, "results": []}

        with mock.patch.object(main_module, "TMDbClient", EmptyFake):
            old_config = main_module.CONFIG_PATH
            main_module.CONFIG_PATH = os.path.join(self.env.dir, "config.json")
            try:
                with mock.patch.dict(os.environ, {
                    "TMDB_API_KEY": "fake",
                    "TELEGRAM_BOT_TOKEN": "fake",
                    "TELEGRAM_CHANNEL_ID": "@fake",
                }, clear=False):
                    with self.assertRaises(SystemExit) as ctx:
                        main_module.main()
            finally:
                main_module.CONFIG_PATH = old_config

        self.assertEqual(ctx.exception.code, 0)
        self.assertFalse(os.path.exists(self.env.history_path()))

    def test_real_config_has_required_keys(self):
        cfg = real_config()
        w = cfg["scoring"]["weights"]
        self.assertAlmostEqual(sum(w.values()), 1.0, places=4)
        self.assertTrue(set(w).issuperset({
            "quality", "novelty", "category_diversity", "genre_diversity",
            "director_diversity", "era_diversity", "popularity", "surprise",
        }))
        self.assertIn("trending", w)
        content = cfg["content"]
        # هر angle یا قالب اختصاصی دارد یا default_template به عنوان fallback
        self.assertTrue(content.get("default_template"), "default_template باید تعریف شود")
        self.assertIn(content["default_template"], content["templates"])
        for angle in cfg["angles"]["priority"]:
            self.assertTrue(
                angle in content["templates"] or content.get("default_template") in content["templates"],
                f"هیچ قالب کپشنی برای angle {angle} تعریف نشده")
        self.assertIn("diversity", cfg)
        self.assertIn("quality_gate", cfg)
        # پیکربندی تریلر باید placeholderهای لازم را داشته باشد
        trailer_caption = cfg["trailer"]["caption"]
        self.assertIn("{title_fa}", "".join(trailer_caption))
        self.assertIn("{post_link}", "".join(trailer_caption))
        self.assertGreaterEqual(int(cfg["trailer"]["after_days"]), 1)

    def test_trailer_publish_flow_for_stale_posts(self):
        """پست معرفیِ قدیمی‌تر از after_days باید تریلرِ خود را به‌صورت پست جدا منتشر کند."""
        from src.publisher import TelegramPublisher
        from src.tmdb_client import TMDbClient
        from main import publish_pending_trailers, build_trailer_caption

        cfg = real_config()
        cfg["trailer"]["after_days"] = 1
        cfg["posting"]["dry_run"] = True
        now = datetime.now(timezone.utc)

        history = {"posted": [
            {
                "id": 7, "title": "قدیمی", "title_fa": "قدیمی", "title_en": "Old",
                "status": "published", "message_id": 123,
                "poster": "/p7.jpg",
                "posted_at": (now - timedelta(days=3)).isoformat(),
            },
            {
                "id": 8, "title": "تازه", "title_fa": "تازه", "title_en": "New",
                "status": "published", "message_id": 124,
                "poster": "/p8.jpg",
                "posted_at": now.isoformat(),
            },
        ]}

        class RecordingTrailerClient(FakeTMDbClient):
            def __init__(self, *a, **k):
                self.trailer_calls = []

            def movie_trailer(self, movie_id):
                self.trailer_calls.append(movie_id)
                return f"tr{movie_id}"

        client = RecordingTrailerClient()
        publisher = TelegramPublisher("fake", "@fake", cfg)

        count = publish_pending_trailers(client, publisher, cfg, history, now=now)
        self.assertEqual(count, 1, "فقط پست ۳ روزِ قدیمی باید تریلر بگیرد")
        self.assertEqual(client.trailer_calls, [7])
        self.assertIn("trailer_posted_at", history["posted"][0])
        self.assertNotIn("trailer_posted_at", history["posted"][1])

        # لینک پست معرفی و اسم فیلم در کپشن تریلر آمده
        caption = build_trailer_caption(
            cfg, history["posted"][0], "tr7", "https://t.me/@RandomGoodMovies/123")
        self.assertIn("قدیمی", caption)
        self.assertIn("https://t.me/@RandomGoodMovies/123", caption)
        self.assertIn("عضو", caption)


if __name__ == "__main__":
    unittest.main()