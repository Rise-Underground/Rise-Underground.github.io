"""
Shared competition window logic.

The competition runs 2nd Sunday of the month, 00:00 UTC, through the
following Saturday, 23:59:59.999 UTC — one 7-day window per month.

compute_competition_window(now) always returns the window that's either
currently active OR the next upcoming one (never a past one) — so the
same function works both for "what am I counting down to" and "am I
inside a live competition right now."
"""

from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------
# TEST_MODE is off -- the real "2nd Sunday of the month" rule below is
# now live. First official window: Sep 13-19, 2026.
# ---------------------------------------------------------------------
TEST_MODE = False
TEST_WINDOW_START = datetime(2026, 8, 16, 0, 0, 0, tzinfo=timezone.utc)   # unused while TEST_MODE is off
TEST_WINDOW_END = datetime(2026, 8, 22, 23, 59, 59, 999000, tzinfo=timezone.utc)  # unused while TEST_MODE is off


def get_second_sunday_window(year, month):
    first_of_month = datetime(year, month, 1, tzinfo=timezone.utc)
    # Python's weekday(): Monday=0 ... Sunday=6
    days_to_first_sunday = (6 - first_of_month.weekday()) % 7
    first_sunday = first_of_month + timedelta(days=days_to_first_sunday)
    start = first_sunday + timedelta(days=7)
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999000)
    return start, end


def compute_competition_window(now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    if TEST_MODE:
        return TEST_WINDOW_START, TEST_WINDOW_END
    start, end = get_second_sunday_window(now.year, now.month)
    if now > end:
        next_month = now.month + 1
        next_year = now.year
        if next_month > 12:
            next_month = 1
            next_year += 1
        start, end = get_second_sunday_window(next_year, next_month)
    return start, end


if __name__ == "__main__":
    now = datetime.now(timezone.utc)
    start, end = compute_competition_window(now)
    print(f"Now: {now.isoformat()}")
    print(f"Current/next competition window: {start.isoformat()} -> {end.isoformat()}")
