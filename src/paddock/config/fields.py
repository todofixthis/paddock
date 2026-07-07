# Single source of truth for the standard config key structure. Each top-level
# key maps to its nested keys (empty tuple = leaf). The allowlist directive
# list is derived from this; ``schema.py`` is hand-written and checked against
# it by a co-location test, so no code reflects into filters' private
# ``_filters`` internals.
CONFIG_FIELDS: dict[str, tuple[str, ...]] = {
    "agent": (),
    "build": ("args", "context", "dockerfile", "policy"),
    "image": (),
    "network": (),
    "volumes": (),
}


def allowlist_directives() -> list[str]:
    """Return the valid dotted paths for ``[config.allowlist]`` list entries.

    Returns:
        Top-level keys (``image``, ``agent`` …) plus nested ones
        (``build.dockerfile`` …), derived from :data:`CONFIG_FIELDS`.
    """
    out: list[str] = []
    for key, subs in CONFIG_FIELDS.items():
        out.append(key)
        out.extend(f"{key}.{sub}" for sub in subs)
    return out
