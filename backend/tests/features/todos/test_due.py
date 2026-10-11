from datetime import date, datetime, timezone

import pytest

from app.features.todos.due import due_soon_range, is_due_soon, utc_now

NOW = datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)


def test_utc_now_is_timezone_aware_utc():
    assert utc_now().utcoffset().total_seconds() == 0


def test_due_soon_range_spans_today_through_end_of_window_day():
    assert due_soon_range(NOW) == (date(2026, 10, 15), date(2026, 10, 17))


@pytest.mark.parametrize("due,expected", [
    (date(2026, 10, 14), False),
    (date(2026, 10, 15), True),
    (date(2026, 10, 17), True),
    (date(2026, 10, 18), False),
])
def test_is_due_soon_checks_inclusive_window(due, expected):
    assert is_due_soon(due, False, NOW) is expected


def test_is_due_soon_false_when_completed():
    assert is_due_soon(date(2026, 10, 15), True, NOW) is False


def test_is_due_soon_false_without_due_date():
    assert is_due_soon(None, False, NOW) is False
