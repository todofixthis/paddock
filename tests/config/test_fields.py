from paddock.config.fields import CONFIG_FIELDS, allowlist_directives


def test_directives_include_top_level_keys():
    """Every top-level config key is a valid directive."""
    directives = set(allowlist_directives())
    assert {"agent", "build", "image", "network", "volumes"} <= directives


def test_directives_include_nested_build_keys():
    """Nested build keys are emitted dotted."""
    directives = set(allowlist_directives())
    assert {
        "build.args",
        "build.context",
        "build.dockerfile",
        "build.policy",
    } <= directives


def test_directives_match_declaration():
    """No directive exists outside the declaration (no private reflection)."""
    expected = {
        d
        for key, subs in CONFIG_FIELDS.items()
        for d in ([key] + [f"{key}.{s}" for s in subs])
    }
    assert set(allowlist_directives()) == expected
