"""تست‌های TMDbClient: فیلترِ «واقعاً مشابه» و گرفتن فهرست ترند روز."""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.tmdb_client import TMDbClient  # noqa: E402


class StubClient(TMDbClient):
    def __init__(self, data, config=None):
        self.data = data
        self.cfg = config or {}

    def _get(self, endpoint, params=None):
        return self.data


class RecordingClient(TMDbClient):
    def __init__(self, config=None):
        self.cfg = config or {}
        self.calls = []

    def _get(self, endpoint, params=None):
        self.calls.append((endpoint, params))
        return {"page": 1, "total_pages": 1, "results": []}


class TMDbClientTests(unittest.TestCase):
    def test_similar_filters_unrelated_and_low_rating(self):
        """مرد ماهیگیرِ بی‌ربط و فیلمِ کم‌امتیاز نباید بیایند."""
        data = {"results": [
            {"id": 1, "title": "Good", "genre_ids": [18], "vote_average": 8.0,
             "vote_count": 800, "release_date": "2000-01-01"},
            {"id": 2, "title": "Fisherman", "genre_ids": [35], "vote_average": 6.5,
             "vote_count": 900, "release_date": "1990-01-01"},
            {"id": 3, "title": "Weak", "genre_ids": [18], "vote_average": 5.0,
             "vote_count": 800, "release_date": "2010-01-01"},
        ]}
        client = StubClient(data)
        out = client.movie_similar(240, genres=[18], limit=3)
        self.assertEqual([o["title"] for o in out], ["Good"])

    def test_similar_sorted_by_overlap_then_rating(self):
        """فیلمِ با ژانر مشترکِ بیشتر (حتی ریتینگ کمتر) اول می‌آید."""
        data = {"results": [
            {"id": 1, "title": "BothGenres", "genre_ids": [18, 80], "vote_average": 7.0,
             "vote_count": 800, "release_date": "2001-01-01"},
            {"id": 2, "title": "OneGenreHighRating", "genre_ids": [18], "vote_average": 9.0,
             "vote_count": 800, "release_date": "2002-01-01"},
            {"id": 3, "title": "SameId", "genre_ids": [18, 80], "vote_average": 7.5,
             "vote_count": 800, "release_date": "2003-01-01"},
        ]}
        client = StubClient(data)
        out = client.movie_similar(3, genres=[18, 80], limit=3)
        self.assertEqual([o["title"] for o in out], ["BothGenres", "OneGenreHighRating"])

    def test_similar_empty_when_no_shared_genre(self):
        client = StubClient({"results": [
            {"id": 1, "title": "Unrelated", "genre_ids": [27], "vote_average": 8.0,
             "vote_count": 900, "release_date": "2000-01-01"},
        ]})
        self.assertEqual(client.movie_similar(240, genres=[18], limit=3), [])

    def test_similar_returns_year(self):
        client = StubClient({"results": [
            {"id": 1, "title": "Good", "genre_ids": [18], "vote_average": 8.0,
             "vote_count": 800, "release_date": "1984-06-01"},
        ]})
        out = client.movie_similar(240, genres=[18], limit=3)
        self.assertEqual(out[0]["year"], 1984)

    def test_trending_returns_ids(self):
        client = StubClient({"results": [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}]})
        self.assertEqual(client.trending("week", 5), [1, 2])

    def test_trending_empty_on_error(self):
        client = StubClient({"results": []})
        self.assertEqual(client.trending("day", 5), [])

    def test_trailer_picks_official_youtube_trailer(self):
        data = {"results": [
            {"key": "teaser1", "site": "YouTube", "type": "Teaser", "official": True},
            {"key": "off1", "site": "YouTube", "type": "Trailer", "official": True, "size": 720},
            {"key": "nonoff1", "site": "YouTube", "type": "Trailer", "official": False, "size": 1080},
            {"key": "vimeo1", "site": "Vimeo", "type": "Trailer", "official": True},
        ]}
        client = StubClient(data)
        self.assertEqual(client.movie_trailer(240), "off1",
                         "اولویت با تریلر رسمی یوتیوب است (نه یوتیوب غیررسمی با وضوح بالاتر)")

    def test_trailer_none_when_no_youtube_trailer(self):
        client = StubClient({"results": [
            {"key": "teaser1", "site": "YouTube", "type": "Teaser"},
            {"key": "vimeo1", "site": "Vimeo", "type": "Trailer"},
        ]})
        self.assertIsNone(client.movie_trailer(240))

    def test_trailer_none_on_error(self):
        client = StubClient({"errors": []})
        self.assertIsNone(client.movie_trailer(240))

    def test_discover_maps_date_filters_to_primary_release_date(self):
        """بین سال باید primary_release_date.gte/lte شود؛ پارامتر نامعتبر قدیمی نباید برود."""
        client = RecordingClient()
        profile = {
            "name": "شاهکارهای کلاسیک",
            "with_genres": "18",
            "vote_average_gte": 8.0,
            "vote_count_gte": 2000,
            "release_date_gte": "1970-01-01",
            "release_date_lte": "1999-12-31",
        }
        client.discover(profile, "fa-IR", 1)
        _, params = client.calls[-1]
        self.assertEqual(params["primary_release_date.gte"], "1970-01-01")
        self.assertEqual(params["primary_release_date.lte"], "1999-12-31")
        self.assertNotIn("release_date_lte", params)
        self.assertNotIn("release_date.gte", params)
        self.assertEqual(params["vote_average.gte"], 8.0)
        self.assertEqual(params["vote_count.gte"], 2000)
        self.assertEqual(params["with_genres"], "18")

    def test_discover_respects_profile_sort_by(self):
        client = RecordingClient()
        client.discover({"sort_by": "vote_average.desc"}, "fa-IR", 1)
        self.assertEqual(client.calls[-1][1]["sort_by"], "vote_average.desc")


if __name__ == "__main__":
    unittest.main()