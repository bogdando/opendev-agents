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

Upstream declares what knowledge subsystems exist (style, testing, database, API, messaging...)
Globs define activation context (which files trigger which rules)
MCP references point to external knowledge without coupling to implementation
Downstream fulfills the contracts however it wants

## Agent capability negotiation

A project declares: "to contribute here, your agent needs access to: linting rules, test runner, Gerrit review API"
CI validates that contributions were made with compliant tooling
The 'Generated-By:' / 'Assisted-By:' labels are a primitive form of this already

## Quality gates as machine-readable contracts

Not just "run tox -e pep8" in prose, but a structured declaration that any agent can consume
Pre-commit, CI checks, review criteria expressed in a format agents can reason about
The validation pipeline section in [linting.mdc](./.cursor/rules/linting.mdc) is manual prose today; it could be a structured contract tomorrow

## Knowledge lifecycle management

How rules evolve, version, deprecate (your CLAUDE.md has no versioning)
How downstream overrides upstream (no precedence mechanism exists)
How conflicts between rules from different sources are resolved

## Feedback loops

Agent learns from CI failures which rules it violated
Review comments feed back into rule refinement
RAG systems index past review discussions to improve future suggestions

# What's missing?

The thing that would be "REST for agents" - is a standardized architectural style that answers:

**Discovery**: How does an agent find which MCP servers exist and what they offer? (REST had HATEOAS; agents have nothing standardized)

**Composition**: How do you chain tool calls across multiple servers with consistent error handling? (REST had idempotency and status codes; agents wing it)

**Versioning**: How do you evolve tool schemas without breaking agents? (REST had URL versioning, content negotiation; MCP has nothing)

**Authorization scoping**: How does a tool server declare what permissions it needs? (REST had OAuth scopes; MCP has basic capability negotiation)

**Contracts**: How does a project declare "I depend on these MCP capabilities"? (REST had OpenAPI specs vendored or linked; agents have prose in rule files)