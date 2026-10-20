from datetime import UTC, datetime, timedelta, timezone

from app.timeutils import CLINIC_TZ, as_utc, to_clinic_time


def test_naive_datetimes_are_treated_as_utc():
    # SQLite returns datetimes without tzinfo; they were stored as UTC.
    assert as_utc(datetime(2030, 1, 7, 6, 0)) == datetime(2030, 1, 7, 6, 0, tzinfo=UTC)


def test_aware_datetimes_are_converted_to_utc():
    plus_three = timezone(timedelta(hours=3))
    converted = as_utc(datetime(2030, 1, 7, 9, 0, tzinfo=plus_three))
    assert converted == datetime(2030, 1, 7, 6, 0, tzinfo=UTC)
    assert converted.utcoffset() == timedelta(0)


def test_clinic_time_is_east_africa_time():
    local = to_clinic_time(datetime(2030, 1, 7, 6, 0, tzinfo=UTC))
    assert local.utcoffset() == timedelta(hours=3)
    assert local.hour == 9
    assert local.tzinfo is CLINIC_TZ
