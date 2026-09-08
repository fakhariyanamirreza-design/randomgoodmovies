"""موتور تصمیم سردبیری (Editorial Decision Engine).

Candidate Pool → Score → Top N → Diversity Constraints → Final Selection.

قوانین تنوع از config خوانده می‌شوند و انتخاب نهایی deterministic+توضیح‌پذیر است:
اگر در پنجره‌ی اخیر ژانر/پروفایل/کارگردان/دهه‌ای پرتکرار باشد، آن گزینه‌ها حذف/جریمه می‌شوند.
"""

import random

from .history import counts_in_window


# نام فیلد واقعی هر بعد در تاریخچه (category در history با کلید profile ذخیره می‌شود،
# genre با کلید genres که لیستی است)
CONSEC_FIELD = {
    "category": "profile",
    "genre": "genres",
    "director": "director",
    "era": "era",
}


class DiversityResult:
    def __init__(self, candidate, reasons):
        self.candidate = candidate
        self.reasons = reasons  # list[str] توضیح چرا رد/انتخاب شد


class EditorialEngine:
    def __init__(self, config, history_mem):
        self.cfg = config
        self.diversity_cfg = config.get("diversity", {})
        self.weighted_cfg = config.get("weighted_selection", {})
        self.history_mem = history_mem

    def _check_consecutive(self, cand, dimension, value):
        if not value:
            return True, None
        limit = self.diversity_cfg.get(dimension, {}).get("max_consecutive", 99)
        field = CONSEC_FIELD.get(dimension, dimension)
        count = self.history_mem.consecutive_count(field, value)
        if count >= limit:
            return False, (f"{value} بیش از {limit} بار پشت‌سرهم استفاده شده است")
        return True, None

    def _within_group_limits(self, cand, dimension, value, recent_counts, limit_key):
        if not value:
            return True, None
        limit = self.diversity_cfg.get(dimension, {}).get(limit_key, 99)
        count = recent_counts.get(value, 0)
        if count >= limit:
            return False, (f"{value} در {self.diversity_cfg.get('recent_window', 5)} پست اخیر به حد {limit} رسیده است")
        return True, None

    def enforce(self, ranked, top_n=None):
        """با خروجی scoring (مرتب شده) کار می‌کند؛ Top-N را با قوانین تنوع فیلتر می‌کند.

        برمی‌گرداند (selected, ordered_survivors):
          - selected: کاندیدای منتخب (با وزن‌دار بر اساس امتیاز) یا None
          - ordered_survivors: لیست کاندیداهای باقی‌مانده برای fallback،
            اولویت اول منتخب است و بقیه بر اساس امتیاز.
        هر المان: (total, breakdown, cand, reasons)
        """
        recent_window = self.diversity_cfg.get("recent_window", 5)
        genre_counts = counts_in_window(self.history_mem.history, recent_window, "genres")
        profile_counts = counts_in_window(self.history_mem.history, recent_window, "profile")
        director_counts = counts_in_window(self.history_mem.history, recent_window, "director")
        era_counts = counts_in_window(self.history_mem.history, recent_window, "era")

        top = ranked[:max(top_n or 1, 1)]

        # اول hard limits
        hard_survivors = []
        for total, breakdown, cand in top:
            reasons = []
            ok = True

            if not self.history_mem.is_published(cand.get("tmdb_id")):
                reasons.append("قبلاً منتشر نشده")
            rating = cand.get("rating") or 0
            if rating >= 8.3:
                reasons.append(f"کیفیت بالا (rating {rating:.1f})")

            # category
            key = (cand.get("profile_key") or cand.get("profile"))
            ok_c, r = self._within_group_limits(cand, "category", key, profile_counts, "hard_limit")
            ok &= ok_c
            if not ok_c:
                reasons.append(r)
            ok_c, r = self._check_consecutive(cand, "category", key)
            ok &= ok_c
            if not ok_c:
                reasons.append(r)

            # genre
            genres = cand.get("genres") or []
            for g in genres:
                ok_g, r = self._within_group_limits(cand, "genre", g, genre_counts, "hard_limit")
                ok &= ok_g
                if not ok_g:
                    reasons.append(r)
            for g in genres:
                ok_g, r = self._check_consecutive(cand, "genre", g)
                ok &= ok_g
                if not ok_g:
                    reasons.append(r)

            # director
            ok_d, r = self._within_group_limits(cand, "director", cand.get("director"), director_counts, "hard_limit")
            ok &= ok_d
            if not ok_d:
                reasons.append(r)
            ok_d, r = self._check_consecutive(cand, "director", cand.get("director"))
            ok &= ok_d
            if not ok_d:
                reasons.append(r)

            # era
            ok_e, r = self._within_group_limits(cand, "era", cand.get("era"), era_counts, "hard_limit")
            ok &= ok_e
            if not ok_e:
                reasons.append(r)
            ok_e, r = self._check_consecutive(cand, "era", cand.get("era"))
            ok &= ok_e
            if not ok_e:
                reasons.append(r)

            if ok:
                hard_survivors.append((total, breakdown, cand, reasons))

        # اگر hard هیچی باقی نگذاشت، soft limits
        if not hard_survivors:
            soft_survivors = []
            for total, breakdown, cand in top:
                reasons = []
                n_penalties = 0

                if not self.history_mem.is_published(cand.get("tmdb_id")):
                    reasons.append("قبلاً منتشر نشده")
                rating = cand.get("rating") or 0
                if rating >= 8.3:
                    reasons.append(f"کیفیت بالا (rating {rating:.1f})")
                for dimension, key in [
                    ("category", cand.get("profile_key") or cand.get("profile")),
                    ("director", cand.get("director")),
                    ("era", cand.get("era")),
                ]:
                    if not key:
                        continue
                    counts = {"category": profile_counts, "director": director_counts, "era": era_counts}[dimension]
                    ok, r = self._within_group_limits(cand, dimension, key, counts, "soft_limit")
                    if not ok:
                        n_penalties += 1
                        reasons.append(r)
                    ok, r = self._check_consecutive(cand, dimension, key)
                    if not ok:
                        n_penalties += 1
                        reasons.append(r)
                for g in (cand.get("genres") or []):
                    ok, r = self._within_group_limits(cand, "genre", g, genre_counts, "soft_limit")
                    if not ok:
                        n_penalties += 1
                        reasons.append(r)
                    ok, r = self._check_consecutive(cand, "genre", g)
                    if not ok:
                        n_penalties += 1
                        reasons.append(r)
                soft_survivors.append((n_penalties, total, breakdown, cand, reasons))
            soft_survivors.sort(key=lambda x: (x[0], -x[1]))
            if not soft_survivors:
                return None, []
            n_penalties, total, breakdown, cand, reasons = soft_survivors[0]
            ordered = [(total, breakdown, cand, reasons or ["soft limit: کمترین تخلف تنوع در گروه باقی‌مانده"])]
            return ordered[0], ordered

        # انتخاب نهایی از hard_survivors: وزن‌دار بر اساس امتیاز (temperature) برای تنوع
        primary = self._weighted_pick(hard_survivors)
        ordered = [primary] + [s for s in hard_survivors if s is not primary]
        return primary, ordered

    def _weighted_pick(self, survivors):
        if not self.weighted_cfg.get("enabled", True):
            return survivors[0]
        temperature = self.weighted_cfg.get("temperature", 1.2)
        pool = survivors
        # صرفاً محاسبه وزن؛ random.sample با weights
        weights = []
        for total, _b, _c, _r in pool:
            weights.append(max(total, 0.0) ** temperature)
        total_w = sum(weights)
        r = random.random() * total_w
        acc = 0.0
        for item, w in zip(pool, weights):
            acc += w
            if r <= acc:
                return item
        return pool[-1]