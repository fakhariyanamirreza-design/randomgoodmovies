"""تست‌های انتخاب پوستر اصلی: اولویت en → images → fa (دقیقاً همان پوستر TMDb/IMDb)."""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.discovery import CandidateDiscovery, _best_poster_from_images, pick_poster, build_candidate  # noqa: E402
from tests.helpers import base_config, base_history  # noqa: E402


def _details(poster=None, language="en"):
    return {"poster_path": poster, "overview": "overview", "title": f"T{language}"}


class BuildCandidateTests(unittest.TestCase):
    def setUp(self):
        self.cfg = base_config()

    def test_countries_iso_extracted_from_fa_details(self):
        details_fa = {
            "id": 7, "title": "هفت", "overview": "خ.", "vote_average": 8.0,
            "vote_count": 100, "popularity": 5, "genres": [],
            "release_date": "2010-01-01", "runtime": 120,
            "production_countries": [{"iso_3166_1": "US", "name": "United States of America"}],
        }
        cand = build_candidate("درام‌های جایزه‌گرفته", self.cfg["profiles"][0],
                               {"id": 7}, details_fa, {"title": "Seven"},
                               2010, director=None, imdb_id=None, poster_path=None)
        self.assertEqual(cand["countries_iso"], ["US"])
        self.assertEqual(cand["countries_fa"], ["آمریکا"])

    def test_countries_iso_empty_when_absent(self):
        cand = build_candidate("درام‌های جایزه‌گرفته", self.cfg["profiles"][0],
                               {"id": 8}, {"id": 8, "title": "X", "genres": []},
                               {"title": "X"}, 2010)
        self.assertEqual(cand["countries_iso"], [])
        self.assertEqual(cand["countries_fa"], [])


class PosterTests(unittest.TestCase):
    def test_en_poster_preferred_over_fa_localized(self):
        # fa یک پوستر محلی‌سازی‌شده دارد ولی en اصلی: باید en برنده باشد
        result = pick_poster(
            details_fa={"poster_path": "/localized_fa.jpg"},
            details_en={"poster_path": "/canonical_en.jpg"},
        )
        self.assertEqual(result, "/canonical_en.jpg")

    def test_uses_best_from_images_when_no_en_poster(self):
        result = pick_poster(
            details_fa={"poster_path": "/fa.jpg"},
            details_en={"poster_path": None},
            images_data={"posters": [{"file_path": "/best.jpg", "vote_count": 500, "vote_average": 5.6}]},
        )
        self.assertEqual(result, "/best.jpg")

    def test_fa_poster_is_last_resort(self):
        self.assertEqual(
            pick_poster({"poster_path": "/fa.jpg"}, {"poster_path": None}, images_data=None),
            "/fa.jpg",
        )

    def test_no_poster_anywhere_gives_none(self):
        self.assertIsNone(pick_poster({"poster_path": None}, {"poster_path": None}, images_data=None))

    def test_best_from_images_picks_highest_vote_count(self):
        data = {"posters": [
            {"file_path": "/low_votes.jpg", "vote_count": 10, "vote_average": 9.0},
            {"file_path": "/main_poster.jpg", "vote_count": 1000, "vote_average": 5.0},
            {"file_path": "/mid.jpg", "vote_count": 500, "vote_average": 6.0},
        ]}
        self.assertEqual(_best_poster_from_images(data), "/main_poster.jpg")

    def test_best_from_images_tiebreak_by_vote_average(self):
        data = {"posters": [
            {"file_path": "/a.jpg", "vote_count": 100, "vote_average": 6.0},
            {"file_path": "/b.jpg", "vote_count": 100, "vote_average": 7.0},
        ]}
        self.assertEqual(_best_poster_from_images(data), "/b.jpg")

    def test_resolve_poster_skips_images_call_when_en_present(self):
        class CountingClient:
            def __init__(self):
                self.calls = 0

            def movie_images(self, movie_id):
                self.calls += 1
                return {"posters": [{"file_path": "/x.jpg", "vote_count": 1}]}

        client = CountingClient()
        discovery = CandidateDiscovery(client, base_config(), base_history())
        result = discovery._resolve_poster(
            1,
            details_fa={"poster_path": "/fa.jpg"},
            details_en={"poster_path": "/en.jpg"},
        )
        self.assertEqual(result, "/en.jpg")
        self.assertEqual(client.calls, 0, "با وجود پوستر en نباید به images endpoint درخواست بدهد")

    def test_resolve_poster_calls_images_to_avoid_localized_fa(self):
        # فقط پوستر fa (محلی) هست: حتی بدون en، باید images امتحان شود تا پوستر اصلی برنده شود
        class CountingClient:
            def __init__(self):
                self.calls = 0

            def movie_images(self, movie_id):
                self.calls += 1
                return {"posters": [{"file_path": "/from_images.jpg", "vote_count": 5}]}

        client = CountingClient()
        discovery = CandidateDiscovery(client, base_config(), base_history())
        result = discovery._resolve_poster(
            1,
            details_fa={"poster_path": "/fa.jpg"},
            details_en={"poster_path": None},
        )
        self.assertEqual(result, "/from_images.jpg")
        self.assertEqual(client.calls, 1)

    def test_resolve_poster_falls_back_to_fa_when_images_empty(self):
        class EmptyImagesClient:
            def movie_images(self, movie_id):
                return {"posters": []}

        discovery = CandidateDiscovery(EmptyImagesClient(), base_config(), base_history())
        result = discovery._resolve_poster(
            1,
            details_fa={"poster_path": "/fa.jpg"},
            details_en={"poster_path": None},
        )
        self.assertEqual(result, "/fa.jpg")


