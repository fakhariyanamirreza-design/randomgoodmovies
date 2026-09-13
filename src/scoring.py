"""موتور امتیازدهی (Editorial Scoring Engine).

امتیاز نهایی = sum(وزن * share(max)) به‌طوری که هر معیار بین 0 و max خودش scale می‌شود.
خروجی تا «سهم هر معیار» قابل توضیح (explainable) است.
"""

from datetime import date


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def normalize_weights(weights):
    total = sum(weights.values()) or 1.0
    return {k: v / total for k, v in weights.items()}


def quality_component(cand, cfg):
    """کیفیت = ترکیب rating و vote_count (هرکدام سهم مساوی)."""
    sc = cfg
    rating = float(cand.get("rating", 0) or 0)
    vote_count = float(cand.get("vote_count", 0) or 0)
    rating_max = sc.get("rating_reference_max", 10)
    ref = sc.get("quality_vote_count_reference", 5000)
    rating_share = _clamp(rating / rating_max)
    votes_share = _clamp(vote_count / ref)
    return (rating_share + votes_share) / 2


def novelty_component(cand, history_mem):
    """فیلم‌های منتشرنشده + فیلم‌های با سابقه‌ی کمتر امتیاز کامل، بقیه 0."""
    if history_mem.is_published(cand.get("tmdb_id")):
        return 0.0
    return 1.0


def category_diversity_component(cand, history_mem):
    counts = history_mem.profile_counts()
    total = sum(counts.values()) or 1
    profile = cand.get("profile_key") or cand.get("profile")
    used = counts.get(profile, 0)
    return 1.0 - (used / total)


def genre_diversity_component(cand, history_mem):
    counts = history_mem.genre_counts()
    total = sum(counts.values()) or 1
    genres = cand.get("genres") or []
    if not genres:
        return 0.5
    used_avg = sum(counts.get(g, 0) for g in genres) / len(genres)
    return 1.0 - (used_avg / total)


def director_diversity_component(cand, history_mem):
    counts = history_mem.director_counts()
    total = sum(counts.values()) or 1
    director = cand.get("director")
    if not director:
        return 0.5
    used = counts.get(director, 0)
    return 1.0 - (used / total)


def era_diversity_component(cand, history_mem):
    counts = history_mem.era_counts()
    total = sum(counts.values()) or 1
    era = cand.get("era")
    if not era:
        return 0.5
    used = counts.get(era, 0)
    return 1.0 - (used / total)


def popularity_component(cand, cfg):
    """محبوبیت با سقف: رابطه‌ی سیری‌پذیر تا popular_reference."""
    sc = cfg
    pop = float(cand.get("popularity", 0) or 0)
    ref = sc.get("popularity_reference", 100)
    return _clamp(pop / ref)


def surprise_component(cand, cfg):
    """غافلگیری: کیفیت بالا اما کمتر آشکار (vote_count پایین‌تر از آستانه)."""
    sc = cfg
    threshold = sc.get("surprise_vote_count_threshold", 3000)
    rating = float(cand.get("rating", 0) or 0)
    vote_count = float(cand.get("vote_count", 0) or 0)
    if rating >= 8.0 and vote_count < threshold:
        gap = 1.0 - (vote_count / threshold)
        return 0.5 + 0.5 * _clamp(gap)
    return 0.0


def trending_component(cand, _cfg):
    """ترند بودن: اگر فیلم الان در فهرست ترند TMDb باشد سهم کامل، وگرنه 0 (بدون تاریخچه)."""
    return 1.0 if cand.get("trending") else 0.0


def classic_component(cand, cfg):
    """کلاسیک بودن: هرچه فیلم قدیمی‌تر، سهم بیشتر (تا سقف classic_max_age).

    با آن‌که era_diversity «تکرار یک دهه» را جریمه می‌کند، فیلم‌های به‌روز به خاطر
    popularity/trending/quality بالا برنده می‌شدند؛ این معیار به فیلم‌های قدیمی بونس
    صریح می‌دهد تا تعادل برقرار شود. بدون year سهم 0 است.
    """
    year = cand.get("year")
    if not year:
        return 0.0
    try:
        age = date.today().year - int(year)
    except (TypeError, ValueError):
        return 0.0
    min_age = cfg.get("classic_min_age", 10)
    max_age = cfg.get("classic_max_age", 20)
    if max_age <= min_age:
        return 1.0 if age >= min_age else 0.0
    if age <= min_age:
        return 0.0
    if age >= max_age:
        return 1.0
    return (age - min_age) / (max_age - min_age)


COMPONENTS = {
    "quality": quality_component,
    "novelty": novelty_component,
    "category_diversity": category_diversity_component,
    "genre_diversity": genre_diversity_component,
    "director_diversity": director_diversity_component,
    "era_diversity": era_diversity_component,
    "popularity": popularity_component,
    "surprise": surprise_component,
    "trending": trending_component,
    "classic": classic_component,
}

DEFAULTS = {
    "quality_max": 100,
    "quality_vote_count_reference": 5000,
    "rating_reference_max": 10,
    "popularity_max": 100,
    "popularity_reference": 100,
    "surprise_vote_count_threshold": 3000,
    "trending_max": 100,
    "classic_max": 100,
}


class ScoringEngine:
    def __init__(self, config, history_mem):
        sc = config.get("scoring", {})
        self.cfg = sc
        self.weights = normalize_weights(sc.get("weights", {}))
        self.history_mem = history_mem

    def score_one(self, cand):
        """امتیاز یک کاندیدا + تفکیک هر معیار (برای explainability)."""
        breakdown = {}
        total = 0.0
        cfg_needing = {"quality", "popularity", "surprise", "trending", "classic"}
        for name, weight in self.weights.items():
            max_val = DEFAULTS.get(name + "_max", 100.0)
            func = COMPONENTS.get(name)
            if func is None:
                share = 0.0
            elif name in cfg_needing:
                share = func(cand, self.cfg)
            else:
                share = func(cand, self.history_mem)
            weighted = share * max_val * weight
            breakdown[name] = weighted
            total += weighted
        return total, breakdown

    def score_many(self, candidates):
        ranked = []
        for cand in candidates:
            total, breakdown = self.score_one(cand)
            ranked.append((total, breakdown, cand))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked