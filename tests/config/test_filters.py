from pathlib import Path

import filters as f
import pytest

from paddock.config.filters import Agent, Filepath, Volume


def test_volume_bare_path():
    """A bare container path (no mode) is normalised by appending ':ro'."""
    assert (
        f.FilterRunner(Volume, "/container/path").cleaned_data == "/container/path:ro"
    )


def test_volume_explicit_ro():
    """':ro' mode is valid and returned as-is."""
    assert (
        f.FilterRunner(Volume, "/container/path:ro").cleaned_data
        == "/container/path:ro"
    )


def test_volume_explicit_rw():
    """':rw' mode is valid and returned as-is."""
    assert (
        f.FilterRunner(Volume, "/container/path:rw").cleaned_data
        == "/container/path:rw"
    )


def test_volume_implicit_ro():
    """A path with no mode suffix has ':ro' appended."""
    assert (
        f.FilterRunner(Volume, "/container/path").cleaned_data == "/container/path:ro"
    )


def test_volume_invalid():
    """A value with more than one colon-separated segment is invalid."""
    assert not f.FilterRunner(Volume, "not:a:valid:path").is_valid()


def test_agent_string():
    """A non-empty string agent name is valid."""
    assert f.FilterRunner(Agent, "claude").cleaned_data == "claude"


def test_agent_false_string():
    """The string 'false' is mapped to boolean False."""
    assert f.FilterRunner(Agent, "false").cleaned_data is False


def test_agent_true_rejected():
    """Boolean True is not a valid agent value."""
    assert not f.FilterRunner(Agent, True).is_valid()


def test_agent_false_bool():
    """Boolean False (already a bool) passes through."""
    assert f.FilterRunner(Agent, False).cleaned_data is False


# ---------------------------------------------------------------------------
# Filepath
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _filepath_set_home(monkeypatch, tmp_path):
    """Set HOME to tmp_path for every test in this file.

    autouse=True means this applies to all tests in test_filters.py, not
    just the Filepath section. That is intentional and harmless — no other
    filter in this file reads HOME — but if a future filter does, move this
    fixture to a conftest scoped to a Filepath-only subdirectory or convert
    it to an explicit fixture.
    """
    monkeypatch.setenv("HOME", str(tmp_path))


def test_pass_none(assert_filter_passes):
    """None is always a pass-through."""
    assert_filter_passes(Filepath, None, None)


# -- tilde expansion --------------------------------------------------------


def test_pass_tilde_expansion_applied_tilde_only(assert_filter_passes, tmp_path):
    """Bare ~ expands to HOME."""
    assert_filter_passes(Filepath, "~", tmp_path.resolve())


def test_pass_tilde_expansion_applied_tilde_slash(assert_filter_passes, tmp_path):
    """~/ expands to HOME."""
    assert_filter_passes(Filepath, "~/", tmp_path.resolve())


def test_pass_tilde_expansion_applied_str(assert_filter_passes, tmp_path):
    """~/foo expands to HOME/foo (str input)."""
    target = tmp_path / "foo"
    target.mkdir()
    assert_filter_passes(Filepath, "~/foo", target.resolve())


def test_pass_tilde_expansion_applied_path_tilde_only(assert_filter_passes, tmp_path):
    """Path("~") expands to HOME."""
    assert_filter_passes(Filepath, Path("~"), tmp_path.resolve())


def test_pass_tilde_expansion_applied_path_with_segment(assert_filter_passes, tmp_path):
    """Path("~/foo") expands to HOME/foo."""
    target = tmp_path / "foo"
    target.mkdir()
    assert_filter_passes(Filepath, Path("~/foo"), target.resolve())


def test_pass_tilde_expansion_not_applied_abs(assert_filter_passes, tmp_path):
    """An absolute path without a leading tilde is returned as a Path object."""
    target = tmp_path / "file.txt"
    target.write_text("")
    assert_filter_passes(Filepath, str(target), target.resolve())


def test_pass_tilde_expansion_not_applied_tilde_in_middle(
    assert_filter_passes, tmp_path
):
    """A tilde not at the start of a path is treated as a literal character."""
    tilde_dir = tmp_path / "~in"
    tilde_dir.mkdir()
    target = tilde_dir / "middle"
    target.write_text("")
    assert_filter_passes(Filepath, str(target), target.resolve())


def test_pass_tilde_expansion_custom_home_dir(assert_filter_passes):
    """A custom home_dir overrides Path.home() for tilde expansion."""
    assert_filter_passes(
        Filepath(home_dir="/custom/home"),
        "~/project",
        Path("/custom/home/project"),
    )


# -- wrong type -------------------------------------------------------------


def test_fail_wrong_type(assert_filter_errors):
    """A value that is neither str nor Path is rejected."""
    assert_filter_errors(Filepath(home_dir="/h"), 42, [f.Type.CODE_WRONG_TYPE])


# -- resolve ----------------------------------------------------------------


def test_pass_resolve_dot_segment(assert_filter_passes, tmp_path):
    """resolve=True resolves '.' segments in paths."""
    target = tmp_path / "target.txt"
    target.write_text("")

    # Use an f-string so the '.' reaches the filter as a string — Path() would
    # normalise it away before the filter sees it.
    assert_filter_passes(
        Filepath(home_dir=tmp_path, resolve=True),
        f"{tmp_path}/./target.txt",
        target.resolve(),
    )