def test_trending_movies_added_to_pool_and_marked(self):
        class TrendingClient:
            def __init__(self):
                self.added = 0

            def discover(self, *a, **k):
                return {"total_pages": 1, "results": []}

            def trending(self, window="week", limit=15):
                return [555]

            def movie_details(self, movie_id, language):
                if language != "fa-IR":
                    return {"title": "EN", "poster_path": "/en.jpg", "overview": "x",
                            "credits": {}, "external_ids": {"imdb_id": "tt555"},
                            "genres": [], "release_date": "2010-01-01", "runtime": 120}
                return {"title": "فیلم ترند", "poster_path": "/fa.jpg",
                        "overview": "خلاصه فارسی ترند.", "vote_average": 7.5,
                        "vote_count": 8000, "popularity": 50, "genres": [],
                        "release_date": "2010-06-01", "runtime": 120}

            def movie_images(self, movie_id):
                return {"posters": [{"file_path": "/p.jpg"}]}

        cfg = base_config()
        cfg["trending"] = {"enabled": True, "limit": 5}
        discovery = CandidateDiscovery(TrendingClient(), cfg, base_history())
        cands, _ex, stats = discovery.discover()
        self.assertEqual(stats["trending_found"], 1)
        self.assertTrue(any(c["trending"] and c["profile"] == "ترند روز" for c in cands),
                        "فیلم ترند باید به pool اضافه و tagged شود")


class TrendingDiscoveryTests(unittest.TestCase):
    def test_trending_movies_added_to_pool_and_marked(self):
        class TrendingClient:
            def __init__(self):
                self.added = 0

            def discover(self, *a, **k):
                return {"total_pages": 1, "results": []}

            def trending(self, window="week", limit=15):
                return [555]

            def movie_details(self, movie_id, language):
                if language != "fa-IR":
                    return {"title": "EN", "poster_path": "/en.jpg", "overview": "x",
                            "credits": {}, "external_ids": {"imdb_id": "tt555"},
                            "genres": [], "release_date": "2010-01-01", "runtime": 120}
                return {"title": "فیلم ترند", "poster_path": "/fa.jpg",
                        "overview": "خلاصه فارسی ترند.", "vote_average": 7.5,
                        "vote_count": 8000, "popularity": 50, "genres": [],
                        "release_date": "2010-06-01", "runtime": 120}

            def movie_images(self, movie_id):
                return {"posters": [{"file_path": "/p.jpg"}]}

        cfg = base_config()
        cfg["trending"] = {"enabled": True, "limit": 5}
        discovery = CandidateDiscovery(TrendingClient(), cfg, base_history())
        cands, _ex, stats = discovery.discover()
        self.assertEqual(stats["trending_found"], 1)
        self.assertTrue(any(c["trending"] and c["profile"] == "ترند روز" for c in cands),
                        "فیلم ترند باید به pool اضافه و tagged شود")


if __name__ == "__main__":
    unittest.main()