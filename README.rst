paddock
=======

Launch coding agents (or a plain shell) in isolated Docker containers,
with the current working directory mounted as the workspace.

Usage guides and API reference: https://phx-paddock.readthedocs.io/

.. image:: https://img.shields.io/pypi/v/phx-paddock.svg
   :target: https://pypi.org/project/phx-paddock/
   :alt: PyPI version

.. image:: https://img.shields.io/pypi/pyversions/phx-paddock.svg
   :alt: Python versions

.. image:: https://img.shields.io/badge/licence-MIT-blue.svg
   :alt: MIT Licence

.. contents:: Contents
   :backlinks: none
   :depth: 1
   :local:

Overview
--------

``paddock`` assembles and executes a ``docker run`` command from a layered
configuration system.  Sources are merged in ascending priority — later
sources overwrite earlier ones:

1. Project-level TOML  (``<workdir>/.paddock/config.toml``)
2. User-level TOML  (``$XDG_CONFIG_HOME/paddock/config.toml``, by default
   ``~/.config/paddock/config.toml``)
3. ``[projects."<path>"]`` overrides in the user TOML
4. ``PADDOCK_*`` environment variables
5. CLI flags

Higher sources win per key, except that ``volumes`` and ``build.args`` add
up across sources.  The project-level file is ignored until you
enable it; see `Configuration`_.

Requirements
------------

- Python 3.12+
- Docker (CLI must be available on ``PATH``)

Installation
------------

.. code-block:: bash

   pip install phx-paddock

Or with `uv <https://github.com/astral-sh/uv>`_:

.. code-block:: bash

   uv tool install phx-paddock

Quick Start
-----------

Drop into a plain bash shell inside the current directory:

.. code-block:: bash

   paddock --image=ubuntu:24.04 --agent=false

Run Claude Code in an isolated container:

.. code-block:: bash

   paddock --image=my-claude-image --agent=claude

Print the assembled ``docker run`` command without executing it:

.. code-block:: bash

   paddock --image=ubuntu:24.04 --agent=false --dry-run

Configuration
-------------

paddock reads ``config.toml`` from ``$XDG_CONFIG_HOME/paddock/`` (by default
``~/.config/paddock/``).  Any setting can also come from a ``PADDOCK_*``
environment variable or a command-line flag:

.. code-block:: toml

   image   = "my-claude-image:latest"
   network = "my-docker-network"

   [volumes]
   "~/datasets" = "/data:ro"

   [projects."/home/alice/code/widgets"]
   image = "widgets-dev:latest"

   [projects."/home/alice/code/widgets".build]
   dockerfile = "~/code/widgets/Dockerfile"
   policy     = "weekly"

The `configuration reference <https://phx-paddock.readthedocs.io/en/latest/usage/configuration.html>`__
covers every setting: its TOML key, environment variable and flag, its default,
and when to use it.

A project can commit its own ``.paddock/config.toml``, which paddock ignores
until you grant it keys from your user config:

.. code-block:: toml

   [projects."/home/alice/code/widgets".config.allowlist]
   project_toml = ["volumes"]

See
`project-level configuration and the allowlist <https://phx-paddock.readthedocs.io/en/latest/usage/project-config.html>`__
for what each grant hands a committed file.

Running commands
----------------

.. code-block:: text

   paddock [FLAGS] [COMMAND...]
   paddock [FLAGS] -- [ARGS...]

paddock exits with the container's exit status; ``--dry-run`` exits 0, a
config error exits 1 and an unknown flag exits 2.

With no command before it, everything after ``--`` is appended to the agent's
command:

.. code-block:: bash

   # runs: claude "fix this bug"
   paddock --agent=claude -- "fix this bug"
   # runs: claude --resume
   paddock --agent=claude -- --resume

The first positional argument before ``--`` starts a command that replaces
the agent's, running in a container still configured for that agent (its
volumes and build args).  Everything after it — ``--`` and anything that looks
like a paddock flag included — belongs to that command, so put paddock flags
first:

.. code-block:: bash

   # runs: /bin/bash
   paddock --agent=claude /bin/bash

A prompt without ``--`` in front is therefore a command: ``paddock
--agent=claude "fix this bug"`` tries to execute ``fix this bug``.  Anything
else before ``--`` must be a paddock flag, spelt in full, so ``paddock --agent=claude
--resume`` fails.  For every flag, see the
`configuration reference <https://phx-paddock.readthedocs.io/en/latest/usage/configuration.html>`__.

Agents
------

``claude``
~~~~~~~~~~

Runs ``claude`` inside the container.  Mounts ``~/.claude`` from the host
to ``/root/.claude:rw``, and ``~/.claude.json`` to ``/root/.claude.json:rw``
if it exists, so authentication, onboarding and configuration persist between
sessions.

``false`` (shell)
~~~~~~~~~~~~~~~~~

Runs ``/bin/bash``.  Useful for exploring the container environment or
running ad-hoc commands without a coding agent.

Adding agents
~~~~~~~~~~~~~

Additional agents can be registered via the ``paddock.agents`` entry-point
group in any installed package:

.. code-block:: toml

   [project.entry-points."paddock.agents"]
   my-agent = "mypackage.agents:MyAgent"

Each agent must subclass ``paddock.agents.BaseAgent`` and implement
``get_command()`` and ``get_volumes()``.

Docker Image
------------

A ready-to-use ``Dockerfile`` is included in `images/ <https://github.com/todofixthis/paddock/tree/main/images>`__.  It installs
Python (via the deadsnakes PPA), Node.js, and the selected coding agent.

Build arguments:

+--------------------+-------------------+----------------------------------------------+
| ARG                | Default           | Description                                  |
+====================+===================+==============================================+
| ``UBUNTU_VERSION`` | ``24.04``         | Ubuntu base image tag                        |
+--------------------+-------------------+----------------------------------------------+
| ``AGENT``          | ``none``          | ``claude`` or ``none``                       |
+--------------------+-------------------+----------------------------------------------+
| ``NODE_VERSION``   | ``22``            | Node.js major version                        |
+--------------------+-------------------+----------------------------------------------+
| ``PYTHON_VERSION`` | ``3.13``          | Python version (installed from deadsnakes)   |
+--------------------+-------------------+----------------------------------------------+

Build the image manually:

.. code-block:: bash

   docker build \
     --build-arg AGENT=claude \
     -t my-claude-image \
     -f images/Dockerfile .

Or set ``build.dockerfile`` in your config and let paddock build it
automatically according to your chosen policy.

For what a custom image needs, and troubleshooting one that won't start, see
`custom Docker images <https://phx-paddock.readthedocs.io/en/latest/usage/docker-images.html>`__.

Licence
-------

MIT — see `LICENCE.txt <https://github.com/todofixthis/paddock/blob/main/LICENCE.txt>`__.