def test_pass_resolve_dotdot_segment(assert_filter_passes, tmp_path):
    """resolve=True resolves '..' segments in paths."""
    subdir = tmp_path / "sub"
    subdir.mkdir()
    target = tmp_path / "target.txt"
    target.write_text("")

    assert_filter_passes(
        Filepath(home_dir=tmp_path, resolve=True),
        str(subdir / ".." / "target.txt"),
        target.resolve(),
    )


def test_pass_resolve_symlink(assert_filter_passes, tmp_path):
    """resolve=True follows symlinks to their real target."""
    target = tmp_path / "target.txt"
    target.write_text("")

    link = tmp_path / "link.txt"
    link.symlink_to(target)

    assert_filter_passes(
        Filepath(home_dir=tmp_path, resolve=True),
        link,
        target.resolve(),
    )


# -- resolve: behaviour when home_dir is not set ----------------------------


def test_pass_resolve_default_home_dir_activates(assert_filter_passes, tmp_path):
    """When home_dir is not set, resolve is enabled automatically."""
    subdir = tmp_path / "sub"
    subdir.mkdir()
    target = tmp_path / "target.txt"
    target.write_text("")

    assert_filter_passes(
        Filepath,
        "~/sub/../target.txt",
        target.resolve(),
    )


def test_pass_resolve_false_skips_resolution(assert_filter_passes, tmp_path):
    """Explicit resolve=False returns the tilde-expanded Path without resolution."""
    subdir = tmp_path / "sub"
    subdir.mkdir()
    target = tmp_path / "target.txt"
    target.write_text("")

    assert_filter_passes(
        Filepath(resolve=False),
        "~/sub/../target.txt",
        tmp_path / "sub" / ".." / "target.txt",
    )


# -- resolve: behaviour when home_dir is set --------------------------------


def test_pass_resolve_defaults_off_with_home_dir(assert_filter_passes, tmp_path):
    """When home_dir is set, resolve is disabled by default."""
    subdir = tmp_path / "sub"
    subdir.mkdir()

    assert_filter_passes(
        Filepath(home_dir=tmp_path),
        "~/sub/../target.txt",
        tmp_path / "sub" / ".." / "target.txt",
    )


def test_pass_resolve_explicit_true_with_home_dir(assert_filter_passes, tmp_path):
    """Explicit resolve=True resolves paths even when home_dir is set."""
    subdir = tmp_path / "sub"
    subdir.mkdir()

    assert_filter_passes(
        Filepath(home_dir=tmp_path, resolve=True),
        "~/sub/../target.txt",
        (tmp_path / "target.txt").resolve(),
    )


# -- must_exist -------------------------------------------------------------


def test_pass_must_exist_explicit_true_valid(assert_filter_passes, tmp_path):
    """must_exist=True passes when the path exists."""
    target = tmp_path / "target.txt"
    target.write_text("")

    assert_filter_passes(Filepath(home_dir=tmp_path, must_exist=True), target)


def test_fail_must_exist_explicit_true_invalid(assert_filter_errors, tmp_path):
    """must_exist=True is invalid when the path does not exist."""
    assert_filter_errors(
        Filepath(home_dir=tmp_path, must_exist=True),
        tmp_path / "target.txt",
        [Filepath.CODE_DOES_NOT_EXIST],
    )


def test_fail_must_exist_broken_symlink(assert_filter_errors, tmp_path):
    """A broken symlink is invalid when must_exist=True and resolve=True."""
    link = tmp_path / "link.txt"
    link.symlink_to(tmp_path / "target.txt")

    assert_filter_errors(
        Filepath(home_dir=tmp_path, resolve=True, must_exist=True),
        link,
        [Filepath.CODE_DOES_NOT_EXIST],
    )


def test_pass_must_exist_false_missing(assert_filter_passes, tmp_path):
    """must_exist=False skips the existence check."""
    assert_filter_passes(
        Filepath(home_dir=tmp_path, must_exist=False),
        "~/./target.txt",
        tmp_path / "target.txt",
    )


def test_pass_must_exist_resolve_false_valid(assert_filter_passes, tmp_path):
    """must_exist=True with resolve=False: explicit .exists() check passes."""
    target = tmp_path / "target.txt"
    target.write_text("")

    assert_filter_passes(
        Filepath(home_dir=tmp_path, must_exist=True, resolve=False),
        "~/./target.txt",
        tmp_path / "." / "target.txt",
    )


def test_fail_must_exist_resolve_false_invalid(assert_filter_errors, tmp_path):
    """must_exist=True with resolve=False: .exists() check rejects a missing path."""
    assert_filter_errors(
        Filepath(home_dir=tmp_path, must_exist=True, resolve=False),
        "~/./target.txt",
        [Filepath.CODE_DOES_NOT_EXIST],
    )


# -- must_exist: behaviour when home_dir is not set -------------------------


def test_pass_must_exist_default_activates(assert_filter_passes, tmp_path):
    """When home_dir is not set, must_exist is enabled automatically."""
    target = tmp_path / "target.txt"
    target.write_text("")

    assert_filter_passes(Filepath, "~/target.txt", target.resolve())


def test_fail_must_exist_default_activates_missing(assert_filter_errors, tmp_path):
    """When home_dir is not set, missing paths are rejected automatically."""
    assert_filter_errors(
        Filepath,
        "~/missing.txt",
        [Filepath.CODE_DOES_NOT_EXIST],
    )


def test_pass_must_exist_false_overrides_default(assert_filter_passes, tmp_path):
    """Explicit must_exist=False bypasses the default existence check."""
    assert_filter_passes(
        Filepath(must_exist=False, resolve=False),
        "~/missing.txt",
        tmp_path / "missing.txt",
    )
