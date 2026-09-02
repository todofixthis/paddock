import pytest

from paddock.config.extract import ExtractProject


def test_extracts_matching_project():
    """Returns the sub-dict for the requested project key."""
    raw = {"projects": {"/abs/x": {"image": "p:1"}}, "image": "global"}
    out = ExtractProject(project="/abs/x").apply(raw)
    assert out == {"image": "p:1"}


def test_returns_empty_when_no_match():
    """Returns ``{}`` when the project key is absent."""
    raw = {"projects": {"/abs/x": {"image": "p:1"}}}
    out = ExtractProject(project="/abs/other").apply(raw)
    assert out == {}


def test_returns_empty_when_projects_section_missing():
    """Returns ``{}`` when there is no ``projects`` section."""
    out = ExtractProject(project="/x").apply({"image": "global"})
    assert out == {}


def test_invalid_input_type():
    """Non-dict input raises a filter error."""
    with pytest.raises(Exception):
        ExtractProject(project="/x").apply("not-a-dict")
