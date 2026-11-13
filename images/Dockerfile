ARG UBUNTU_VERSION=26.04

FROM ubuntu:${UBUNTU_VERSION}

ARG AGENT=none

# Version pins — updated by Renovate, which reads each pin's annotation
# renovate: datasource=npm depName=@anthropic-ai/claude-code
ARG CLAUDE_CODE_VERSION=2.1.311
# renovate: datasource=node-version depName=node versioning=node
ARG NODE_VERSION=26
# renovate: datasource=python-version depName=python versioning=python
ARG PYTHON_VERSION=3.13

# Prevent interactive prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive

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

# Install Node.js (required for Claude Code)
RUN curl -fsSL "https://deb.nodesource.com/setup_${NODE_VERSION}.x" | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install coding agent based on ARG
RUN case "$AGENT" in \
    claude) npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" ;; \
    none) echo "No agent selected" ;; \
    *) echo "Unknown agent: $AGENT" && exit 1 ;; \
    esac
