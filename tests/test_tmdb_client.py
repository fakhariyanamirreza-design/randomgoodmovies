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


if __name__ == "__main__":
    unittest.main()