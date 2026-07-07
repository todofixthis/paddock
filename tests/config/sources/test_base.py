from pathlib import Path

import filters as f
import pytest

from paddock.cli import ParsedArgs
from paddock.config.context import ConfigContext
from paddock.config.sources.base import ConfigSource, LoadResult, source_registry


def _ctx(tmp_path: Path) -> ConfigContext:
    parsed = ParsedArgs(
        agent=None,
        build_args={},
        build_context=None,
        build_dockerfile=None,
        build_policy=None,
        command=[],
        config_file=None,
        dry_run=False,
        image=None,
        network=None,
        quiet=False,
        volumes={},
        workdir=None,
    )
    return ConfigContext(
        parsed=parsed,
        environ={},
        workdir=tmp_path,
        user_config_path=tmp_path / "u.toml",
    )


class _Fake(ConfigSource):
    SOURCE_KEY = "fake_test_only"
    WEIGHT = 5

    def load(self, context):
        # Return an empty valid result — non-empty content would pollute
        # the registry-driven loader and interfere with other tests.
        return LoadResult(f.FilterRunner(f.Type(dict), {}), {})


def test_registry_iteration_is_weight_ordered():
    """SortedClassRegistry iterates by WEIGHT ascending."""
    from paddock.config import sources  # noqa: F401 — triggers registration

    keys_in_order = list(source_registry.keys())
    # The five "real" sources in their expected order:
    expected = ["project_toml", "user", "project_overrides", "extra", "env", "cli"]
    # Filter out the test class
    keys_in_order = [k for k in keys_in_order if k in expected]
    assert keys_in_order == expected


def test_annotate_source_defaults_to_source_key(tmp_path):
    src = _Fake()
    result = src._annotate_source({"image": "x"})
    assert result == {"image": {"value": "x", "source": "fake_test_only"}}


def test_annotate_source_explicit_override(tmp_path):
    src = _Fake()
    result = src._annotate_source({"image": "x"}, source="custom")
    assert result["image"]["source"] == "custom"


def test_abstract_load_cannot_be_omitted():
    with pytest.raises(TypeError):

        class _Bad(ConfigSource):  # type: ignore[misc]
            SOURCE_KEY = "bad"
            WEIGHT = 99

        _Bad()  # noqa: F841
