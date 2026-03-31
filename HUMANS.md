# Glossary

* **MCP** is to AI agents what HTTP is to web browsers - a transport protocol for requesting and receiving data.
* MCP **Resources** are like GET requests - fetch known content by URI (read-only data).
* MCP **Tools** are like POST/RPC endpoints - invoke server-side logic and actions with parameters.
* **RAG** is like a search engine built on top of HTTP - it uses the transport layer but adds
  indexing, ranking, and query → retrieve → augment logic.
* 🦕 **REST "HTTP"**, but for AI agents - the GAP, what we are supposed to fill with AI-SDLC as
  conventions for how agents discover, compose, and chain capabilities
* 🦕 UNIX *socket*, but for AI agents - Local files: `CLAUDE.md`, `.cursor/rules/*.mdc`, `skills/` <-- we are here.

# So what is this all about?

**Today**: Prose rules in .mdc files, manual external MCP references.

**Tomorrow**: Structured rule schemas, declared MCP dependencies.

**Future**: Standardized SDLC agent protocol (filling the "REST" gap moment).


```bash
Local files     →  MCP server    →  (future REST-like SDLC layer)
├─ CLAUDE.md       ├─ search()      ├─ knowledge contracts
├─ AGENTS.md       ├─ resources     ├─ capability negotiation
├─ .cursor/rules/  ├─ tools         ├─ quality gates
└─ skills/         └─ prompts       └─ feedback loops

🦕 UNIX socket    🦕 HTTP          🦕 REST
```

# More on the REST moment

## Knowledge contracts

Upstream declares what knowledge subsystems exist (style, testing, database, API, messaging...).
Globs define activation context (which files trigger which rules).
MCP references point to external knowledge without coupling to implementation.
Downstream fulfills the contracts however it wants.

Prior art:
* [Ambient](https://github.com/ambient-code/workflows/blob/main/WORKFLOW_DEVELOPMENT_GUIDE.md): artifact contracts via `results` field mapping output names to file globs.
* [ARC](https://github.com/ansible-automation-platform/harness): `guardrails.arc.yaml` declares required files/sections per repo; locked instruction files are append-only at lower levels; `org.arc.mcp.json` declares MCP servers with `mandatory` flags. Does not have glob-based contextual activation (all rules load into a generated `CLAUDE.md`).

## Agent capability negotiation

A project declares: "to contribute here, your agent needs access to: linting rules, test runner, Gerrit review API".
CI validates that contributions were made with compliant tooling.
The 'Generated-By:' / 'Assisted-By:' labels are a primitive form of this already.

Prior art:
* ARC: approved models/CLIs in guardrails, `required-permissions`, mandatory MCP servers that lower levels cannot remove. Skills declare `requires` dependencies and `mandatory` status.

## Quality gates as machine-readable contracts

Not just "run tox -e pep8" in prose, but a structured declaration that any agent can consume.
Pre-commit, CI checks, review criteria expressed in a format agents can reason about.
The validation pipeline section in [linting.mdc](./.cursor/rules/linting.mdc) is manual prose today; it could be a structured contract tomorrow.

Prior art:
* ARC: `validate.py` deterministic post-sync check of merged settings vs guardrails,machine-readable coverage thresholds. Mandatory `session-recorder` skill for workflow audit trail.

## Knowledge lifecycle management

How rules evolve, version, deprecate (your CLAUDE.md has no versioning).
How downstream overrides upstream (no precedence mechanism exists).
How conflicts between rules from different sources are resolved.

Prior art:
* ARC: four-level merge hierarchy (org → component → repo → user), branch pinning via `ARC_REF`, deep-merge of MCP configs, decoupled config authoring from install locations.

## Feedback loops

Agent learns from CI failures which rules it violated.
Review comments feed back into rule refinement.
RAG systems index past review discussions to improve future suggestions.

Prior art:
* ARC: structured workflow recordings uploaded to shared repo, manual feedback into rules.

# What's still missing?

*AI quote of a day*

> Everyone speaks MCP. Almost no one has a pluggable RAG interface natively. So if you build a RAG system as an MCP server, it works everywhere without vendor lock-in.

Despite partial solutions above, no standardized architectural style yet answers:

## Discovery

How does an agent determine which MCP servers are available and what services they provide? In REST, HATEOAS enabled dynamic discovery, but agent frameworks today lack such a standard — each invents its own configuration. Most existing frameworks restrict MCP usage to exposing Tools (actions), and notably, **no implementation leverages MCP Resources as a RAG interface for sharing cross-project knowledge, even though the protocol is capable of it**.

RAG backends already exist — [llama-stack](https://github.com/llamastack/llama-stack) provides pluggable vector store providers with OpenAI-compatible `/v1/vector_stores/{id}/search` endpoints and built-in file search via the Responses API; [LiteLLM](https://docs.litellm.ai/docs/vector_stores/search) unifies vector store search behind the same OpenAI-compatible surface. The missing piece is not the backend but the **MCP server that exposes cross-project knowledge as Resources** (URI-addressable, e.g. `project://nova/api-standards`) alongside a search Tool — and a contract format for projects to declare which knowledge domains they publish and depend on.

## Composition

How can tool invocations be reliably chained across multiple MCP servers while maintaining consistent error management? Unlike REST, which benefits from idempotency and standardized status codes, current agent frameworks rely on ad hoc approaches—implementing skill chains and phase commands uniquely per system without general standards.

## Versioning

How is schema evolution managed for tools so as to avoid breaking existing agents? REST introduced techniques such as URL versioning and content negotiation to address similar challenges, but agents lack a standardized solution for progressing tool interfaces without disrupting interoperability.

## Authorization Scoping

How does a tool server specify its required permissions? While REST uses the concept of OAuth scopes for this purpose, current agent server implementations may seed permissions but typically do not provide ways for servers to self-declare their capabilities or scope requirements directly.

## Contracts

How can a project explicitly declare its dependencies on specific MCP capabilities? REST employs OpenAPI specifications to articulate such requirements. In contrast, agent ecosystems today might only validate the presence of required servers, stopping short of checking their exposed capabilities or API contracts.
