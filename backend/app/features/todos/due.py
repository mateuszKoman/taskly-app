from datetime import date, datetime, timedelta, timezone

DUE_SOON_WINDOW = timedelta(hours=48)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def due_soon_range(now: datetime) -> tuple[date, date]:
    """Due dates from today through the day the 48-hour window ends, inclusive."""
    return now.date(), (now + DUE_SOON_WINDOW).date()


def is_due_soon(due_date: date | None, completed: bool, now: datetime) -> bool:
    if completed or due_date is None:
        return False
    start, end = due_soon_range(now)
    return start <= due_date <= end
