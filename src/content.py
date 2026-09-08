"""سازنده‌ی محتوا (Content Builder) — موتور قالب کپشن بر اساس زاویه‌ی سردبیری.

همه‌ی الگوها و بلاک‌ها از config خوانده می‌شوند؛ این ماژول فقط اجرا می‌کند.
"""

import re
import textwrap

from .common import GENRE_FA


def format_runtime_fa(minutes):
    if not minutes:
        return None
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"{hours} ساعت و {mins} دقیقه"
    if hours:
        return f"{hours} ساعت"
    return f"{mins} دقیقه"


def keywords_to_hashtags(keywords, limit=5):
    hashtags = []
    for name in keywords[:limit]:
        cleaned = re.sub(r"[^\w\s]", "", name, flags=re.UNICODE).strip()
        cleaned = re.sub(r"\s+", "_", cleaned)
        if cleaned:
            hashtags.append(f"#{cleaned}")
    return " ".join(hashtags)


class ContentBuilder:
    def __init__(self, config):
        self.cfg = config
        content = config.get("content", {})
        self.templates = content.get("templates", {})
        self.blocks = content.get("block_template", {})
        self.overview_max_chars = config.get("posting", {}).get("overview_max_chars", 320)
        self.include_keywords = content.get("include_keywords", True)

    def _prepare_values(self, cand, keywords, director_en, director_imdb_id, similar=None):
        rating = float(cand.get("rating", 0) or 0)
        genres = "، ".join(GENRE_FA.get(gid, gname) for gid, gname in
                           zip(cand.get("genres") or [], cand.get("genre_names_fa") or []))
        if not genres:
            genres = "، ".join(cand.get("genre_names_fa") or [])

        runtime_text = format_runtime_fa(cand.get("runtime"))
        director_fa = cand.get("director")
        hashtags = keywords_to_hashtags(keywords) if self.include_keywords else ""

        overview = cand.get("overview_fa") or cand.get("overview_en") or ""
        if len(overview) > self.overview_max_chars:
            overview = textwrap.shorten(overview, width=self.overview_max_chars, placeholder="…")

        imdb_link = None
        if cand.get("imdb_id"):
            imdb_link = f"https://www.imdb.com/title/{cand['imdb_id']}/"

        director_line_en = None
        if director_en and director_en != director_fa:
            if director_imdb_id:
                director_line_en = f'<a href="https://www.imdb.com/name/{director_imdb_id}/">{director_en}</a>'
            else:
                director_line_en = director_en

        similar_lines = []
        for item in (similar or []):
            title = item.get("title") or ""
            year = item.get("year")
            line = f"• {title}" + (f" ({year})" if year else "")
            if line.strip() != "•":
                similar_lines.append(line)

        return {
            "title_fa": cand.get("title_fa"),
            "title_en": cand.get("title_en"),
            "year": str(cand.get("year")) if cand.get("year") else "----",
            "tagline": cand.get("tagline") or "",
            "category": cand.get("profile") or cand.get("profile_key") or "",
            "rating": f"{rating:.1f}",
            "genres": genres,
            "runtime": runtime_text or "",
            "country": "، ".join(cand.get("countries_fa") or []),
            "director_fa": director_fa or "",
            "director_en": director_line_en or "",
            "overview": overview,
            "imdb_link": imdb_link or "",
            "similar_movies": "\n".join(similar_lines),
            "trending_line": "🔥 همین حالا در فهرست فیلم‌های ترند روز TMDb است" if cand.get("trending") else "",
            "hashtags": hashtags,
            "footer": self.cfg.get("posting", {}).get("channel_footer") or "",
        }

    @staticmethod
    def _block_is_empty(block_text):
        """یک بلاک خالی اگر اصلاً متن نداشته باشد یا فقط قالب/ایموجیِ ثابت باشد، حذف می‌شود."""
        stripped = re.sub(r"[:/.\-—|،,«»…()]", "", block_text, flags=re.UNICODE).strip()
        # هر چیزی که کاراکتر الفبایی/هشتگ/ایموجی محتوا ندارد خالی است
        if re.search(r"[\w]", stripped, flags=re.UNICODE):
            return False
        return True

    # هر بلاک وابسته به کدام مقدار است؛ اگر آن مقدار خالی باشد بلاک حذف می‌شود.
    BLOCK_VALUE_DEP = {
        "title_fa": "title_fa",
        "title_en": "title_en",
        "tagline": "tagline",
        "rating": "rating",
        "genres": "genres",
        "runtime": "runtime",
        "country": "country",
        "director_fa": "director_fa",
        "director_en": "director_en",
        "overview": "overview",
        "similar_movies": "similar_movies",
        "trending_line": "trending_line",
        "imdb_link": "imdb_link",
        "hashtags": "hashtags",
        "footer": "footer",
    }

    def build(self, cand, angle_decision, keywords, director_en=None, director_imdb_id=None,
              similar=None):
        angle = angle_decision.angle
        template = self.templates.get(angle) or self.templates.get("genre_recommendation") or []
        values = self._prepare_values(cand, keywords, director_en, director_imdb_id, similar)

        lines = []
        for key in template:
            if key == "blank":
                lines.append("")
                continue
            block = self.blocks.get(key)
            if not block:
                continue
            dep = self.BLOCK_VALUE_DEP.get(key)
            if dep is not None and not values.get(dep):
                continue
            try:
                rendered = block.format(**values)
            except (KeyError, IndexError, ValueError):
                continue
            if self._block_is_empty(rendered):
                continue
            lines.append(rendered)

        caption = "\n".join(lines).strip()
        caption = re.sub(r"\n{3,}", "\n\n", caption)
        max_chars = self.cfg.get("content", {}).get("max_caption_chars", 1024)
        if len(caption) > max_chars:
            caption = textwrap.shorten(caption, width=max_chars, placeholder="…", break_long_words=False)
        return caption