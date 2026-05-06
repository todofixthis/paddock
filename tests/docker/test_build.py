from datetime import datetime, timedelta, timezone


from paddock.docker.build import BuildPolicy, ImageBuilder


def test_should_build_always():
    assert ImageBuilder.should_build(
        BuildPolicy.ALWAYS, image_created_at=datetime.now(timezone.utc)
    )


def test_should_build_if_missing_image_exists():
    assert not ImageBuilder.should_build(
        BuildPolicy.IF_MISSING, image_created_at=datetime.now(timezone.utc)
    )


def test_should_build_if_missing_image_absent():
    assert ImageBuilder.should_build(BuildPolicy.IF_MISSING, image_created_at=None)


def test_should_build_daily_old_image():
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    assert ImageBuilder.should_build(BuildPolicy.DAILY, image_created_at=old)


def test_should_build_daily_fresh_image():
    fresh = datetime.now(timezone.utc) - timedelta(hours=1)
    assert not ImageBuilder.should_build(BuildPolicy.DAILY, image_created_at=fresh)


def test_should_build_weekly_old_image():
    old = datetime.now(timezone.utc) - timedelta(days=8)
    assert ImageBuilder.should_build(BuildPolicy.WEEKLY, image_created_at=old)


def test_run_build_basic(mocker):
    mock_run = mocker.patch("paddock.docker.build.subprocess.run")
    ImageBuilder().run_build(
        image="myapp:latest",
        dockerfile="/path/Dockerfile",
        context="/path",
        build_args={},
    )
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert call_args[:3] == ["docker", "build", "-t"]
    assert "myapp:latest" in call_args
    assert "-f" in call_args


def test_run_build_with_args(mocker):
    mock_run = mocker.patch("paddock.docker.build.subprocess.run")
    ImageBuilder().run_build(
        image="myapp:latest",
        dockerfile="/path/Dockerfile",
        context="/path",
        build_args={"AGENT": "claude"},
    )
    call_args = mock_run.call_args[0][0]
    assert "--build-arg" in call_args
    assert "AGENT=claude" in call_args
