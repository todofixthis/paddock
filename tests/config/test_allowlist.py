from paddock.config.allowlist import Allowlist

# Mirrors the class defaults the loader injects.
_DEFAULTS: dict[str, bool | list[str]] = {
    "cli": True,
    "env": True,
    "project_toml": False,
    "user": True,
}


def test_class_defaults_apply_when_unset():
    al = Allowlist(_DEFAULTS, {})
    assert al.is_enabled("env") is True
    assert al.is_enabled("project_toml") is False


def test_user_is_always_enabled_even_if_default_false():
    """The trusted user source is never gated, whatever the defaults say."""
    assert Allowlist({"user": False}, {}).is_enabled("user") is True


def test_unknown_source_defaults_denied():
    """A key in neither defaults nor raw is blocked (default-deny)."""
    assert Allowlist(_DEFAULTS, {}).is_enabled("mystery") is False


def test_explicit_rule_overrides_class_default():
    al = Allowlist(_DEFAULTS, {"project_toml": True})
    assert al.is_enabled("project_toml") is True


def test_filter_with_report_lists_dropped_keys():
    al = Allowlist(_DEFAULTS, {"project_toml": ["image"]})
    kept, dropped = al.filter_with_report(
        {"image": "x", "network": "n"}, "project_toml"
    )
    assert kept == {"image": "x"}
    assert dropped == ["network"]


def test_filter_dotted_path_descends():
    """A nested dotted path keeps only the named leaf, not its siblings."""
    al = Allowlist(_DEFAULTS, {"project_toml": ["build.dockerfile"]})
    kept, dropped = al.filter_with_report(
        {"build": {"dockerfile": "Dockerfile", "context": "."}, "image": "x"},
        "project_toml",
    )
    assert kept == {"build": {"dockerfile": "Dockerfile"}}
    assert dropped == ["build.context", "image"]


def test_user_filter_with_report_ignores_false_default():
    """The trusted user source always passes everything through, even if
    its rule is ``False`` — matching ``is_enabled``'s override."""
    al = Allowlist({"user": False}, {})
    assert al.filter_with_report({"image": "x", "network": "n"}, "user") == (
        {"image": "x", "network": "n"},
        [],
    )


def test_dropped_reports_nested_leaf_paths():
    """A sibling dropped from a kept table is reported by its full path."""
    al = Allowlist(_DEFAULTS, {"project_toml": ["build.args"]})
    kept, dropped = al.filter_with_report(
        {"build": {"args": {"VERSION": "1"}, "dockerfile": "Dockerfile"}},
        "project_toml",
    )
    assert kept == {"build": {"args": {"VERSION": "1"}}}
    assert dropped == ["build.dockerfile"]


def test_dropped_lists_every_leaf_of_a_wholly_dropped_table():
    """Every leaf of a dropped table is named, not just the table."""
    al = Allowlist(_DEFAULTS, {"project_toml": ["image"]})
    kept, dropped = al.filter_with_report(
        {"build": {"context": ".", "dockerfile": "Dockerfile"}, "image": "x"},
        "project_toml",
    )
    assert kept == {"image": "x"}
    assert dropped == ["build.context", "build.dockerfile"]


def test_free_form_maps_are_reported_whole():
    """Free-form maps are reported whole.

    ``volumes`` and ``build.args`` hold user data, so their keys must never
    reach a warning.
    """
    al = Allowlist(_DEFAULTS, {"project_toml": ["image"]})
    kept, dropped = al.filter_with_report(
        {
            "build": {"args": {"SECRET": "s"}},
            "image": "x",
            "volumes": {"/etc/shadow": "/etc/shadow:ro"},
        },
        "project_toml",
    )
    assert kept == {"image": "x"}
    assert dropped == ["build.args", "volumes"]


def test_disabled_source_reports_leaf_paths():
    """A wholly disabled source reports the same dotted-path form."""
    al = Allowlist(_DEFAULTS, {"project_toml": False})
    kept, dropped = al.filter_with_report(
        {"build": {"dockerfile": "Dockerfile"}, "image": "x"}, "project_toml"
    )
    assert kept == {}
    assert dropped == ["build.dockerfile", "image"]


def test_undeclared_nested_table_reports_as_the_declared_leaf():
    """A table under a declared leaf key is reported whole."""
    al = Allowlist(_DEFAULTS, {"project_toml": ["image"]})
    kept, dropped = al.filter_with_report(
        {"image": "x", "network": {"inner": "n"}}, "project_toml"
    )
    assert kept == {"image": "x"}
    assert dropped == ["network"]
