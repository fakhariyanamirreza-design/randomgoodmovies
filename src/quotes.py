"""موتور نقل قول‌های سینمایی: بارگذاری، فیلتر محتوا، انتشار روزانه."""

import json
import os
import random
from datetime import datetime, timezone


# لیست کلمات رکیک/فحش فارسی برای فیلتر محتوا
# هر کلمه به صورت substring بررسی می‌شود
PROFANITY_FA = [
    "مادرسگ", "مادر جنده", "خواهر جنده", "برادر جنده",
    "جنده", "کثاف", "کثیف", "حرامی", "حروم زاده", "حرامزاده",
    "کیری", "کوس", "کص", "کسه", "کیرم", "گایید",
    "بی‌ناموس", "بی ناموس", "ناموس",
    "عوضی", "پلشت", "پست",
    "بی‌شرم", "بی شرم", "بی‌عفت", "بی عفت",
    "لعنتی", "ملعون", "لعنت", "نفرین",
    "سکس", "جنسی", "رابطه جنسی",
    "fucking", "bitch", "motherfucker", "damn", "fuck", "shit",
    "ass ", "dick",
]


def contains_profanity(text):
    """بررسی وجود کلمات رکیک در متن فارسی."""
    text_lower = text.lower()
    for word in PROFANITY_FA:
        if word.lower() in text_lower:
            return True
    return False


class QuoteEngine:
    """بارگذاری و مدیریت نقل قول‌های سینمایی."""

    def __init__(self, quotes_path, history):
        self.quotes_path = quotes_path
        self.history = history
        self.quotes = self._load_quotes()

    def _load_quotes(self):
        """بارگذاری نقل قول‌ها از فایل JSON."""
        if not os.path.exists(self.quotes_path):
            return []
        try:
            with open(self.quotes_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def get_published_indices(self):
        """ایندکس نقل قول‌های قبلاً منتشرشده."""
        posted = self.history.get("quotes_posted", [])
        return {item.get("quote_index") for item in posted if "quote_index" in item}

    def next_quote(self):
        """انتخاب نقل قول بعدی (اولین نقل قول منتشرنشده)."""
        published = self.get_published_indices()
        for i, quote in enumerate(self.quotes):
            if i in published:
                continue
            if contains_profanity(quote.get("quote_fa", "")):
                continue
            return i, quote
        return None, None

    def record_published(self, index, message_id=None):
        """ثبت نقل قول منتشرشده در تاریخچه."""
        if "quotes_posted" not in self.history:
            self.history["quotes_posted"] = []
        self.history["quotes_posted"].append({
            "quote_index": index,
            "movie": self.quotes[index].get("movie"),
            "posted_at": datetime.now(timezone.utc).isoformat(),
            "message_id": message_id,
        })

    def build_caption(self, quote, footer, year=None):
        """ساخت کپشن پست نقل قول. اگر year داده شود کنار نام فیلم می‌آید."""
        movie_name = quote.get("movie", "")
        imdb_url = quote.get("imdb_url", "")
        quote_fa = quote.get("quote_fa", "")
        movie_label = f"{movie_name} ({year})" if year else movie_name

        lines = [
            f"«{quote_fa}»",
            "",
            f"<a href=\"{imdb_url}\">{movie_label}</a>",
            "",
            footer,
        ]
        return "\n".join(lines)

    def _find_movie(self, quote, tmdb_client):
        """جستجوی فیلم در TMDb با imdb_id؛ اولین نتیجه برمی‌گردد (یا None)."""
        imdb_id = quote.get("imdb_url", "").split("/title/")[1].rstrip("/")
        if not imdb_id:
            return None
        find_result = tmdb_client._get(f"find/{imdb_id}", {"external_source": "imdb_id"})
        movie_results = (find_result or {}).get("movie_results", [])
        return movie_results[0] if movie_results else None

    def get_movie_year(self, quote, tmdb_client):
        """سال ساخت فیلم از پاسخ TMDb (از روی release_date)؛ None اگر پیدا نشد."""
        try:
            movie = self._find_movie(quote, tmdb_client)
        except Exception:
            return None
        if not movie:
            return None
        release_date = movie.get("release_date") or ""
        prefix = release_date[:4]
        if prefix.isdigit():
            return int(prefix)
        return None

    def get_backdrop_url(self, quote, tmdb_client, photo_size="w1280"):
        """دریافت URL عکس افقی (backdrop) از TMDb."""
        try:
            movie = self._find_movie(quote, tmdb_client)
        except Exception:
            return None
        if not movie:
            return None
        tmdb_id = movie.get("id")
        if not tmdb_id:
            return None

        try:
            images = tmdb_client._get(f"movie/{tmdb_id}/images", {"include_image_language": "null"})
            backdrops = images.get("backdrops", [])
            if not backdrops:
                return None
            best = max(backdrops, key=lambda b: b.get("vote_average", 0))
            path = best.get("file_path")
            if not path:
                return None
            return f"https://image.tmdb.org/t/p/{photo_size}{path}"
        except Exception:
            return None
