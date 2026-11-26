ARG UBUNTU_VERSION=26.04

FROM ubuntu:${UBUNTU_VERSION}

# Each ARG below sits directly above the first step that uses it. Docker hands
# an ARG to every RUN after its declaration, so a pin declared at the top would
# rebuild every layer whenever Renovate bumped it; here a bump rebuilds its own
# step and those after it. The agent comes last: it is bumped most often.

# Prevent interactive prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive

# renovate: datasource=python-version depName=python versioning=python
ARG PYTHON_VERSION=3.13
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    "python${PYTHON_VERSION}" \
    "python${PYTHON_VERSION}-venv" \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (npm installs OpenCode)
# renovate: datasource=node-version depName=node versioning=node
ARG NODE_VERSION=26
RUN curl -fsSL "https://deb.nodesource.com/setup_${NODE_VERSION}.x" | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install OpenCode. One image serves both of its containers: the server, which
# runs the agent's tools and so needs the toolchain above, and the client,
# which is thereby at the server's version.
#
# paddock passes the agent's name with every build. This image is OpenCode's
# whatever that name is; declaring the argument keeps Docker from warning that
# it went unused.
ARG AGENT=opencode
# renovate: datasource=npm depName=@opencode/cli
ARG OPENCODE_VERSION=2.4.1
RUN npm install -g "@opencode/cli@${OPENCODE_VERSION}"
