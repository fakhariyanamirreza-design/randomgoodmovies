"""توضیح‌پذیری (Explainability) — لاگ قابل‌فهم برای هر تصمیم که در GitHub Actions هم دیده می‌شود."""

import sys


def print_header(title):
    print(f"\n{'='*60}")
    print(title)
    print("=" * 60)


def print_stats(discovered, filtered):
    print(f"Candidates discovered: {discovered}")
    print(f"Candidates after filtering: {filtered}")


def print_recent_history(summary):
    print("\nRecent history:")
    if not summary:
        print("  (تاریخچه‌ای ثبت نشده)")
        return
    for label, field in [("genres", "ژانر"), ("profiles", "دسته"), ("directors", "کارگردان"), ("eras", "دهه")]:
        counts = summary.get(label, {})
        if not counts:
            continue
        items = "، ".join(f"{k}: {v}" for k, v in sorted(counts.items(), key=lambda x: -x[1]))
        print(f"  {field}: {items}")


def print_top_candidates(ranked, top_n=5):
    print("\nTop candidates:")
    for i, (total, _breakdown, cand) in enumerate(ranked[:top_n], 1):
        title = cand.get("title_fa") or cand.get("title_en")
        print(f"  {i}. {title} — {total:.1f}")


def print_selection(cand, total, breakdown, reasons, angle_decision):
    title = cand.get("title_fa") or cand.get("title_en")
    print("\nSelected:")
    print(f"  {title}")

    print(f"\nProfile:")
    print(f"  {cand.get('profile') or cand.get('profile_key')}")

    print(f"\nFinal score:")
    print(f"  {total:.1f}")

    print("\nScore breakdown:")
    for name in sorted(breakdown, key=breakdown.get, reverse=True):
        print(f"  {name}: {breakdown[name]:.1f}")

    print("\nEditorial angle:")
    if angle_decision:
        print(f"  {angle_decision.angle}")
        for reason in angle_decision.reasons:
            print(f"  - {reason}")
    else:
        print("  (در ادامه مشخص می‌شود)")

    print("\nDecision reasons:")
    for reason in reasons:
        print(f"  - {reason}")


def print_quality(result):
    print("\nContent quality:")
    if result.passed:
        print("  PASS")
    else:
        print("  FAIL")
        for err in result.errors:
            print(f"  - {err}")


def print_publish_status(ok, message=""):
    print("\nPublishing to Telegram...")
    print(f"  {'SUCCESS' if ok else 'FAILURE'} {message}")


def print_memory_status():
    print("\nMemory updated.")


def print_no_candidate(reason):
    print()
    print("هیچ کاندیدای مناسبی پیدا نشد. Publish انجام نشد.")
    print(f"دلیل: {reason}")


def print_message(text):
    print(text)


def eprint(text):
    print(text, file=sys.stderr)