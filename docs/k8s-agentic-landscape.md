# Kubernetes Agentic Tooling Landscape

> **Status**: Analysis - reference document.

## Scope

This document analyzes how Kubernetes-native agentic projects
[NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell),
[Kuadrant MCP Gateway](https://github.com/Kuadrant/mcp-gateway), and
[Kagenti Operator](https://github.com/kagenti/kagenti-operator) help
making agentic SDLC workflows more secure, and how these relate to Lightspeed core stack.

## The projects

### NVIDIA OpenShell

A safe, private sandbox runtime for autonomous AI agents. Each sandbox
runs in an isolated container (on K3s inside Docker) with declarative
YAML policies enforced across four domains:

| Policy domain | Scope | Hot-reloadable? |
|---------------|-------|-----------------|
| Filesystem | Prevent reads/writes outside allowed paths | No (locked at creation) |
| Network | Block unauthorized outbound connections | Yes |
| Process | Block privilege escalation, dangerous syscalls | No (locked at creation) |
| Inference | Reroute model API calls to controlled backends | Yes |

The **Privacy Router** intercepts outbound LLM API calls from the sandbox and does one of three things:

1. **Allows** -- destination and binary match a policy block
2. **Routes for inference** -- strips caller credentials, injects
   backend credentials, forwards to the managed model
3. **Denies** -- blocks the request and logs it

This makes OpenShell's Privacy Router a candidate implementation of
the "transparent LLM proxy" pattern described as Option E in the
[lightspeed-core-solr spec](../specs/lightspeed-core-solr.md#option-e-lightspeed-as-transparent-llm-proxy-guardrails--rag-injection) --
an alternative gateway to Lightspeed for RAG injection and
guardrails.

### Kuadrant MCP Gateway

An Envoy-based gateway that aggregates multiple MCP servers behind a
single endpoint with auth, rate limiting, and tool-level ACL.

| Component | Role |
|-----------|------|
| MCP Broker | Aggregates tools from multiple MCP servers into a single `tools/list` |
| MCP Router | Envoy ext_proc that parses MCP JSON-RPC, sets routing headers |
| Discovery Controller | Watches `MCPServerRegistration` CRDs, discovers servers via `HTTPRoute` |

The gateway sits in front of MCP servers (like `rag-mcp-server`) and
provides:

- **Single entrypoint** -- agents connect to one MCP endpoint, get
  tools from many servers
- **OAuth / Keycloak ACL** -- tool-level permissions (which agent can
  call which tool)
- **Rate limiting** -- per-agent or per-tool rate limits via Kuadrant
  policies
- **Tool prefixing** -- namespace tools to avoid collisions
  (`weather_get_forecast` vs `calendar_get_events`)

The design philosophy is "defense in depth": agents are treated as
adversarial because LLMs can make mistakes, and MCP tools may enable
destructive actions.

**Relationship to our architecture**: MCP Gateway would sit between
agents and `rag-mcp-server`. Instead of agents connecting directly to
`rag-mcp-server`, they connect to the gateway, which routes `search()`
calls to the appropriate backend. This adds auth, rate limiting, and
observability without changing `rag-mcp-server` code.

### Kagenti Operator

A Kubernetes operator for deploying, discovering, and securing AI
agents as K8s workloads.

| CRD | Purpose |
|-----|---------|
| AgentCard | Discovers and indexes agent metadata via [A2A protocol](https://google.github.io/A2A/) |
| AgentRuntime | Declarative enrollment of workloads into the agent platform (labels, identity, observability) |

Key capabilities:

- **Agent discovery** -- auto-creates `AgentCard` resources for
  labeled Deployments/StatefulSets, fetches agent metadata from
  `/.well-known/agent-card.json`
- **Signature verification** -- JWS-based cryptographic verification
  of agent cards (RSA, ECDSA) via SPIRE trust bundles
- **Identity binding** -- SPIFFE-based workload identity with
  allowlist enforcement
- **NetworkPolicy enforcement** -- verified agents get permissive
  policies; unverified agents get restrictive ones
- **AuthBridge webhook** -- injects sidecar containers (envoy-proxy,
  SPIFFE helper, client registration) into agent pods

Kagenti answers "who is this agent, is it trusted, and what can it
talk to?" -- questions that the other projects don't address.

### Lightspeed stack

The existing stack in this repository:

| Component | Role |
|-----------|------|
| `rag-mcp-server` | MCP server exposing knowledge stores (mock, solr, confluence backends) |
| OLS / Lightspeed service | External RAG + LLM synthesis service |
| `okp-mcp` | Solr BM25 client library |
| Advisory rules (`.mdc`) | Agent-side instructions for when/how to use `search()` |

## Layer analysis

Each project operates at a different layer of the agentic stack:

```
┌─────────────────────────────────────────────────────┐
│  Agent Lifecycle & Identity          [Kagenti]      │
│  Deploy, discover, verify, RBAC, NetworkPolicy      │
├─────────────────────────────────────────────────────┤
│  Agent Sandbox & LLM Proxy           [OpenShell]    │
│  Isolation, filesystem/network/process policy,      │
│  Privacy Router (inference routing + credentials)   │
├─────────────────────────────────────────────────────┤
│  MCP Tool Gateway                    [MCP Gateway]  │
│  Tool aggregation, auth, rate limiting, routing     │
├─────────────────────────────────────────────────────┤
│  Knowledge & RAG                     [Lightspeed]   │
│  rag-mcp-server, OLS, Solr, Confluence, mock        │
└─────────────────────────────────────────────────────┘
```

## Overlap and complementarity

### What overlaps

| Concern | OpenShell | MCP Gateway | Kagenti | Lightspeed |
|---------|-----------|-------------|---------|------------|
| Agent isolation | **Primary** | -- | Partial (NetworkPolicy) | -- |
| LLM request interception | **Yes** (Privacy Router) | -- | -- | **Yes** (Option E) |
| Credential injection | **Yes** (providers) | **Yes** (OAuth) | **Yes** (SPIFFE + AuthBridge) | -- |
| Tool-level auth | -- | **Primary** | -- | -- |
| Agent identity | -- | -- | **Primary** (A2A + SPIFFE) | -- |
| Network policy | **Yes** (sandbox-level) | -- | **Yes** (per-agent) | -- |
| Knowledge retrieval | -- | -- | -- | **Primary** |

### What doesn't overlap

Each project has a unique capability that no other provides:

| Unique to | Capability |
|-----------|------------|
| OpenShell | Filesystem + process policy, GPU passthrough, agent-first dev workflow |
| MCP Gateway | MCP protocol-aware Envoy routing, tool aggregation, tool prefixing |
| Kagenti | A2A agent card discovery, JWS signature verification, SPIFFE identity binding |
| Lightspeed | RAG retrieval (Solr/Confluence/mock), knowledge store discovery, embedding models |

### Where they compose

**Full stack composition:**

```
                    ┌──────────────────────┐
                    │  Kagenti Operator    │
                    │  (agent lifecycle)   │
                    └────────┬─────────────┘
                             │ deploys + discovers
                    ┌────────▼──────────────┐
                    │  OpenShell Sandbox    │
                    │  (agent runtime)      │
                    │  ┌─────────────────┐  │
                    │  │ Agent (Claude)  │  │
                    │  └──┬──────────┬───┘  │
                    │     │          │      │
                    │     │ LLM call │ MCP  │
                    │  ┌──▼───┐      │      │
                    │  │Privacy│     │      │
                    │  │Router │     │      │
                    │  └──┬────┘     │      │
                    └─────┼──────────┼──────┘
                          │          │
               ┌──────────▼──┐  ┌───▼────────────┐
               │ Upstream LLM│  │ MCP Gateway    │
               │ (+ optional │  │ (auth, routing,│
               │  RAG inject)│  │  rate limiting)│
               └─────────────┘  └───┬────────────┘
                                    │
                          ┌─────────▼──────────┐
                          │ rag-mcp-server     │
                          │ (knowledge stores) │
                          └────────────────────┘
```

**Scenario 1: Explicit RAG (Options A-D, current design)**

The agent explicitly calls `search()` via MCP. Traffic flows:

```
Agent → MCP Gateway → rag-mcp-server → Solr/Confluence/mock
```

Kagenti ensures the agent is trusted. MCP Gateway enforces that the
agent is allowed to call `search()` and rate-limits it. OpenShell
ensures the agent can't exfiltrate the retrieved knowledge.

**Scenario 2: Transparent RAG (Option E)**

The agent's LLM calls are intercepted by OpenShell's Privacy Router.
The router performs RAG retrieval and injects context before
forwarding to the upstream LLM:

```
Agent → Privacy Router → [RAG retrieval] → upstream LLM
```

The agent never calls `search()`. MCP Gateway is not involved in the
RAG path (but may still gate other MCP tools). Kagenti still manages
the agent's identity.

**Scenario 3: Hybrid**

Both paths coexist. The Privacy Router provides baseline RAG
injection for all LLM calls (Option E). The agent can also
explicitly call `search()` via MCP Gateway for targeted retrieval
(Options A-D). This gives defense-in-depth for knowledge access plus
agent control when needed.

## Implications for `rag-mcp-server`

### MCP Gateway changes nothing in `rag-mcp-server`

MCP Gateway is transparent to the MCP server. `rag-mcp-server`
continues to expose `search()`, `knowledge://stores`, etc. The
gateway handles auth, routing, and rate limiting at the Envoy layer.
The only change would be deploying `rag-mcp-server` behind an
`HTTPRoute` and creating an `MCPServerRegistration` CRD.

### OpenShell's Privacy Router could subsume Option E

If OpenShell's Privacy Router were extended with:

1. A RAG retrieval hook (query Solr/Confluence before forwarding)
2. Context injection into the system prompt
3. Content-based output filtering (beyond credential stripping)

...it would become a full Option E implementation. The key advantage
over building Option E into Lightspeed is that OpenShell already has
the proxy infrastructure, policy engine, and sandbox isolation.
Lightspeed would provide the RAG pipeline; OpenShell would provide
the interception point.

### Kagenti provides the trust layer

Today, `rag-mcp-server` has no concept of "who is calling." Any
agent that can reach the MCP endpoint can call `search()`. With
Kagenti:

- Agents would have verified identities (SPIFFE)
- MCP Gateway could use those identities for tool-level ACL
- Different agents could be authorized for different knowledge
  stores (e.g., the `nova-dev` store is only accessible to agents
  with the `openstack-developer` identity)

## Comparison with `kube-agentic-networking`

MCP Gateway explicitly tracks the
[kube-agentic-networking](https://github.com/kubernetes-sigs/kube-agentic-networking)
sig-network subproject, which is standardizing `AccessPolicy` and
agent-to-tool communication patterns in Kubernetes. Kagenti
participates in similar standardization via the A2A protocol. Both
projects expect their CRDs to converge with upstream Kubernetes
standards as they mature.

OpenShell takes a different approach: it runs its own K3s cluster
inside Docker and enforces policies at the container level, not at
the Kubernetes API level. This makes it more portable (works without
an existing K8s cluster) but less integrated with cluster-level
governance.

## Summary

| Question | Answer |
|----------|--------|
| Does OpenShell replace Lightspeed? | No. OpenShell provides the sandbox and LLM proxy; Lightspeed provides the knowledge and RAG pipeline. OpenShell's Privacy Router is where Option E would be implemented, but it needs Lightspeed's RAG backend. |
| Does MCP Gateway replace `rag-mcp-server`? | No. MCP Gateway sits in front of it, adding auth, rate limiting, and tool aggregation. `rag-mcp-server` remains the knowledge backend. |
| Does Kagenti replace either? | No. Kagenti manages agent lifecycle and identity. It's orthogonal to both tool access and knowledge retrieval. |
| Can they all compose? | Yes. The natural composition is: Kagenti (deploy + identity) → OpenShell (sandbox + LLM proxy) → MCP Gateway (tool auth) → rag-mcp-server (knowledge). |
| What about Option E? | OpenShell's Privacy Router is the closest existing implementation. Extending it with Lightspeed's RAG pipeline would give transparent RAG + guardrails without building a new proxy. |
| What about session memory? | None of these projects handle cross-session agent memory. [OpenViking](./openviking-comparison.md) fills that gap with session compression and memory extraction, and could compose as a memory layer alongside rag-mcp-server for knowledge retrieval. |
