from datetime import UTC, datetime, timedelta

from paddock.docker.source import BuildPolicy


def test_is_due_always() -> None:
    assert BuildPolicy.ALWAYS.is_due(datetime.now(UTC))


def test_is_due_if_missing_image_exists() -> None:
    assert not BuildPolicy.IF_MISSING.is_due(datetime.now(UTC))


def test_is_due_if_missing_image_absent() -> None:
    assert BuildPolicy.IF_MISSING.is_due(None)


def test_is_due_daily_old_image() -> None:
    old = datetime.now(UTC) - timedelta(hours=25)
    assert BuildPolicy.DAILY.is_due(old)


def test_is_due_daily_fresh_image() -> None:
    fresh = datetime.now(UTC) - timedelta(hours=1)
    assert not BuildPolicy.DAILY.is_due(fresh)


def test_is_due_weekly_old_image() -> None:
    old = datetime.now(UTC) - timedelta(days=8)
    assert BuildPolicy.WEEKLY.is_due(old)
