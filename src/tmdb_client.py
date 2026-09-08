"""کلاینت TMDb با timeout، retry محدود، رعایت rate limit و handling خطا."""

import time

import requests

from .common import GENRE_FA, country_names_fa  # noqa: F401 (country_names_fa باز-export برای discovery)


class TMDbError(Exception):
    pass


class TMDbClient:
    def __init__(self, api_key, config=None):
        if not api_key:
            raise TMDbError("TMDB_API_KEY تنظیم نشده است.")
        self.api_key = api_key
        cfg = config or {}
        self.base_url = cfg.get("base_url", "https://api.themoviedb.org/3")
        self.timeout = cfg.get("request_timeout", 20)
        self.max_retries = cfg.get("max_retries", 2)
        self.backoff = cfg.get("retry_backoff_seconds", 2.0)
        self.rate_limit_sleep = cfg.get("rate_limit_sleep_seconds", 0.3)
        self.cfg = cfg

    def _get(self, endpoint, params=None):
        params = dict(params or {})
        params["api_key"] = self.api_key
        url = f"{self.base_url}/{endpoint}"
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                r = requests.get(url, params=params, timeout=self.timeout)
                if r.status_code == 429 or r.status_code >= 500:
                    # rate limit یا خطای سرور: retry با backoff محدود
                    last_error = TMDbError(f"TMDb خطای سرور/rate-limit: {r.status_code}")
                    time.sleep(self.backoff * (attempt + 1))
                    continue
                r.raise_for_status()
                time.sleep(self.rate_limit_sleep)
                return r.json()
            except requests.Timeout:
                last_error = TMDbError("timeout در درخواست به TMDb")
                time.sleep(self.backoff * (attempt + 1))
            except requests.RequestException as exc:
                last_error = TMDbError(f"خطای شبکه در TMDb: {exc}")
                if attempt < self.max_retries:
                    time.sleep(self.backoff * (attempt + 1))
        raise last_error

    def discover(self, profile, language, page=1, sort_by="popularity.desc", exclude_adult="false"):
        params = {
            "language": language,
            "sort_by": sort_by,
            "include_adult": exclude_adult,
            "page": page,
        }
        for key in ("with_genres", "vote_average_gte", "vote_count_gte",
                    "release_date_gte", "release_date_lte"):
            if key in profile:
                tmdb_param = key.replace("_gte", ".gte")
                params[tmdb_param] = profile[key]
        return self._get("discover/movie", params)

    def movie_details(self, movie_id, language):
        return self._get(f"movie/{movie_id}", {
            "language": language,
            "append_to_response": "credits,external_ids",
        })

    def movie_images(self, movie_id):
        return self._get(f"movie/{movie_id}/images", {"include_image_language": "null,en"})

    def movie_keywords(self, movie_id):
        data = self._get(f"movie/{movie_id}/keywords")
        return [k.get("name") for k in data.get("keywords", [])]

    def movie_similar(self, movie_id, genres=None, language="en-US", limit=3):
        """۳ فیلم واقعاً مشابه از /movie/{id}/similar (رایگان است).

        برای جلوگیری از پیشنهادهای عجیب (مثل مرد ماهیگیر برای پدرخوانده) فیلترهای ساده:
         - وقتی genres فیلم اصلی داده شده، نتیجه باید حداقل یک ژانر مشترک داشته باشد.
         - امتیاز و تعداد رأی کمتر از floor نباشد (پیشنهادهای کم‌اعتبار حذف شوند).
        سپس بر اساس (تعداد ژانر مشترک، امتیاز، تعداد رأی) مرتب و top-limit برمی‌گردد.

        برمی‌گرداند: list[dict{id, title, year}] — در صورت خطا/خالی بودن [].
        """
        try:
            data = self._get(f"movie/{movie_id}/similar", {"language": language})
        except TMDbError:
            return []
        genres = set(genres or [])
        min_rating = float(self.cfg.get("similar_min_rating", 6.0))
        min_vote_count = int(self.cfg.get("similar_min_vote_count", 100))

        def _overlap(item):
            return len(genres & set(item.get("genre_ids") or []))

        pool = []
        for item in (data.get("results") or []):
            if item.get("id") == movie_id:
                continue
            if genres and _overlap(item) == 0:
                continue
            if float(item.get("vote_average") or 0) < min_rating:
                continue
            if int(item.get("vote_count") or 0) < min_vote_count:
                continue
            pool.append(item)

        pool.sort(key=lambda it: (_overlap(it), it.get("vote_average", 0), it.get("vote_count", 0)),
                  reverse=True)
        out = []
        for item in pool[:limit]:
            year = None
            rd = item.get("release_date") or ""
            try:
                if rd:
                    year = int(rd[:4])
            except ValueError:
                year = None
            out.append({"id": item.get("id"), "title": item.get("title"), "year": year})
        return out

    def trending(self, window="week", limit=15):
        """فیلم‌های ترندِ حالِ حاضر TMDb (رایگان، بدون LLM) برای منبع اضافی کاندیدا.

        برمی‌گرداند: list[int] از tmdb_id — در صورت خطا/خالی بودن [].
        """
        try:
            data = self._get(f"trending/movie/{window}", {"language": "en-US"})
        except TMDbError:
            return []
        return [m.get("id") for m in (data.get("results") or [])[:limit] if m.get("id")]

    def person_imdb_id(self, person_id):
        try:
            return self._get(f"person/{person_id}/external_ids").get("imdb_id")
        except TMDbError:
            return None

    def person_english_name(self, person_id):
        try:
            return self._get(f"person/{person_id}", {"language": "en-US"}).get("name")
        except TMDbError:
            return None

    def person_birthday(self, person_id):
        """تاریخ تولد شخص (ISO) برای زاویه‌ی سالروز تولد؛ در صورت خطا None."""
        try:
            return self._get(f"person/{person_id}").get("birthday")
        except TMDbError:
            return None


def get_director(details):
    """اولین کارگردان از credits را برمی‌گرداند."""
    for member in details.get("credits", {}).get("crew", []):
        if member.get("job") == "Director":
            return member
    return None


def genre_names_fa(genres):
    return [GENRE_FA.get(g.get("id"), g.get("name")) for g in (genres or [])]
