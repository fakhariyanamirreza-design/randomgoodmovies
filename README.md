# سیستم خودمختار تولید محتوای سینمایی (Autonomous Movie Content System)

نسخه‌ی تکامل‌یافته‌ی ربات «انتشار فیلم رندوم» که از یک انتخابگر رندوم ساده به یک
**موتور تصمیم سردبیری** (Editorial Decision Engine) rule-based تبدیل شده است.

- بدون LLM و بدون هیچ API پولی (فقط TMDb + Telegram Bot API رایگان)
- کاملاً خودکار با GitHub Actions؛ بدون سرور و بدون دخالت دستی
- تمام تصمیم‌ها deterministic و قابل توضیح (explainable) هستند
- حافظه روی JSON ساده (`data/posted.json`) نگه داشته می‌شود

---

## گردش کار

```
Discover           → ساخت Candidate Pool از پروفایل‌های config (با metadata کامل)
Filter             → حذف فیلم‌های منتشرشده + فیلم‌های بدون خلاصه‌ی فارسی
Score              → امتیازدهی editorial بر اساس ۸ معیار وزن‌دار
Analyze History    → توزیع ژانر/کارگردان/دهه/دسته از حافظه
Select             → قوانین تنوع (hard/soft limit) + انتخاب وزن‌دار از Top-N
Choose Angle       → انتخاب زاویه‌ی سردبیری (Highly Rated، Hidden Gem و ...)
Generate Content   → موتور قالب کپشن به‌ازای هر angle
Quality Check      → گیت کیفیت (متادیتا + کپشن + کوتاهی)
Publish            → انتشار به تلگرام با retry محدود
Save Memory        → ثبت تاریخچه‌ی کامل پست
```

اگر هیچ کاندیدای مناسبی پیدا نشود یا گیت کیفیت در همه رد شود، **چیزی منتشر نمی‌شود**
و دلیل آن در لاگ نوشته می‌شود.

---

## ساختار پروژه

```
main.py                  # orchestrator: کل گردش کار
config.json              # همه‌ی تنظیمات (وزن‌ها، محدودیت‌ها، angles، قالب‌ها)
requirements.txt         # فقط requests
data/posted.json         # حافظه / تاریخچه (schema v2)

src/
├── __init__.py
├── common.py            # ژانرها/کشورها + ابزار مشترک
├── tmdb_client.py       # TMDb Client (retry، timeout، rate limit)
├── discovery.py         # Candidate Discovery (ساخت pool)
├── history.py           # آنالیز حافظه (شمارش، streak، آخرین استفاده)
├── scoring.py           # Editorial Scoring Engine
├── editorial.py         # Editorial Decision Engine (قوانین تنوع)
├── angles.py            # Angle Selection Engine
├── content.py           # Content Builder (موتور قالب)
├── quality.py           # Quality Gate
├── publisher.py         # Telegram Publisher
├── persistence.py       # بارگذاری/ذخیره‌ی JSON + مهاجرت ورودی‌های قدیمی
└── explain.py           # خروجی توضیح‌پذیر برای لاگ

tests/                   # ۴۳ تست unittest (بدون نیاز به شبکه)
.github/workflows/publish.yml
```

---

## امتیازدهی

امتیاز نهایی = مجموع `سهم(معیار) × max × وزن`.

| معیار | وزن پیش‌فرض | ایده |
|---|---|---|
| quality | 0.30 | rating و vote_count |
| novelty | 0.15 | منتشرنشده بودن |
| category_diversity | 0.10 | کمبود/اشباع دسته در پنجره‌ی اخیر |
| genre_diversity | 0.10 | کمبود/اشباع ژانر |
| director_diversity | 0.10 | تکرار کارگردان |
| era_diversity | 0.08 | تعادل دهه‌ها |
| popularity | 0.10 | جذابیت برای مخاطب (با سیری پذیری) |
| surprise | 0.07 | کیفیت بالا ولی کمتر شناخته‌شده |

وزن‌ها و پارامترهای هر معیار در `config.json → scoring` هستند و بدون تغییر Python قابل تنظیم‌اند
(مجموع وزن‌ها باید ۱ شود).

## تنوع (Editorial Decision)

`config.json → diversity` شامل:
- `history_window` و `recent_window`
- برای هر بعد (دسته/ژانر/کارگردان/دهه): `hard_limit`، `soft_limit`، `max_consecutive`

