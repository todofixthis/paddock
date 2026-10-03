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

``volumes`` entries are additive per host path — the same host path set by a
higher-priority source replaces the earlier mapping.

The project-level file is off by default (blocked) — enable it in the user
file's ``[config.allowlist]``; see
`project-level configuration and the allowlist <https://phx-paddock.readthedocs.io/en/latest/usage/project-config.html>`__.

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

TOML files
~~~~~~~~~~

Place a ``config.toml`` at ``$XDG_CONFIG_HOME/paddock/`` (user-level) or
``<project>/.paddock/`` (project-level).  paddock uses ``~/.config`` in place
of ``XDG_CONFIG_HOME`` when it is unset, empty or not an absolute path, and
reads only that one location: with ``XDG_CONFIG_HOME`` set to an absolute path,
it never checks ``~/.config/paddock/``.  Both files are optional, and the
project-level file is off by default until you opt in from your user config:

.. code-block:: toml

   [config.allowlist]
   project_toml = true

``true`` is the blanket grant; a list such as ``project_toml = ["volumes"]``
permits only the keys it names.  See
`project-level configuration and the allowlist <https://phx-paddock.readthedocs.io/en/latest/usage/project-config.html>`__
for what each grant hands a committed file.

A config file looks like this:

.. code-block:: toml

   agent  = "claude"
   image  = "my-claude-image:latest"
   network = "my-docker-network"

   [volumes]
   "/host/path" = "/container/path:ro"

   [build]
   dockerfile = "images/Dockerfile"
   context    = "."
   policy     = "daily"

   [build.args]
   AGENT          = "claude"
   PYTHON_VERSION = "3.13"

Config fields
~~~~~~~~~~~~~

+--------------------+----------------------------+--------------------------------------------------+
| Field              | Type                       | Description                                      |
+====================+============================+==================================================+
| ``agent``          | ``string`` or ``false``    | Agent key (``"claude"``) or ``false`` for shell  |
+--------------------+----------------------------+--------------------------------------------------+
| ``image``          | ``string``                 | Docker image to run (required)                   |
+--------------------+----------------------------+--------------------------------------------------+
| ``network``        | ``string`` (optional)      | Docker network to attach the container to        |
+--------------------+----------------------------+--------------------------------------------------+
| ``volumes``        | ``{host: container}`` map  | Extra bind-mounts; container path may end        |
|                    |                            | in ``:ro`` or ``:rw`` (bare path defaults to     |
|                    |                            | ``:ro``)                                         |
+--------------------+----------------------------+--------------------------------------------------+
| ``build``          | sub-table (optional)       | Image auto-build settings (see below)            |
+--------------------+----------------------------+--------------------------------------------------+

Build sub-table
~~~~~~~~~~~~~~~

+----------------+---------------------------------------------+-------------------------------------------+
| Field          | Type                                        | Description                               |
+================+=============================================+===========================================+
| ``dockerfile`` | ``string``                                  | Path to the Dockerfile (required if build |
|                |                                             | table is present)                         |
+----------------+---------------------------------------------+-------------------------------------------+
| ``context``    | ``string`` (optional)                       | Docker build context path                 |
+----------------+---------------------------------------------+-------------------------------------------+
| ``policy``     | ``"always"`` / ``"daily"`` /                | When to rebuild the image                 |
|                | ``"if-missing"`` / ``"weekly"``             |                                           |
+----------------+---------------------------------------------+-------------------------------------------+
| ``args``       | ``{name: value}`` map (optional)            | Build-time ``--build-arg`` values         |
+----------------+---------------------------------------------+-------------------------------------------+

Environment variables
~~~~~~~~~~~~~~~~~~~~~

Six config fields can be set via an environment variable, by uppercasing the
field name and prefixing it with ``PADDOCK_``.  Nested keys are joined with
``_``:

.. code-block:: bash

   PADDOCK_AGENT=claude
   PADDOCK_BUILD_CONTEXT=.
   PADDOCK_BUILD_DOCKERFILE=images/Dockerfile
   PADDOCK_BUILD_POLICY=daily
   PADDOCK_IMAGE=my-claude-image
   PADDOCK_NETWORK=my-docker-network

``volumes`` and ``build.args`` have no environment-variable form — set them in a
TOML file, or pass ``--volume`` / ``--build-args-KEY=VALUE`` on the command
line.  ``PADDOCK_BUILD_ARGS`` is ignored rather than rejected.  Any other
unrecognised ``PADDOCK_*`` name is a fatal config error, so a typo stops the
run:

.. code-block:: text

   [env:foo] Unexpected key "foo".

CLI flags
~~~~~~~~~

.. code-block:: text

   paddock [FLAGS] [COMMAND...]
   paddock [FLAGS] -- [ARGS...]

   --agent AGENT                Agent key (e.g. "claude") or "false" for a shell
   --build-args-KEY=VALUE        Build-time ARG (repeatable)
   --build-context PATH         Docker build context
   --build-dockerfile PATH      Path to Dockerfile
   --build-policy POLICY        Build policy (always|daily|if-missing|weekly)
   --dry-run                    Print the docker command and exit without running it
   --image IMAGE                Docker image
   --network NETWORK            Docker network
   --quiet                      Suppress all logging and the docker command printout
   --version                    Print the paddock version and exit
   --volume HOST:CONTAINER[:MODE]  Extra bind-mount (repeatable)
   --workdir PATH               Host path to use as the workspace (default: CWD)

``--workdir`` is resolved to an absolute real path — symlinks followed —
before it is used for the ``[projects]`` lookup and for the mounts.

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
else before ``--`` must be a paddock flag, spelled in full, so ``paddock --agent=claude
--resume`` fails.


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

Or set a ``[build]`` table in your config and let paddock build it
automatically according to your chosen policy.

For what a custom image needs, and troubleshooting one that won't start, see
`custom Docker images <https://phx-paddock.readthedocs.io/en/latest/usage/docker-images.html>`__.

Licence
-------

MIT — see `LICENCE.txt <https://github.com/todofixthis/paddock/blob/main/LICENCE.txt>`__.
