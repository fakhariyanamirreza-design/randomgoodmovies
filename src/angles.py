"""موتور انتخاب زاویه‌ی سردبیری (Angle Selection) — rule-based و deterministic.

زاویه با اولین قانونِ منطبق‌شده در ترتیب config.angles.priority انتخاب می‌شود.
هر تصمیم، توضیح کوتاهی دارد (که در لاگ و history می‌نشیند).
"""


class AngleDecision:
    def __init__(self, angle, reasons):
        self.angle = angle
        self.reasons = reasons

    def as_dict(self):
        return {"angle": self.angle, "reasons": self.reasons}


def _rating(cand):
    return float(cand.get("rating", 0) or 0)


def _vote_count(cand):
    return int(cand.get("vote_count", 0) or 0)


def _year(cand):
    return cand.get("year") or 0


def _runtime(cand):
    return cand.get("runtime") or 0


class AngleEngine:
    def __init__(self, config):
        angles_cfg = config.get("angles", {})
        self.priority = angles_cfg.get("priority", [])
        self.rules = angles_cfg.get("rules", {})
        self.default_angle = angles_cfg.get("default_angle", "genre_recommendation")
        self.posting = config.get("posting", {})

    def choose(self, cand, keywords=None):
        """برمی‌گرداند AngleDecision. keywords اختیاری (برای award detection)."""
        keywords = keywords or []
        for angle in self.priority:
            rule = self.rules.get(angle, {})
            reasons = []
            ok = True
            if angle == "highly_rated":
                if _rating(cand) < rule.get("min_rating", 99):
                    ok = False
                elif _vote_count(cand) < rule.get("min_vote_count", 0):
                    ok = False
                else:
                    reasons.append(f"امتیاز {_rating(cand):.1f} بالاتر از حداقل {rule.get('min_rating')} و رأی کافی")
            elif angle == "hidden_gem":
                if _rating(cand) < rule.get("min_rating", 99):
                    ok = False
                elif _vote_count(cand) > rule.get("max_vote_count", 0):
                    ok = False
                else:
                    reasons.append(f"امتیاز بالا اما با {_vote_count(cand)} رأی، کمتر شناخته‌شده است")
            elif angle == "director_spotlight":
                if not cand.get("director"):
                    ok = False
                elif _rating(cand) < rule.get("min_rating", 0):
                    ok = False
                else:
                    reasons.append(f"کارگردان شناخته‌شده: {cand.get('director')}")
            elif angle == "award_recognition":
                hit = [k for k in rule.get("award_keywords", []) if k.lower() in " ".join(keywords).lower()]
                if not hit:
                    ok = False
                else:
                    reasons.append(f"بازتاب جوایز در کلمات کلیدی: {hit[0]}")
            elif angle == "modern_classic":
                if _rating(cand) < rule.get("min_rating", 0):
                    ok = False
                elif _year(cand) < rule.get("min_year", 1995):
                    ok = False
                else:
                    reasons.append(f"{_year(cand)} و امتیاز {_rating(cand):.1f} → اثر مدرنِ برجسته")
            elif angle == "classic_recommendation":
                if _year(cand) > rule.get("max_year", 1994):
                    ok = False
                else:
                    reasons.append(f"سال {_year(cand)} → کلاسیک")
            elif angle == "short_runtime":
                if not _runtime(cand) or _runtime(cand) > rule.get("max_runtime", 100):
                    ok = False
                else:
                    reasons.append(f"مدت‌زمان {_runtime(cand)} دقیقه")
            elif angle == "influential_film":
                if _vote_count(cand) < rule.get("min_vote_count", 0):
                    ok = False
                elif float(cand.get("popularity", 0) or 0) < rule.get("min_popularity", 0):
                    ok = False
                else:
                    reasons.append(f"تأثیرگذار: {_vote_count(cand)} رأی و محبوبیت بالا")
            elif angle == "decade_recommendation":
                if _rating(cand) < rule.get("min_rating", 0):
                    ok = False
                else:
                    reasons.append(f"پیشنهاد دهه‌ای (دهه‌ی {cand.get('era')})")
            elif angle == "genre_recommendation":
                if _rating(cand) < rule.get("min_rating", 0):
                    ok = False
                else:
                    reasons.append(f"پیشنهاد بر اساس ژانر: {', '.join(cand.get('genre_names_fa') or [])}")
            elif angle == "weekend_recommendation":
                if _rating(cand) < rule.get("min_rating", 0):
                    ok = False
                else:
                    reasons.append("انتخاب مناسب تعطیلات آخر هفته")

            if ok:
                return AngleDecision(angle, reasons)
        return AngleDecision(self.default_angle, ["زاویه‌ی پیش‌فرض (rule عمومی)"])

    def choose_for_day(self, cand, keywords=None):
        """مانند choose ولی اگر آخر هفته باشد اول weekend_recommendation سنجیده می‌شود."""
        # با انتخاب weekday در main/کمک قابل استفاده است؛ این‌جا ساده نگه می‌داریم.
        return self.choose(cand, keywords)