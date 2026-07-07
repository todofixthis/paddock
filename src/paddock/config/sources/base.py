from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

import filters as f
from class_registry.base import AutoRegister
from class_registry.registry import SortedClassRegistry

from paddock.config.context import ConfigContext


@dataclass
class LoadResult:
    """A source's contribution: instance config plus optional meta.

    Attributes:
        instance: Runner whose ``cleaned_data`` conforms to the standard config
            shape on success; on a malformed file, the invalid source runner.
        meta: The validated ``[config]`` section as a plain dict (``{}`` for
            sources that carry no meta). Valid by construction — it is only
            ever populated from an already-valid full runner, since a
            malformed ``[config]`` invalidates the instance runner first, so
            it needs no separate validity check.
    """

    instance: "f.FilterRunner"
    meta: dict


# Iterated in ascending WEIGHT order; the loader uses this directly as the
# merge order (lower weight = lower precedence = merged first).
# ``sort_key`` is passed as a string — ``SortedClassRegistry`` converts that
# into ``getattr(cls, "WEIGHT")``. A callable here would receive a
# ``(key, class, lookup_key)`` tuple, not just the class, so a one-arg lambda
# would break — verified against the installed ``class_registry`` source.
source_registry: SortedClassRegistry = SortedClassRegistry(
    attr_name="SOURCE_KEY",
    sort_key="WEIGHT",
)


# Inherits ``ABC`` explicitly: ``AutoRegister`` skips registering classes whose
# ``is_abstract()`` returns True, which requires both ABC inheritance AND at
# least one unimplemented ``@abstractmethod``. Without ABC the registry would
# try to register the base itself and raise on its missing ``SOURCE_KEY``.
class ConfigSource(AutoRegister(source_registry), ABC):  # type: ignore[misc]
    """Base class for a single configuration source.

    Each subclass declares two class attributes:
      * ``SOURCE_KEY`` — the canonical identifier (e.g. ``"user"``, ``"env"``).
      * ``WEIGHT`` — an integer controlling merge precedence. Lower values are
        merged first; later sources overwrite earlier ones.

    Subclasses are auto-registered into :data:`source_registry` on import via
    :class:`AutoRegister`. Subclasses MUST be initialisable with no constructor
    arguments — all per-resolve inputs come through :meth:`load` via
    :class:`ConfigContext`.
    """

    SOURCE_KEY: ClassVar[str]
    WEIGHT: ClassVar[int]

    # Default [config.allowlist] rule when the user sets none explicitly.
    # Default-deny: any new source that forgets to override this is blocked
    # until its author makes a deliberate choice.
    ALLOWLIST_DEFAULT: ClassVar[bool | list[str]] = False

    # Sections valid in a user-shaped TOML file but not part of a source's
    # standard-config output. Sources that read user-shaped files strip these
    # before returning. Hoisted to the base so the set is defined once and is
    # easy to extend.
    _META_SECTION_KEYS: ClassVar[frozenset[str]] = frozenset({"config", "projects"})

    @abstractmethod
    def load(self, context: ConfigContext) -> LoadResult:
        """Read, validate, and return a :class:`LoadResult`.

        ``cleaned_data`` on ``result.instance`` must conform to the
        ``standard_config_schema(merged=False)`` shape so the loader can merge
        runners symmetrically.

        Returns:
            A :class:`LoadResult`. If the physical source contributes nothing
            (missing file, no matching env vars), ``instance`` should still be
            valid with ``cleaned_data == {}``. Sources that carry no ``[config]``
            meta return ``meta = {}``.
        """

    def _annotate_source(self, data: dict, source: str | None = None) -> dict[str, Any]:
        """Wrap each leaf in ``data`` with ``{"value": ..., "source": source}``.

        Available to subclasses that want to attach provenance to their raw
        dicts for richer error messages. Not required by the canonical workflow.

        Args:
            data: Nested dict whose leaves are scalars (or further dicts).
            source: Source label. Defaults to ``self.SOURCE_KEY``.
        """
        label = source if source is not None else self.SOURCE_KEY
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = self._annotate_source(value, label)
            else:
                result[key] = {"value": value, "source": label}
        return result
