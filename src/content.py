"""سازنده‌ی محتوا (Content Builder) — موتور قالب کپشن بر اساس زاویه‌ی سردبیری.

همه‌ی الگوها و بلاک‌ها از config خوانده می‌شوند؛ این ماژول فقط اجرا می‌کند.
"""

import re
import textwrap

from .common import GENRE_FA

FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def fa_digits(text):
    """تبدیل ارقام انگلیسی به فارسی در یک رشته."""
    return "".join(FA_DIGITS[int(c)] if c.isdigit() else c for c in str(text))


def _shorten(text, limit):
    """کوتاه‌کردن یک متن بدون از بین‌بردن سطرها/ساختار؛ انتهایش «…» اضافه می‌شود."""
    if limit <= 1:
        return text[:limit]
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _flag_emoji(iso):
    """پرچم کشور از کد دوحرفی ISO (مثلاً US → 🇺🇸)؛ بدون کد معتبر خالی."""
    if not iso or len(iso) != 2:
        return ""
    a, b = ord(iso[0].upper()), ord(iso[1].upper())
    if not (ord("A") <= a <= ord("Z") and ord("A") <= b <= ord("Z")):
        return ""
    return chr(0x1F1E6 + a - ord("A")) + chr(0x1F1E6 + b - ord("A"))


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
        self.default_template = content.get("default_template", "genre_recommendation")
        self.blocks = content.get("block_template", {})
        self.overview_max_chars = config.get("posting", {}).get("overview_max_chars", 320)
        self.include_keywords = content.get("include_keywords", True)

    def _structured_hashtags(self, cand):
        """هشتگ‌های پایدار و قابل‌جست‌وجو: ژانر اصلی + سال + دهه."""
        tags = []
        genres = cand.get("genres") or []
        genre_names_fa = cand.get("genre_names_fa") or []
        if genres:
            gname = GENRE_FA.get(genres[0], genre_names_fa[0] if genre_names_fa else "")
            if gname:
                tags.append("#" + re.sub(r"\s+", "_", gname))
        year = cand.get("year")
        if year:
            tags.append("#" + str(year))
        era = cand.get("era") or ""
        if era.endswith("s") and era[:-1].isdigit():
            tags.append("#دهه_" + fa_digits(era[:-1]))
        return " ".join(tags)

    def _prepare_values(self, cand, keywords, director_en, director_imdb_id, similar=None,
                        angle_decision=None, reasons=None):
        rating = float(cand.get("rating", 0) or 0)
        genres = "، ".join(GENRE_FA.get(gid, gname) for gid, gname in
                           zip(cand.get("genres") or [], cand.get("genre_names_fa") or []))
        if not genres:
            genres = "، ".join(cand.get("genre_names_fa") or [])

        runtime_text = format_runtime_fa(cand.get("runtime"))
        director_fa = cand.get("director")

        content_cfg = self.cfg.get("content", {})
        if content_cfg.get("hashtag_mode", "structured") == "keywords":
            hashtags = keywords_to_hashtags(keywords) if self.include_keywords else ""
        else:
            hashtags = self._structured_hashtags(cand)

        overview = cand.get("overview_fa") or cand.get("overview_en") or ""
        overview = _shorten(overview, self.overview_max_chars)

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

        # ایموجی ژانر (ایده ۱): اولین/اصلی‌ترین ژانر → ایموجی، وگرنه پیش‌فرض
        first_genre = (cand.get("genres") or [None])[0]
        genre_emoji = content_cfg.get("genre_emoji", {}).get(str(first_genre)) \
            if first_genre is not None else None
        genre_emoji = genre_emoji or content_cfg.get("genre_emoji_default", "🎬")

        # پرچم کشور اصلی (ایده ۵)
        isos = cand.get("countries_iso") or []
        flag = ""
        if isos:
            fl = _flag_emoji(str(isos[0]).upper())
            if fl:
                flag = f" {fl}"

        # تیزر/قلاب جذابیت دورانی (ایده ۲) — با چرخش تعیین‌شده‌ی بین پست‌ها
        teaser_variants = content_cfg.get("teaser_variants", [])
        teaser_line = ""
        if teaser_variants:
            mid = cand.get("tmdb_id") or 0
            teaser_line = teaser_variants[mid % len(teaser_variants)]

        # رویدادهای تاریخ‌محور (ایده ۸) — توسط main روی cand محاسبه شد
        occasion_line = cand.get("_occasion") or ""

        # مخاطب‌شناس (ایده ۷): بر اساس اولین فیلم مشابه
        audience_line = ""
        if similar:
            first_title = similar[0].get("title") or ""
            if first_title:
                audience_line = f"🎯 اگر «{first_title}» را دوست داشتی، این فیلم همان حال و هواست."

        # «چرا این؟» (ایده ۱۰): از نگاشت angle یا اولین دلیل editorial
        angle = angle_decision.angle if angle_decision else ""
        why_line = content_cfg.get("why_lines", {}).get(angle) or ""
        if not why_line and reasons:
            why_line = next((r for r in reasons if r and r != "قبلاً منتشر نشده"), "")

        return {
            "title_fa": cand.get("title_fa"),
            "title_en": cand.get("title_en"),
            "year": str(cand.get("year")) if cand.get("year") else "----",
            "tagline": cand.get("tagline") or "",
            "genre_emoji": genre_emoji,
            "flag": flag,
            "teaser_line": teaser_line,
            "occasion_line": occasion_line,
            "audience_line": audience_line,
            "why_line": why_line,
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
        "teaser_line": "teaser_line",
        "occasion_line": "occasion_line",
        "audience_line": "audience_line",
        "why_line": "why_line",
        "imdb_link": "imdb_link",
        "hashtags": "hashtags",
        "footer": "footer",
    }

    def _compose(self, template, values):
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
        return caption, lines

    def build(self, cand, angle_decision, keywords, director_en=None, director_imdb_id=None,
              similar=None, reasons=None):
        angle = angle_decision.angle
        template = (self.templates.get(angle)
                    or self.templates.get(self.default_template)
                    or self.templates.get("genre_recommendation")
                    or [])
        values = self._prepare_values(cand, keywords, director_en, director_imdb_id,
                                      similar, angle_decision, reasons)
        max_chars = self.cfg.get("content", {}).get("max_caption_chars", 1024)

        caption, lines = self._compose(template, values)

        if len(caption) > max_chars:
            # اول overview (بلندترین بخش) را با بودجه‌ی باقی‌مانده جور کن تا نظم و لیست بلاک‌ها
            # به هم نریزد؛ اگر باز هم جا نشد، بلاک‌های انتهایی را کامل حذف کن (هرگز flatten نشود).
            overview = values.get("overview") or ""
            overhead = len(caption) - len(overview)
            budget = max_chars - overhead - 12
            if budget >= 120 and len(overview) > budget:
                values["overview"] = _shorten(overview, budget)
                caption, lines = self._compose(template, values)
            while len(caption) > max_chars and lines:
                lines.pop()
                caption = "\n".join(lines).strip()
                caption = re.sub(r"\n{3,}", "\n\n", caption)
        return caption