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
    assert dropped == ["image"]


def test_user_filter_with_report_ignores_false_default():
    """The trusted user source always passes everything through, even if
    its rule is ``False`` — matching ``is_enabled``'s override."""
    al = Allowlist({"user": False}, {})
    assert al.filter_with_report({"image": "x", "network": "n"}, "user") == (
        {"image": "x", "network": "n"},
        [],
    )
