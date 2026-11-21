# Squid Proxy Sidecar

Route all outbound traffic from the paddock container through a Squid proxy running in a companion container, giving operators visibility and control over what the agent can reach.

## Motivation

Coding agents can make arbitrary outbound HTTP/S requests. Without a proxy, there is no way to audit, restrict, or replay that traffic. A sidecar proxy provides a chokepoint without modifying the agent container.

## Design sketch

- A second Docker container (the sidecar) runs Squid alongside the paddock container on a shared bridge network.
- The paddock container's `HTTP_PROXY` / `HTTPS_PROXY` env vars point at the sidecar.
- All outbound traffic flows through Squid; direct internet access from the paddock container is blocked at the network level.
- The sidecar exposes a web UI for monitoring traffic in real time.
- A policy file (mounted from the host) controls which domains/URLs are allowed or blocked.
- The sidecar's admin interfaces (Squid manager, web UI) are not reachable from within the paddock container — only from the host.

## Starting points

The agent-server work built most of what a sidecar needs:

- `ManagedContainer` (`src/paddock/docker/managed.py`) already runs a named, labelled, long-lived container on a network of its own, and knows nothing about agents. A sidecar would reuse it rather than grow a second lifecycle.
- A container on two networks needs Docker Engine 25.0 or newer. `DockerVersion` makes that check only for a run that chooses an agent server (ADR 019), so a sidecar must make it itself.
- A sidecar is a container every client shares. ADR 018 leaves that case open: it needs a decision of its own, not a reuse of the agent-server one.

## Open questions

- Which web UI? (squidguard, SquidAnalyzer, or a lightweight custom viewer)
- How to enforce that the paddock container cannot reach the sidecar's admin port — iptables rules inside the sidecar, or Docker network policy?
- Should the proxy be opt-in per-project (config flag) or always-on?
- Certificate handling for HTTPS interception (MITM CA, trust injection into the paddock container).
