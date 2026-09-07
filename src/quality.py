"""گیت کیفیت (Quality Gate) — قبل از انتشار، یکسری بررسی deterministic انجام می‌دهد.

اگر گیت شکست بخورد publish نمی‌شود و سیستم سراغ کاندیدای بعدی می‌رود (در orchestrator).
"""

from .content import keywords_to_hashtags


class QualityError(Exception):
    pass


class QualityResult:
    def __init__(self, passed, errors, caption=None):
        self.passed = passed
        self.errors = errors  # list[str]
        self.caption = caption


class QualityGate:
    def __init__(self, config):
        self.cfg = config.get("quality_gate", {})
        self.content_max = config.get("content", {}).get("max_caption_chars", 1024) or \
            self.cfg.get("max_caption_chars", 1024)

    def validate_metadata(self, cand):
        errors = []

        if not cand.get("title_fa"):
            errors.append("عنوان فارسی وجود ندارد")

        if self.cfg.get("require_overview", True):
            overview = cand.get("overview_fa") or cand.get("overview_en") or ""
            if not overview:
                errors.append("overview فارسی/انگلیسی وجود ندارد")

        poster = cand.get("poster_path")
        if self.cfg.get("require_poster", True) and not poster:
            errors.append("پوستر وجود ندارد")

        rating = float(cand.get("rating", 0) or 0)
        if self.cfg.get("require_rating", True):
            if not rating:
                errors.append("امتیاز معتبر نیست")
            elif rating < self.cfg.get("min_rating", 6.0):
                errors.append(f"امتیاز کمتر از حداقل {self.cfg.get('min_rating')} است")

        if self.cfg.get("require_imdb_when_available", False):
            # اینجا دلیلی برای رد ندارد؛ فقط فیلد را چک می‌کنیم اگر موجود بود
            pass

        if not (cand.get("profile") or cand.get("profile_key")):
            errors.append("دسته (profile) معتبر نیست")

        return errors

    def validate_caption(self, caption):
        errors = []
        if not caption:
            errors.append("کپشن خالی است")
        if len(caption) > self.content_max:
            errors.append(f"کپشن از حد {self.content_max} کاراکتر بیشتر است")
        return errors

    def check(self, cand, caption=None):
        """بررسی کامل: متادیتا + (اختیاری) کپشن. برمی‌گرداند QualityResult."""
        errors = self.validate_metadata(cand)
        if caption is not None:
            errors.extend(self.validate_caption(caption))
        if not errors:
            return QualityResult(True, [], caption=caption)
        return QualityResult(False, errors, caption=caption)