from paddock.config.allowlist import Allowlist


def test_defaults():
    a = Allowlist({})
    assert a.is_enabled("cli") is True
    assert a.is_enabled("env") is True
    assert a.is_enabled("project_toml") is False


def test_project_toml_enabled_by_true():
    assert Allowlist({"project_toml": True}).is_enabled("project_toml") is True


def test_project_toml_disabled_by_empty_list():
    assert Allowlist({"project_toml": []}).is_enabled("project_toml") is False


def test_filter_true_passes_all():
    cfg = {"image": "x", "network": "y"}
    assert Allowlist({"env": True}).filter(cfg, "env") == cfg


def test_filter_false_blocks_all():
    assert (
        Allowlist({"project_toml": False}).filter({"image": "x"}, "project_toml") == {}
    )


def test_filter_key_list_keeps_listed():
    cfg = {"image": "x", "network": "y"}
    assert Allowlist({"env": ["image"]}).filter(cfg, "env") == {"image": "x"}


def test_filter_dotted_path_descends():
    cfg = {"build": {"dockerfile": "/p/D", "context": "/p"}}
    assert Allowlist({"env": ["build.dockerfile"]}).filter(cfg, "env") == {
        "build": {"dockerfile": "/p/D"}
    }


def test_disabled_source_always_returns_empty():
    cfg = {"image": "x"}
    assert Allowlist({}).filter(cfg, "project_toml") == {}
