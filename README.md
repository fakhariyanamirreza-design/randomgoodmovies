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
Score              → امتیازدهی editorial بر اساس ۹ معیار وزن‌دار
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

tests/                   # ۶۳ تست unittest (بدون نیاز به شبکه)
.github/workflows/publish.yml
```

---

## امتیازدهی

امتیاز نهایی = مجموع `سهم(معیار) × max × وزن`.

| معیار | وزن پیش‌فرض | ایده |
|---|---|---|
| quality | 0.27 | rating و vote_count |
| novelty | 0.15 | منتشرنشده بودن |
| category_diversity | 0.10 | کمبود/اشباع دسته در پنجره‌ی اخیر |
| genre_diversity | 0.10 | کمبود/اشباع ژانر |
| director_diversity | 0.10 | تکرار کارگردان |
| era_diversity | 0.08 | تعادل دهه‌ها |
| popularity | 0.09 | جذابیت برای مخاطب (با سیری پذیری) |
| surprise | 0.04 | کیفیت بالا ولی کمتر شناخته‌شده |
| trending | 0.07 | «ترند روز» بودن در TMDb (هم‌پوشانی با حال‌وهوای روز) |

وزن‌ها و پارامترهای هر معیار در `config.json → scoring` هستند و بدون تغییر Python قابل تنظیم‌اند
(مجموع وزن‌ها باید ۱ شود).

## تنوع (Editorial Decision)

`config.json → diversity` شامل:
- `history_window` و `recent_window`
- برای هر بعد (دسته/ژانر/کارگردان/دهه): `hard_limit`، `soft_limit`، `max_consecutive`

روال: ابتدا `hard_limit` در پنجره‌ی اخیر و محدودیت streak اعمال می‌شود؛ اگر هیچ کاندیدایی
نماند، فقط `soft_limit` (کم‌ترین تخلف) اعمال می‌شود. در پایان، با
`weighted_selection` (Top-N + temperature) انتخاب نهایی برای حفظ تنوع انجام می‌شود.

## ترند روز (Trending)

برای اینکه محتوا «تا حدی» با چیزی که الان جلوی چشم کاربران است هم‌پوشانی داشته باشد
(رایگان و بدون LLM):

- `config.json → trending`: فیلم‌های `/trending/movie/week` TMDb به‌عنوان **منبع اضافی
  کاندیدا** وارد pool می‌شوند (فقط فیلم‌های با ریتینگ/رأی بالای آستانه).
- هر کاندیدایی که در فهرست ترند باشد وزن `trending` (0.07) را در امتیاز می‌گیرد؛ چون
  وزن کم است، صرفاً **شانس را بالا می‌برد** نه اینکه انتخاب را به سمت ترند سوگیری کامل دهد.
- زاویه‌ی `trending_now` در صدر priority با دلیل «همین حالا جزو ترندهای روز است» ثبت می‌شود.
- در کپشن، بلاک `trending_line` («🔥 همین حالا در فهرست فیلم‌های ترند روز TMDb است»)
  فقط برای فیلم‌های ترند نمایش داده می‌شود.

## زاویه‌ی سردبیری

`config.json → angles`:
- `priority`: ترتیب سنجش قوانین
- `rules`: شرایط هر angle (مثلاً «highly_rated» نیاز به rating≥8.3 و رأی≥3000)
- `default_angle`: سقوط اگر هیچ قانونی جور نبود

زاویه‌ها: trending_now، release_anniversary، director_birthday، highly_rated، hidden_gem،
director_spotlight، award_recognition، modern_classic، classic_recommendation،
short_runtime، influential_film، decade_recommendation، genre_recommendation،
weekend_recommendation.

زاویه‌های تاریخ‌محور: `release_anniversary` (سالگرد اکران) و `director_birthday` (تولد
کارگردان) بدون نیاز به هیچ API پولی — فقط از `release_date` و `person/{id}/birthday` TMDb محاسبه
می‌شوند و تا وقتی که در آن روز ویژه رخ ندهد، انتخاب نمی‌شوند.

## پوستر اصلی فیلم

پوستر با اولویت زیر انتخاب می‌شود تا دقیقاً همان پوستر اصلی (که در TMDb/IMDb دیده می‌شود)
منتشر شود:

1. `poster_path` از `movie/details` با زبان en-US (پوستر اصلی/کانونیکال TMDb)
2. بهترین پوستر انگلیسی از `movie/images?include_image_language=null,en` (پوستری که بیشترین
   رأی کاربران TMDb را دارد؛ `vote_count` اولویت دارد)
3. پوستر فارسی/محلی‌سازی‌شده — فقط آخرین راه، چون می‌تواند نسخه‌ی منطقه‌ای/جایگزین باشد

وقتی پوستر en موجود است، درخواست اضافه به `images` انجام نمی‌شود؛ اما اگر فقط پوستر fa
هست، حتماً `images` امتحان می‌شود تا نسخه‌ی محلی غلبه نکند.

## قالب کپشن

`config.json → content.templates` برای هر angle یک الگو دارد (ترتیب بلاک‌ها) و
`content.block_template` قالب هر بلاک را می‌دهد. بلاک‌هایی که مقدار ندارند خودکار حذف می‌شوند.
اگر angled قالبی نداشته باشد از `content.default_template` استفاده می‌شود (برای یکدستی ظاهری).
برای تغییر متن یا ترتیب، فقط config را تغییر بده.

قالب هر پست (پس از عنوان) به این شکل است:

- `title_fa`: هدر یکدست با ایموجی ژانر + پرچم کشور سازنده، مثلاً `💥 **تلقین** (2010) 🇺🇸`.
  نگاشت ژانر→ایموجی در `content.genre_emoji` و ایموجی پیش‌فرض در `genre_emoji_default`.
- `tagline`: اسلوگان فیلم از TMDb (اگر باشد) — به‌جای جمله‌ی ثابتِ تکراری
- `trending_line`: «همین حالا در ترند روز TMDb است» — فقط برای فیلم‌های ترند
- `occasion_line`: پیام سالگرد اکران یا تولد کارگردان (فقط در همان روز)
- `similar_movies`: ۳ فیلم مشابه از `/movie/{id}/similar` — بخش «فیلم‌های شبیه به این»
  (هدر بُلد است و یک خط خالی قبلش دارد). برای جلوگیری از پیشنهادهای عجیب، فیلم مشابه
  باید حداقل یک ژانر مشترک با فیلم اصلی داشته باشد و ریتینگ/رأیِ قابل‌قبول؛ مرتب‌سازی بر
  اساس (تعداد ژانر مشترک، امتیاز، رأی).
- `audience_line`: بر اساس بهترین فیلمِ مشابه: «اگر X را دوست داشتی، این فیلم همان حال و هواست»
- `hashtags`: در حالت `structured` هشتگ‌های پایدار «ژانر_سال_دهه» با ارقام فارسی؛ در حالت
  `keywords` پرچم‌ها از کلمات کلیدی TMDb ساخته می‌شوند

> بلاک‌های `teaser_line` و `why_line` از قالب پیش‌فرض حذف شده‌اند (درخواست کاربر)؛ موتورِ
> رندر و منطق آن‌ها همچنان در کد هست و اگر قالب را دوباره اضافه کنی کار می‌کند.

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
کافی‌اند و هیچ Secret جدیدی لازم نیست. Workflow هر روز دو بار (ساعت ۹:۱۵ و ۲۱:۱۵ به وقت تهران)
اجرا می‌شود، `data/posted.json` را به‌روزرسانی و commit می‌کند (خودکار).

## تست

```
python -m unittest discover -s tests
```

بخش‌های deterministic (امتیاز، تنوع، حافظه، angle، کپشن، گیت کیفیت، duplicate) با ۶۳ تست
بدون نیاز به شبکه پوشش داده شده‌اند.

---

## مسیرهای توسعه‌ی آینده (اختیاری — فعلاً اضافه نشده)

- **Local LLM اختیاری**: به‌عنوان ماژول جدا برای متن‌های خلاقانه‌تر، اما پولی/ارجاعی نیست
  و الان خاموش است. ازآنجاکه تصمیم‌ها هنوز rule-based هستند، افزودن آن معماری فعلی را نمی‌شکند.
- **Performance Memory واقعی**: اگر تلگرام آمار پست بدهد، `meta.performance` فعال و با داده‌ی
  واقعی پر می‌شود.
- **SQLite**: اگر حجم تاریخچه‌ها خیلی زیاد شد، می‌توان بدون تغییر سطح APIها از JSON به SQLite
  رفت؛ فعلاً JSON کافی است.