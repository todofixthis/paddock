from collections.abc import Mapping

from paddock.docker.build import ImageBuilder
from paddock.docker.pull import ImagePuller, PullLog
from paddock.docker.source import BuildPolicy, ImageSource


class ImageSourceFactory:
    """Picks how a run keeps its image current from the ``build`` config."""

    @staticmethod
    def from_config(
        build_config: dict,
        *,
        agent_build_args: dict[str, str],
        environ: Mapping[str, str],
    ) -> ImageSource:
        """
        Return the image source a ``build`` config asks for.

        A ``dockerfile`` builds the image; without one, the policy pulls it
        (ADR 013).

        Args:
            build_config: The merged config's ``build`` table.
            agent_build_args: The agent's build args, which ``build.args``
                overrides.
            environ: Environment variable mapping, for the pull log's path.

        Returns:
            An ``ImageBuilder`` or an ``ImagePuller``.
        """
        policy = BuildPolicy(build_config.get("policy", "if-missing"))
        dockerfile = build_config.get("dockerfile")
        if not dockerfile:
            return ImagePuller(
                policy=policy, log=PullLog(PullLog.default_path(environ))
            )
        return ImageBuilder(
            policy=policy,
            dockerfile=dockerfile,
            context=build_config.get("context") or dockerfile.parent,
            build_args={**agent_build_args, **build_config.get("args", {})},
        )
