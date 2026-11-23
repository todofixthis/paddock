from dataclasses import dataclass
from pathlib import Path
from typing import Any

import filters as f
from filters.base import BaseFilter

from paddock.config.errors import ConfigError
from paddock.config.filters import Filepath, VolumeSpec


@dataclass(frozen=True)
class ServerSettings:
    """One server's settings, checked on disk (ADR 019).

    Built only for the server a run chooses: a stale path under a server the
    run does not use must not stop it.
    """

    image: str
    """The image to run."""

    build: dict[str, Any] | None
    """The ``build`` table with its defaults applied, or ``None`` when unset."""

    port: int | None
    """The host port to publish on loopback, or ``None`` for Docker's choice."""

    volumes: dict[str, VolumeSpec]
    """The configured mounts, keyed by resolved host path."""

    @classmethod
    def from_config(
        cls, settings: dict[str, Any], *, key: str, default_image: str | None
    ) -> "ServerSettings":
        """Check a merged ``agents.<key>.server`` table against the disk.

        Args:
            settings: The merged table, or ``{}`` where none is configured.
                Its host paths are as written; its volume values are cleaned.
            key: The server's registry key, for error messages.
            default_image: The server class's ``DEFAULT_IMAGE``.

        Returns:
            The settings with every host path expanded and resolved.

        Raises:
            ExceptionGroup: One :class:`ConfigError` per problem, each naming
                its path under ``agents.<key>.server``.
        """
        errors: list[ConfigError] = []
        label = f"agents.{key}.server"

        image = settings.get("image", default_image)
        if image is None:
            errors.append(
                ConfigError(
                    f'[{label}.image] No image is set, and server "{key}" has '
                    "no default"
                )
            )

        volumes: dict[str, VolumeSpec] = {}
        for host, spec in settings.get("volumes", {}).items():
            path = cls._host_path(host, Filepath(), f"{label}.volumes.{host}", errors)
            if path is not None:
                volumes[str(path)] = spec

        build = cls._build(settings.get("build"), f"{label}.build", errors)

        if errors:
            raise ExceptionGroup("config validation failed", errors)
        return cls(
            image=str(image),
            build=build,
            port=settings.get("port"),
            volumes=volumes,
        )

    @classmethod
    def _build(
        cls, build: dict[str, Any] | None, label: str, errors: list[ConfigError]
    ) -> dict[str, Any] | None:
        """Apply top-level ``build``'s defaults and resolve its paths.

        Args:
            build: The configured ``build`` table, or ``None``.
            label: The table's config path, for error messages.
            errors: Collects one error per path that fails.

        Returns:
            The table with every key present, or ``None`` when unset.
        """
        if build is None:
            return None
        paths: dict[str, Path | None] = {"context": None, "dockerfile": None}
        for name, is_dir in (("context", True), ("dockerfile", False)):
            if build.get(name) is not None:
                paths[name] = cls._host_path(
                    build[name], Filepath(is_dir=is_dir), f"{label}.{name}", errors
                )
        return {
            "args": build.get("args", {}),
            "context": paths["context"],
            "dockerfile": paths["dockerfile"],
            "policy": build.get("policy", "if-missing"),
        }

    @staticmethod
    def _host_path(
        value: str, path_filter: BaseFilter[Path], label: str, errors: list[ConfigError]
    ) -> Path | None:
        """Expand, resolve and check one host path.

        Args:
            value: The path as written.
            path_filter: The ``Filepath`` to check it with.
            label: The path's config path, for error messages.
            errors: Collects one error per failed check.

        Returns:
            The resolved path, or ``None`` where it failed.
        """
        runner = f.FilterRunner(f.Unicode | path_filter, value)
        if runner.is_valid():
            return runner.cleaned_data
        for messages in runner.errors.values():
            for message in messages:
                errors.append(ConfigError(f"[{label}] {message['message']}"))
        return None
