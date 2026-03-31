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
* [Lightspeed](https://github.com/lightspeed-core/lightspeed-stack): BYOK ("bring your own knowledge") lets projects declare their own vector stores in `lightspeed-stack.yaml`; OKP (Offline Knowledge Portal). No formal contract format, declaring knowledge domains is config-driven.

## Agent capability negotiation

A project declares: "to contribute here, your agent needs access to: linting rules, test runner, Gerrit review API".
CI validates that contributions were made with compliant tooling.
The 'Generated-By:' / 'Assisted-By:' labels are a primitive form of this already.

Prior art:
* ARC: approved models/CLIs in guardrails, `required-permissions`, mandatory MCP servers that lower levels cannot remove. Skills declare `requires` dependencies and `mandatory` status.
* Lightspeed: `LightspeedAgentsImpl` dynamically selects which MCP tools are available per request based on context. MCP servers declared in config with auth requirements; servers missing required auth are skipped gracefully.

## Quality gates as machine-readable contracts

Not just "run tox -e pep8" in prose, but a structured declaration that any agent can consume.
Pre-commit, CI checks, review criteria expressed in a format agents can reason about.
The validation pipeline section in [linting.mdc](./.cursor/rules/linting.mdc) is manual prose today; it could be a structured contract tomorrow.

Prior art:
* ARC: `validate.py` deterministic post-sync check of merged settings vs guardrails, machine-readable coverage thresholds. Mandatory `session-recorder` skill for workflow audit trail.
* Lightspeed: automated machine-readable safety shields as llama-stack providers - strips sensitive content from RAG responses, classifies input before processing.

## Knowledge lifecycle management

How rules evolve, version, deprecate (your CLAUDE.md has no versioning).
How downstream overrides upstream (no precedence mechanism exists).
How conflicts between rules from different sources are resolved.

Prior art:
* ARC: four-level merge hierarchy (org → component → repo → user), branch pinning via `ARC_REF`, deep-merge of MCP configs, decoupled config authoring from install locations.
* Lightspeed: version gating (`MINIMAL/MAXIMAL_SUPPORTED_LLAMA_STACK_VERSION`) ensures provider compatibility; flat layered config is split between `lightspeed-stack.yaml` (application concerns) and `run.yaml` (llama-stack providers).

## Feedback loops

Agent learns from CI failures which rules it violated.
Review comments feed back into rule refinement.
RAG systems index past review discussions to improve future suggestions.

Prior art:
* ARC: structured workflow recordings uploaded to shared repo, manual feedback into rules.
* Lightspeed: conversation persistence (`/v1/conversations`), explicit feedback API (`/v1/feedback`, `/v1/feedback/status`), telemetry export. Captures user feedback on responses - closest to a structured feedback loop, though not yet wired to rule refinement.

# What's still missing?

*AI quote of a day*

> Everyone speaks MCP. Almost no one has a pluggable RAG interface natively. So if you build a RAG system as an MCP server, it works everywhere without vendor lock-in.

The optimal architecture for such an interface seems to be hybrid:

*agent → MCP server → RAG backend → vector DB*

RAG backends already exist:
* [llama-stack](https://github.com/llamastack/llama-stack) provides pluggable vector store providers with OpenAI-compatible `/v1/vector_stores/{id}/search` endpoints and built-in file search via the Responses API.
* [LiteLLM](https://docs.litellm.ai/docs/vector_stores/search) unifies vector store search behind the same OpenAI-compatible surface.
* [Lightspeed Core Stack](https://github.com/lightspeed-core/lightspeed-stack) middleware on top of llama-stack: FastAPI gateway with auth, RAG orchestration (inline context injection + tool-based retrieval), MCP server management, safety shields, and pluggable vector IO.

RAG-as-MCP servers already exist in [RHEL Lightspeed](https://github.com/rhel-lightspeed):
* [docs2db-mcp-server](https://github.com/rhel-lightspeed/docs2db-mcp-server) - FastMCP wrapper over [docs2db-api](https://github.com/rhel-lightspeed/docs2db-api) hybrid search. Returns structured chunks `{text, similarity, source, metadata}`, for the agent which routes it to its own model. Corpus built offline by [docs2db](https://github.com/rhel-lightspeed/docs2db): Docling ingest → contextual chunking → embeddings → PostgreSQL.
* [okp-mcp](https://github.com/rhel-lightspeed/okp-mcp) - MCP bridge to Solr/OKP with tools `search_documentation`, `search_solutions`, `search_cves`, `search_errata`, `search_articles`, `get_document`. Returns formatted markdown strings - ready-to-use for single-store advisory lookups in the prose rules. Harder to compose across stores (or trim to a token budget) compared to structured chunks.

See [specs/rag-mcp-server.md](./specs/rag-mcp-server.md) for a detailed design proposal.

Despite prior art, no standardized architectural style yet answers:

## Discovery

How does an agent determine which MCP servers are available and what services they provide? In REST, HATEOAS enabled dynamic discovery, but agent frameworks today lack such a standard - each invents its own configuration. Most existing frameworks restrict MCP usage to exposing Tools (actions), while we want to also leverage MCP Resources as a RAG interface for accessing external knowledge, for example: `project://nova/api-standards`.

In our prose-rule model, advisory `.mdc` rules with empty globs serve as manual discovery pointers - `rag-nova.mdc` tells the agent "Nova knowledge is available via the RAG MCP server." This works but is static, not self-describing: the agent cannot introspect what stores exist or what knowledge domains they cover without the rule file being present.

## Composition

How can tool invocations be reliably chained across multiple MCP servers while maintaining consistent error management? Unlike REST, which benefits from idempotency and standardized status codes, current agent frameworks rely on ad hoc approaches-implementing skill chains and phase commands uniquely per system without general standards.

Lightspeed's dual RAG modes (inline context injection + tool-based `file_search`) and LLM-based tool filtering across MCP servers show composition within a single session, but not across independent servers.

In the prose-rule model of this repo, the LLM agent already composes naturally: glob-activated rules inject multiple knowledge domains into a single session, and the agent reasons about which MCP tools to call and in what order. This is more flexible than formal chaining - but it is opaque, non-deterministic, and unreplayable interface.

The gap is not the ability to compose but the ability to specify, audit, and enforce compositions.

## Versioning

How is schema evolution managed for tools so as to avoid breaking existing agents? REST introduced techniques such as URL versioning and content negotiation to address similar challenges, but agents lack a standardized solution for progressing tool interfaces without disrupting interoperability.

In a prose-rule model, schema evolution is less critical for the rules themselves - an LLM adapts to rewording without breaking. The real versioning concern is *knowledge currency*: is the rule content (or the RAG corpus) up-to-date for the current release, or stale from two cycles ago? A `linting.mdc` that references removed hacking checks is silently wrong, not loudly broken.

Version metadata on knowledge stores, like `store_version` or `corpus_date`, matters more here than the tool API versioning.

## Authorization Scoping

How does a tool server specify its required permissions? While REST uses the concept of OAuth scopes for this purpose, current agent server implementations may seed permissions but typically do not provide ways for servers to self-declare their capabilities or scope requirements directly.

Lightspeed has the richest auth model observed: per-server auth patterns (file, kubernetes, client-per-request via `MCP-HEADERS`, OAuth, gateway-injected headers), graceful skip on missing auth - but this is server-side enforcement, not self-declaration of required scopes.

In our model, the primary auth concern is *data-tier*: the same RAG MCP server may serve both upstream (public) and downstream (private) knowledge stores. The advisory `.mdc` rule points the agent at a store_id, but the server must decide at query time whether this agent has credentials for that store. This is upstream/downstream access control, not the tool-level permission scoping - closer to row-level security in databases than to OAuth scopes on REST endpoints.

## Contracts

How can a project explicitly declare its dependencies on specific MCP capabilities? REST employs OpenAPI specifications to articulate such requirements. In contrast, agent ecosystems today might only validate the presence of required servers, stopping short of checking their exposed capabilities or API contracts.

Lightspeed publishes its own OpenAPI spec (`docs/openapi.json`) and exposes `/v1/providers`, `/v1/tools`, `/v1/mcp-servers` for runtime introspection - the closest to capability advertisement, but consumed by its own agents, not declared as a project dependency contract.

Our advisory `.mdc` rules are already primitive contracts: `rag-nova.mdc` declares "this project depends on Nova knowledge from the RAG MCP server." But they are prose, not machine-readable - no tooling can validate that the referenced `store_id` exists, that the MCP server exposes the expected search schema, or that the knowledge domain covers the files matched by the rule's globs.

The gap is making these declarations structured enough for automated validation, while keeping them human-readable enough to serve as prose guidance when the MCP server is unavailable.