روال: ابتدا `hard_limit` در پنجره‌ی اخیر و محدودیت streak اعمال می‌شود؛ اگر هیچ کاندیدایی
نماند، فقط `soft_limit` (کم‌ترین تخلف) اعمال می‌شود. در پایان، با
`weighted_selection` (Top-N + temperature) انتخاب نهایی برای حفظ تنوع انجام می‌شود.

## زاویه‌ی سردبیری

`config.json → angles`:
- `priority`: ترتیب سنجش قوانین
- `rules`: شرایط هر angle (مثلاً «highly_rated» نیاز به rating≥8.3 و رأی≥3000)
- `default_angle`: سقوط اگر هیچ قانونی جور نبود

زاویه‌ها: highly_rated، hidden_gem، director_spotlight، award_recognition، modern_classic،
classic_recommendation، short_runtime، influential_film، decade_recommendation،
genre_recommendation، weekend_recommendation.

## قالب کپشن

`config.json → content.templates` برای هر angle یک الگو دارد (ترتیب بلاک‌ها) و
`content.block_template` قالب هر بلاک را می‌دهد. بلاک‌هایی که مقدار ندارند خودکار حذف می‌شوند.
برای تغییر متن یا ترتیب، فقط config را تغییر بده.

## Quality Gate

`config.json → quality_gate`: بررسی عنوان، overview فارسی، پوستر، امتیاز حداقلی، معتبر بودن
دسته، نبودن در تاریخچه، و طول کپشن. در صورت شکست، سیستم کاندیدای بعدی را امتحان می‌کند.

## حافظه / Performance Memory

هر پست شامل: id، عنوان، سال، دسته، ژانرها، کارگردان، دهه، زمان‌پست، امتیاز نهایی، تفکیک
امتیاز، زاویه، کپشن، پوستر، وضعیت. برای compatibility با ورودی‌های قدیمی، `persistence`
مهاجرت خودکار انجام می‌دهد.

`meta.performance` صرفاً placeholder است (views/reactions/comments از واقعیِ تلگرام هنوز
گرفته نمی‌شود و **هیچ metric ساختگی ایجاد نمی‌شود**). اگر بعداً بخواهی، فقط یک مرحله‌ی
گرفتن آمار پست به `record_history` اضافه می‌شود.

---

## اجرا

### محلی / تست

```
pip install -r requirements.txt
set TMDB_API_KEY=...; set TELEGRAM_BOT_TOKEN=...; set TELEGRAM_CHANNEL_ID=...
python main.py
```

برای شبیه‌سازی بدون ارسال واقعی به تلگرام، `posting.dry_run` را در `config.json` روی `true`
بگذار (هیچ پستی ارسال نمی‌شود).

### GitHub Actions

دقیقاً مثل قبل: سه Secret موجود (`TMDB_API_KEY`، `TELEGRAM_BOT_TOKEN`، `TELEGRAM_CHANNEL_ID`)
کافی‌اند و هیچ Secret جدیدی لازم نیست. Workflow هر ۲ روز یکبار اجرا می‌شود، `data/posted.json`
را به‌روزرسانی و commit می‌کند (خودکار).

## تست

```
python -m unittest discover -s tests
```

بخش‌های deterministic (امتیاز، تنوع، حافظه، angle، کپشن، گیت کیفیت، duplicate) با ۴۳ تست
بدون نیاز به شبکه پوشش داده شده‌اند.

---

## مسیرهای توسعه‌ی آینده (اختیاری — فعلاً اضافه نشده)

- **Local LLM اختیاری**: به‌عنوان ماژول جدا برای متن‌های خلاقانه‌تر، اما پولی/ارجاعی نیست
  و الان خاموش است. ازآنجاکه تصمیم‌ها هنوز rule-based هستند، افزودن آن معماری فعلی را نمی‌شکند.
- **Performance Memory واقعی**: اگر تلگرام آمار پست بدهد، `meta.performance` فعال و با داده‌ی
  واقعی پر می‌شود.
- **SQLite**: اگر حجم تاریخچه‌ها خیلی زیاد شد، می‌توان بدون تغییر سطح APIها از JSON به SQLite
  رفت؛ فعلاً JSON کافی است.