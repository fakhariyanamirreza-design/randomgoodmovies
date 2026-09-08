"""تست End-to-End: کل pipeline (discover → score → select → angle → build → quality → publish dry-run → memory).

TMDb به‌صورت fake جایگزین می‌شود تا بدون شبکه و بدون کلید واقعی اجرا شود.
"""

import json
import os
import sys
import tempfile
import unittest
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

    def movie_similar(self, movie_id, genres=None, language="en-US", limit=3):
        return [
            {"id": 900, "title": f"Similar {movie_id} A", "year": 2009},
            {"id": 901, "title": f"Similar {movie_id} B", "year": 2015},
        ]

    def trending(self, window="week", limit=15):
        return []

    def person_english_name(self, person_id):
        return "Denis Villeneuve"

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
        self.assertIn("hidden_gem", cfg["content"]["templates"])
        self.assertIn("highly_rated", cfg["content"]["templates"])
        for angle in cfg["angles"]["priority"]:
            self.assertIn(angle, cfg["content"]["templates"],
                          f"هیچ قالب کپشنی برای angle {angle} تعریف نشده")
        self.assertIn("diversity", cfg)
        self.assertIn("quality_gate", cfg)


if __name__ == "__main__":
    unittest.main()