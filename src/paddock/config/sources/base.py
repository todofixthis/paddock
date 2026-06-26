from abc import ABC, abstractmethod
from typing import Any, ClassVar

import filters as f
from class_registry.base import AutoRegister
from class_registry.registry import SortedClassRegistry

from paddock.config.allowlist import Allowlist
from paddock.config.context import ConfigContext

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

    # Sections valid in a user-shaped TOML file but not part of a source's
    # standard-config output. Sources that read user-shaped files strip these
    # before returning. Hoisted to the base so the set is defined once and is
    # easy to extend.
    _META_SECTION_KEYS: ClassVar[frozenset[str]] = frozenset({"config", "projects"})

    @abstractmethod
    def load(self, context: ConfigContext) -> f.FilterRunner:
        """Read, validate, and return a :class:`filters.FilterRunner`.

        ``cleaned_data`` on the returned runner must conform to the
        ``standard_config_schema(merged=False)`` shape so the loader can merge
        runners symmetrically.

        Returns:
            A :class:`filters.FilterRunner` instance. If the physical source
            contributes nothing (missing file, no matching env vars), the
            runner should still be valid with ``cleaned_data == {}``.
        """

    def sanitise(
        self, runner: f.FilterRunner, allowlist: Allowlist | None
    ) -> f.FilterRunner:
        """Filter the loaded config based on the user-controlled allowlist.

        The default implementation is a no-op. Subclasses representing
        untrusted sources (``project_toml``, ``env``, ``cli``) override this to
        drop top-level keys not permitted by the allowlist for their
        ``SOURCE_KEY``. The override is a one-liner delegating to
        ``allowlist.filter(runner.cleaned_data, self.SOURCE_KEY)``.
        """
        return runner

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
