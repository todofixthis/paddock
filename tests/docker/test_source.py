from datetime import datetime, timedelta, timezone

from paddock.docker.source import BuildPolicy


def test_is_due_always():
    assert BuildPolicy.ALWAYS.is_due(datetime.now(timezone.utc))


def test_is_due_if_missing_image_exists():
    assert not BuildPolicy.IF_MISSING.is_due(datetime.now(timezone.utc))


def test_is_due_if_missing_image_absent():
    assert BuildPolicy.IF_MISSING.is_due(None)


def test_is_due_daily_old_image():
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    assert BuildPolicy.DAILY.is_due(old)


def test_is_due_daily_fresh_image():
    fresh = datetime.now(timezone.utc) - timedelta(hours=1)
    assert not BuildPolicy.DAILY.is_due(fresh)


def test_is_due_weekly_old_image():
    old = datetime.now(timezone.utc) - timedelta(days=8)
    assert BuildPolicy.WEEKLY.is_due(old)
