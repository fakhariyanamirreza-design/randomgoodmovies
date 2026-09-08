"""کشف کاندیداها (Candidate Discovery): ساخت pool از روی پروفایل‌های config به‌همراه metadata کامل."""

import random

from .common import country_names_fa


def _best_poster_from_images(data):
    """بهترین/اصلی‌ترین پوستر انگلیسی از پاسخ movie/images.

    اولویت با پوستری است که بیشترین رأی کاربران TMDb را دارد (vote_count) چون همان
    «پوستر اصلی» است؛ در صورت تساوی رتبه‌ی vote_average و سپس ترتیب خود API در نظر
    گرفته می‌شود. `include_image_language=null,en` پوسترهای محلی‌سازی‌شده را بیرون می‌اندازد.
    """
    posters = data.get("posters") or []
    if not posters:
        return None
    best = max(
        posters,
        key=lambda p: (p.get("vote_count", 0), p.get("vote_average", 0)),
    )
    return best.get("file_path")


def pick_poster(details_fa, details_en, images_data=None):
    """انتخاب پوستر اصلی فیلم، دقیقاً همان که در TMDb/IMDb دیده می‌شود.

    ترتیب اولویت:
      1. پوستر en-US فراهم‌شده در movie/details (پوستر اصلی TMDb)
      2. بهترین پوستر انگلیسی از images endpoint (fallback با کیفیت بالا)
      3. پوستر فارسی/محلی‌سازی‌شده (فقط آخرین راه، چون ممکن است نسخه‌ی منطقه‌ای باشد)
    """
    en = details_en.get("poster_path")
    if en:
        return en
    if images_data is not None:
        cleaned = _best_poster_from_images(images_data)
        if cleaned:
            return cleaned
    return details_fa.get("poster_path")


