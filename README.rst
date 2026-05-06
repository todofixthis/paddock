paddock
=======

Launch coding agents (or a plain shell) in isolated Docker containers,
with the current working directory mounted as the workspace.

.. image:: https://img.shields.io/pypi/v/phx-paddock.svg
   :target: https://pypi.org/project/phx-paddock/
   :alt: PyPI version

.. image:: https://img.shields.io/pypi/pyversions/phx-paddock.svg
   :alt: Python versions

.. image:: https://img.shields.io/badge/licence-MIT-blue.svg
   :alt: MIT Licence

Overview
--------

``paddock`` assembles and executes a ``docker run`` command from a layered
configuration system.  Config is resolved in priority order:

1. User-level TOML  (``~/.config/paddock/config.toml``)
2. Project-level TOML  (``<workdir>/.paddock/config.toml``)
3. Extra TOML file via ``PADDOCK_CONFIG_FILE`` env var
4. Extra TOML file via ``--config-file`` CLI flag
5. ``PADDOCK_*`` environment variables
6. CLI flags

Later sources overwrite earlier ones; ``volumes`` entries are additive.

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

Place a ``config.toml`` at ``~/.config/paddock/`` (user-level) or
``<project>/.paddock/`` (project-level).  Both files are optional.

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

Any config field can be set via an environment variable by uppercasing its
name and prefixing with ``PADDOCK_``.  Nested keys are joined with ``_``:

.. code-block:: bash

   PADDOCK_IMAGE=my-claude-image
   PADDOCK_AGENT=claude
   PADDOCK_BUILD_DOCKERFILE=images/Dockerfile
   PADDOCK_BUILD_POLICY=daily
   PADDOCK_CONFIG_FILE=/path/to/extra.toml   # loads an additional TOML file

CLI flags
~~~~~~~~~

.. code-block:: text

   paddock [FLAGS] [--] [COMMAND...]

   --agent AGENT                Agent key (e.g. "claude") or "false" for a shell
   --build-args-KEY=VALUE        Build-time ARG (repeatable)
   --build-context PATH         Docker build context
   --build-dockerfile PATH      Path to Dockerfile
   --build-policy POLICY        Build policy (always|daily|if-missing|weekly)
   --config-file PATH           Load an additional TOML config file
   --dry-run                    Print the docker command and exit without running it
   --image IMAGE                Docker image
   --network NETWORK            Docker network
   --quiet                      Suppress all logging and the docker command printout
   --volume HOST:CONTAINER[:MODE]  Extra bind-mount (repeatable)
   --workdir PATH               Host path to use as the workspace (default: CWD)

Everything after the first positional argument (or after ``--``) is passed
as the container command:

.. code-block:: bash

   paddock claude --allow-dangerously-skip-permissions --continue
   paddock --image=my-claude-image -- --allow-dangerously-skip-permissions --continue


Agents
------

``claude``
~~~~~~~~~~

Runs ``claude`` inside the container.  Mounts ``~/.claude`` from the host
to ``/root/.claude:rw`` so authentication and configuration persist between
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

A ready-to-use ``Dockerfile`` is included in ``images/``.  It installs
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

Licence
-------

MIT — see ``LICENCE.txt``.
