from datetime import date, timedelta


def get_date_range(days: int, lag_days: int = 3) -> tuple[str, str]:
    """Return (start_date, end_date) as YYYY-MM-DD strings.

    Args:
        days: Number of days to look back.
        lag_days: GSC data lag (default 3 days).
    """
    end = date.today() - timedelta(days=lag_days)
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def split_into_periods(start_date: str, end_date: str, period_days: int = 30) -> list[tuple[str, str]]:
    """Split a date range into equal periods for trend analysis."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    periods = []
    current = start
    while current < end:
        period_end = min(current + timedelta(days=period_days - 1), end)
        periods.append((current.isoformat(), period_end.isoformat()))
        current = period_end + timedelta(days=1)
    return periods


def get_yoy_ranges(days: int = 90, lag_days: int = 3) -> tuple[tuple[str, str], tuple[str, str]]:
    """Return current period and same period last year."""
    current_end = date.today() - timedelta(days=lag_days)
    current_start = current_end - timedelta(days=days)
    prev_end = current_end - timedelta(days=365)
    prev_start = current_start - timedelta(days=365)
    return (
        (current_start.isoformat(), current_end.isoformat()),
        (prev_start.isoformat(), prev_end.isoformat()),
    )
