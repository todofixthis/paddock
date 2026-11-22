# Let Users Control an Agent's Environment and Common Settings

Paddock passes a container the environment variables its agent's class chooses, and a
user cannot add to them or change them. Telemetry is the case that raised it: the client of Omnigent, an agent planned in
`docs/superpowers/specs/2026-11-15-agent-client-server-design.md`, sends it unless a
variable of its own is set. Each agent spells such a switch differently, and a user who
wants it off has to bake the variable into their image.

## Suggested change

Two parts, which could land separately.

- **Environment variables in config.** A way to set variables on an agent's client, and
  on its server, from the user's config.
- **Named settings an agent translates.** A setting such as `telemetry = false` under
  `[agents.opencode]`, which the agent's class turns into whatever variable or flag
  that agent reads. The user states the intent once and does not need to know each
  agent's spelling.

A further step would set one for every agent at once, as `["agents.*"] telemetry =
false` might. That needs its own analysis before it is planned.

## Open questions

- Where a variable may be set from. A project file that can set environment variables
  can redirect an agent to another API endpoint or switch off a safeguard. `agents` is
  one allowlist grant with no finer parts (ADR 017), so a source already granted it
  would get any new `agents.<name>` key with it: this one needs a gate of its own, as
  ADR 019 gave `server`, and some names may need refusing outright.
- Secrets. A value in a config file is printed in the `docker run` line unless it is
  classed as secret (ADR 019), and a token in a TOML file is a different risk from one
  in the environment.
- How a user's variable ranks against one the agent's class sets, and against the
  server's secret, which must not be overridable.
- Which settings are common enough to name. Telemetry and update checks are the two
  seen so far.
- What an agent does with a named setting it has no equivalent for: ignore it, warn, or
  stop.
- For the wildcard form: how it merges with a per-agent value, whether it reaches
  agents installed later, and how it fits ADR 017's rule that settings for an unknown
  agent only warn.
- Whether a server's variables changing is drift (ADR 019 says a safe variable's value
  is).

## Why deferred

Raised while deciding whether paddock should switch Omnigent's telemetry off by
default; it leaves each agent's default alone for now. The general mechanism touches
the allowlist and the config schema, which is more than that question warranted.