def _extract_era(year, decade_brackets):
    if not year:
        return None
    if decade_brackets:
        for name, start, end in decade_brackets:
            if start <= year <= end:
                return name
        return "other"
    decade = (year // 10) * 10
    return f"{decade}s"


def build_candidate(profile_name, profile, list_movie, details_fa, details_en,
                    yaer_fallback, director=None, imdb_id=None, poster_path=None):
    year_text = (details_fa.get("release_date") or details_en.get("release_date") or "")[:4]
    try:
        year = int(year_text) if year_text else None
    except ValueError:
        year = None
    if year is None:
        year = yaer_fallback

    return {
        "tmdb_id": list_movie.get("id") or details_fa.get("id"),
        "title_fa": details_fa.get("title") or details_fa.get("original_title"),
        "title_en": details_en.get("title") or details_en.get("original_title"),
        "year": year,
        "rating": details_fa.get("vote_average", 0) or 0,
        "vote_count": details_fa.get("vote_count", 0) or 0,
        "popularity": details_fa.get("popularity", 0) or 0,
        "genres": [g.get("id") for g in (details_fa.get("genres") or [])],
        "genre_names_fa": [g.get("name") for g in (details_fa.get("genres") or [])],
        "director": director.get("name") if director else None,
        "director_id": director.get("id") if director else None,
        "overview_fa": details_fa.get("overview") or "",
        "overview_en": details_en.get("overview") or "",
        "release_date": details_fa.get("release_date") or details_en.get("release_date"),
        "runtime": details_fa.get("runtime") or details_en.get("runtime"),
        "tagline": details_fa.get("tagline") or details_en.get("tagline") or "",
        "profile": profile_name,
        "profile_key": profile_name,
        "imdb_id": imdb_id,
        "poster_path": poster_path,
        "era": None,  # بعداً با decade_brackets پر می‌شود
        "countries_fa": country_names_fa(details_fa),
        "countries_iso": [c.get("iso_3166_1") for c in (details_fa.get("production_countries") or [])],
    }


class CandidateDiscovery:
    def __init__(self, client, config, history):
        self.client = client
        self.cfg = config
        self.pool_cfg = config.get("candidate_pool", {})
        self.sc_cfg = config.get("scoring", {})
        self.posting = config.get("posting", {})
        self.history = history
        self.language = self.posting.get("language", "fa-IR")
        self.fallback_language = self.posting.get("fallback_language", "en-US")
        self.decade_brackets = config.get("eras", [])
        self.published_ids = {item.get("id") for item in history.get("posted", []) if item.get("id") is not None}

    def _resolve_poster(self, movie_id, details_fa, details_en):
        """پوستر اصلی؛ اولویت en canonical، سپس best english از images، و فقط در آخر fa محلی.

        وقتی پوستر en وجود دارد درخواست اضافه به images نمی‌شود؛ ولی اگر فقط fa (محلی/
        منطقه‌ای) داریم، حتماً images را امتحان می‌کنیم تا پوستر اصلیِ بین‌المللی برنده شود.
        """
        en = details_en.get("poster_path")
        if en:
            return en
        try:
            images_data = self.client.movie_images(movie_id)
        except Exception:
            images_data = None
        return pick_poster(details_fa, details_en, images_data)

    def _finalize(self, list_movie, profile_name, profile, stats, candidates,
                  excluded_no_fa, seen_ids, floors=None):
        """Build نهایی یک کاندیدا از روی اطلاعات کامل؛ با فیلتر quality برای منبع ترند.

        floors: (min_rating, min_vote_count) اختیاری — فقط برای فیلم‌های ترند.
        """
        mid = list_movie.get("id")
        if mid in seen_ids:
            return
        seen_ids.add(mid)
        try:
            details_fa = self.client.movie_details(mid, self.language)
            details_en = self.client.movie_details(mid, self.fallback_language)
        except Exception:
            return
        if floors:
            if float(details_fa.get("vote_average") or 0) < floors[0]:
                stats["trending_skipped"] += 1
                return
            if int(details_fa.get("vote_count") or 0) < floors[1]:
                stats["trending_skipped"] += 1
                return

        overview_fa = details_fa.get("overview") or ""
        if not overview_fa:
            stats["no_fa_overview"] += 1
            excluded_no_fa.append(mid)
            return
        if mid in self.published_ids:
            stats["already_published"] += 1
            return

        director = None
        for member in details_fa.get("credits", {}).get("crew", []):
            if member.get("job") == "Director":
                director = member
                break
        imdb_id = details_fa.get("external_ids", {}).get("imdb_id") or details_en.get("external_ids", {}).get("imdb_id")

        cand = build_candidate(
            profile_name, profile, list_movie, details_fa, details_en,
            yaer_fallback=list_movie.get("release_date", ""),
            director=director, imdb_id=imdb_id,
            poster_path=self._resolve_poster(mid, details_fa, details_en),
        )
        cand["era"] = _extract_era(cand["year"], self.decade_brackets)
        cand["trending"] = mid in self.trending_ids
        candidates.append(cand)

    def discover(self):
        """برمی‌گرداند: (candidates, excluded_no_fa, stats).

        کاندیداها از (۱) پروفایل‌های config و (۲) فهرست ترندِ روز TMDb ساخته می‌شوند؛
        هر کاندیدا برچسب `trending` می‌گیرد تا موتور امتیازدهی بتواند به ترندها وزن بدهد.
        """
        profiles = self.cfg.get("profiles", [])
        target_per_profile = self.pool_cfg.get("target_per_profile", 8)
        max_pages_per_profile = self.pool_cfg.get("max_pages_per_profile", 3)
        max_pages_total = self.pool_cfg.get("max_pages_total", 12)
        sort_by = self.pool_cfg.get("sort_by", "popularity.desc")
        exclude_adult = self.pool_cfg.get("exclude_adult", "false")

        candidates = []
        excluded_no_fa = []  # candidates که overview فارسی ندارند
        seen_ids = set()
        total_pages_used = 0
        stats = {"discovered": 0, "already_published": 0, "no_fa_overview": 0,
                 "trending_found": 0, "trending_skipped": 0}

        trending_cfg = self.cfg.get("trending", {}) or {}
        self.trending_ids = set()
        if trending_cfg.get("enabled", True):
            try:
                self.trending_ids = set(self.client.trending(
                    window=trending_cfg.get("window", "week"),
                    limit=int(trending_cfg.get("limit", 12)),
                ))
            except Exception:
                self.trending_ids = set()
        stats["trending_found"] = len(self.trending_ids)

        for profile in profiles:
            profile_name = profile.get("name") or "نامشخص"
            if total_pages_used >= max_pages_total:
                break
            try:
                first = self.client.discover(profile, self.language, 1, sort_by, exclude_adult)
            except Exception:
                continue
            total_pages = min(first.get("total_pages", 1), 500) or 1
            pages_to_try = [1] + list(range(2, total_pages + 1))
            pages_to_try = pages_to_try[:max_pages_per_profile]
            random.shuffle(pages_to_try[1:])

            gathered = []
            pages_used = 0
            for page in pages_to_try[:max_pages_per_profile]:
                if total_pages_used >= max_pages_total or len(gathered) >= target_per_profile:
                    break
                try:
                    data = first if page == 1 else self.client.discover(profile, self.language, page, sort_by, exclude_adult)
                except Exception:
                    continue
                pages_used += 1
                total_pages_used += 1
                for m in data.get("results", []):
                    if len(gathered) >= target_per_profile:
                        break
                    gathered.append(m)
                    stats["discovered"] += 1

            # برای هر فیلم متادیتای کامل فارسی/انگلیسی بگیر
            for list_movie in gathered:
                self._finalize(list_movie, profile_name, profile, stats, candidates,
                               excluded_no_fa, seen_ids)

        # فیلم‌های ترند روز: منبع اضافی برای هم‌پوشانی با حال‌وهوای روز
        if trending_cfg.get("enabled", True):
            floors = (float(trending_cfg.get("min_rating", 6.5)),
                      int(trending_cfg.get("min_vote_count", 500)))
            trend_profile = {"name": "ترند روز"}
            for mid in sorted(self.trending_ids):
                stats["discovered"] += 1
                self._finalize(
                    {"id": mid, "release_date": ""},
                    "ترند روز", trend_profile, stats, candidates,
                    excluded_no_fa, seen_ids, floors=floors,
                )

        return candidates, excluded_no_fa, stats
