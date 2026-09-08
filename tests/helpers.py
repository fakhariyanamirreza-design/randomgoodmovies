"""ابزار کمک برای تست‌ها — ساخت config و کاندیدای نمونه."""


def base_config():
    return {
        "profiles": [
            {"name": "درام‌های جایزه‌گرفته", "with_genres": "18"},
            {"name": "اکشن مدرن پرامتیاز", "with_genres": "28"},
        ],
        "posting": {
            "language": "fa-IR",
            "fallback_language": "en-US",
            "overview_max_chars": 320,
            "channel_footer": "📢 کانال تست @test",
        },
        "candidate_pool": {
            "target_per_profile": 8,
            "max_pages_per_profile": 2,
            "max_pages_total": 4,
        },
        "trending": {
            "enabled": False  # تست‌ها بدون شبکه
        },
        "scoring": {
            "weights": {
                "quality": 0.27,
                "novelty": 0.15,
                "category_diversity": 0.10,
                "genre_diversity": 0.10,
                "director_diversity": 0.10,
                "era_diversity": 0.08,
                "popularity": 0.09,
                "surprise": 0.04,
                "trending": 0.07,
            },
            "quality_max": 100,
            "quality_vote_count_reference": 5000,
            "rating_reference_max": 10,
            "popularity_max": 100,
            "popularity_reference": 100,
            "surprise_vote_count_threshold": 3000,
        },
        "weighted_selection": {
            "enabled": False,  # تست‌ها deterministic
            "top_n": 3,
            "temperature": 1.2,
        },
        "diversity": {
            "history_window": 10,
            "recent_window": 5,
            "category": {"hard_limit": 1, "soft_limit": 1, "max_consecutive": 1},
            "genre": {"hard_limit": 2, "soft_limit": 1, "max_consecutive": 1},
            "director": {"hard_limit": 2, "soft_limit": 1, "max_consecutive": 2},
            "era": {"hard_limit": 3, "soft_limit": 2, "max_consecutive": 2},
        },
        "angles": {
            "priority": [
                "trending_now", "highly_rated", "hidden_gem", "director_spotlight", "award_recognition",
                "modern_classic", "classic_recommendation", "short_runtime",
                "influential_film", "decade_recommendation", "genre_recommendation",
                "weekend_recommendation",
            ],
            "rules": {
                "trending_now": {},
                "highly_rated": {"min_rating": 8.3, "min_vote_count": 3000},
                "hidden_gem": {"min_rating": 8.0, "max_vote_count": 3000},
                "director_spotlight": {"min_rating": 7.8},
                "award_recognition": {"award_keywords": ["oscar", "cannes", "bafta"]},
                "modern_classic": {"min_rating": 8.0, "min_year": 1995},
                "classic_recommendation": {"max_year": 1994},
                "short_runtime": {"max_runtime": 100},
                "influential_film": {"min_vote_count": 2000, "min_popularity": 20},
                "decade_recommendation": {"min_rating": 7.8},
                "genre_recommendation": {"min_rating": 7.8},
                "weekend_recommendation": {"min_rating": 7.5},
            },
            "default_angle": "genre_recommendation",
        },
        "content": {
            "max_caption_chars": 1024,
            "include_keywords": True,
            "templates": {
                "trending_now": [
                    "title_fa", "title_en", "blank", "tagline", "trending_line",
                    "blank", "category", "rating", "genres", "runtime", "country",
                    "blank", "director_fa", "director_en", "blank", "overview",
                    "blank", "similar_movies", "blank", "imdb_link", "blank", "hashtags",
                    "blank", "footer",
                ],
                "genre_recommendation": [
                    "title_fa", "title_en", "blank", "tagline", "trending_line",
                    "blank", "category", "rating", "genres", "runtime", "country",
                    "blank", "director_fa", "director_en", "blank", "overview",
                    "blank", "similar_movies", "blank", "imdb_link", "blank", "hashtags",
                    "blank", "footer",
                ],
                "hidden_gem": [
                    "title_fa", "title_en", "blank", "tagline", "trending_line",
                    "blank", "rating", "genres", "blank", "overview",
                    "blank", "similar_movies", "blank", "footer",
                ],
            },
            "block_template": {
                "title_fa": "🎬 <b>{title_fa}</b> ({year})",
                "title_en": "↳ {title_en} ({year})",
                "tagline": "💬 «{tagline}»",
                "category": "🗂 دسته: {category}",
                "rating": "⭐ امتیاز: {rating}/10",
                "genres": "🎭 ژانر: {genres}",
                "runtime": "⏱ مدت‌زمان: {runtime}",
                "country": "🌍 کشور سازنده: {country}",
                "director_fa": "🎬 کارگردان: {director_fa}",
                "director_en": "↳ {director_en}",
                "overview": "📝 {overview}",
                "imdb_link": "🔗 <a href=\"{imdb_link}\">صفحه فیلم در IMDB</a>",
                "hashtags": "{hashtags}",
                "footer": "{footer}",
                "similar_movies": "🎯 <b>فیلم‌های شبیه به این:</b>\n{similar_movies}",
                "trending_line": "{trending_line}",
            },
        },
        "quality_gate": {
            "require_overview": True,
            "require_poster": True,
            "require_rating": True,
            "min_rating": 6.0,
            "max_caption_chars": 1024,
        },
        "publisher": {
            "photo_size": "w1280",
            "timeout_seconds": 30,
            "max_retries": 0,
        },
        "tmdb": {
            "request_timeout": 20,
            "max_retries": 0,
        },
    }


def make_candidate(**overrides):
    cand = {
        "tmdb_id": 12345,
        "title_fa": "وردپرس",
        "title_en": "Incendies",
        "year": 2010,
        "rating": 8.2,
        "vote_count": 4000,
        "popularity": 30.0,
        "genres": [18],
        "genre_names_fa": ["درام"],
        "director": "دنی ویلنوو",
        "director_id": 1001,
        "overview_fa": "خلاصه‌ی داستان فارسی فیلم.",
        "overview_en": "English overview.",
        "release_date": "2010-09-04",
        "runtime": 130,
        "profile": "درام‌های جایزه‌گرفته",
        "profile_key": "درام‌های جایزه‌گرفته",
        "imdb_id": "tt1255953",
        "poster_path": "/abc.jpg",
        "era": "2010s",
        "tagline": "",
        "trending": False,
        "countries_fa": ["کانادا"],
    }
    cand.update(overrides)
    return cand


def base_history(posts=None):
    return {
        "schema_version": 2,
        "posted": posts or [],
        "meta": {"performance": {"enabled": False}},
    }