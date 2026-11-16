API Reference
=============

Agents
------
Agents are discovered through the ``paddock.agents`` entry-point group; a new
agent subclasses :py:class:`paddock.agents.BaseAgent`.

.. automodule:: paddock.agents

Servers
-------
Servers are discovered through the ``paddock.servers`` entry-point group; a new
server subclasses :py:class:`paddock.agents.servers.BaseServer`.

.. automodule:: paddock.agents.servers

.. autoclass:: paddock.config.filters.VolumeSpec
