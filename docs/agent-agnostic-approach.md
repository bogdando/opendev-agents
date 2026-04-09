# Agent-Agnostic Approach to RAG Knowledge Stores via MCP

> **Note**: This document describes an untested approach. The
> `.mdc`-based Cursor implementation in this repo is the tested
> reference. The `AGENTS.md` examples below are provided as a
> starting point for porting to other tools.

## Problem

The `.mdc` rule format (`.cursor/rules/*.mdc`) is Cursor-only. To
make RAG knowledge store instructions portable across coding agents,
we need an approach that works with `AGENTS.md` — the format read
by 20+ tools.

## Format support matrix

| Format | Who reads it |
|--------|-------------|
| `.cursor/rules/*.mdc` | Cursor only |
| `AGENTS.md` | Codex, Copilot, Cursor, Windsurf, Gemini CLI, Devin, Amp, Aider, and others |
| `CLAUDE.md` | Claude Code only |
| `GEMINI.md` | Gemini CLI only |

## MCP support matrix

The `search()` tool is exposed by the `rag-knowledge` MCP server.
Any tool that supports **both** `AGENTS.md` **and** MCP can call it:

| Tool | AGENTS.md | MCP | Would call `search()`? |
|------|-----------|-----|----------------------|
| Cursor | yes | yes (`.cursor/mcp.json`) | yes |
| Claude Code | via `CLAUDE.md` | yes (`claude mcp add`) | yes |
| Codex CLI | yes | yes | yes |
| GitHub Copilot | yes | yes (VS Code MCP settings) | yes |
| Windsurf | yes | yes | yes |
| Gemini CLI | yes | limited | unclear |
| Aider | yes | no native MCP | no |
| Devin | yes | cloud-only MCP | unlikely for local server |

## What changes with AGENTS.md

`.mdc` has two features `AGENTS.md` lacks:

1. **Glob-based activation** — `.mdc` rules can activate only when
   certain files are open. `AGENTS.md` is always visible (equivalent
   to `alwaysApply: true`).
2. **Multiple scoped files** — You can have `rag-nova-dev.mdc` and
   `rag-openstack.mdc` as separate rules. `AGENTS.md` is one file
   per directory (though subdirectory `AGENTS.md` files scope to
   that subtree).

For the RAG use case, both advisory rules (`rag-knowledge-mcp.mdc`
and `rag-nova-dev.mdc`) already use `alwaysApply: true` / `globs:
[]`, so the activation difference doesn't matter — they're
equivalent to always-on.

## Example: AGENTS.md with RAG knowledge stores

The current two `.mdc` files would merge into a single `AGENTS.md`
section. The `search()` tool and progressive discovery work
identically — they're MCP-level, not format-level.

```markdown
# AGENTS.md  (repo root)

## RAG Knowledge Stores

This project uses a RAG MCP server (`rag-knowledge`) to provide
searchable knowledge stores. The `search` tool requires a
`vector_store_id` parameter — the server rejects calls without it.

### Progressive discovery (mandatory)

Do NOT guess store IDs. Do NOT search multiple stores in parallel.

1. **Check if you already know the store** — e.g. for Nova
   development questions, use `vector_store_id="nova-dev"`.
2. **Otherwise discover** — read MCP resource
   `knowledge://stores` to list available stores. Wait for the
   result before proceeding.
3. **Pick one store** from the catalog based on the question.
4. **Search once**:

       search(query="...", vector_store_id="<id>", top_k=5)

   Only search a different store after reviewing the first result.

### Known stores

- `nova-dev` — Nova development: architecture, review conventions,
  workflow skills, agent personas.

### MCP server configuration

Each tool has its own MCP config location:

- **Cursor**: `.cursor/mcp.json`
- **Claude Code**: `claude mcp add rag-knowledge`
- **VS Code / Copilot**: `.vscode/mcp.json`
- **Codex CLI**: `codex --mcp-config`

Server command: `rag-mcp-server`
Required env: `RAG_MCP_BACKEND=mock`,
`RAG_MCP_KNOWLEDGE_DIR=<absolute path to knowledge/>`
```

## Per-store scoping with subdirectory AGENTS.md

With `.mdc` you can add a new store-specific rule (e.g.
`rag-cinder-dev.mdc`) without touching the general file. With
`AGENTS.md`, you can achieve similar scoping using subdirectory
files — some tools (Codex, Copilot) traverse subdirectory
`AGENTS.md` files automatically:

```
knowledge/
  nova-dev/
    AGENTS.md      ← "this store covers Nova development"
  cinder-dev/
    AGENTS.md      ← "this store covers Cinder development"
```

Each subdirectory `AGENTS.md` would contain store-specific
instructions, equivalent to a store-specific `.mdc` advisory rule.

## Dual maintenance

For maximum portability, maintain both:

- `.cursor/rules/*.mdc` — for Cursor's glob/frontmatter features
- `AGENTS.md` — for everything else

The content is nearly identical; it's just the packaging that
differs. The `search()` call, progressive discovery sequence, and
`vector_store_id` enforcement are MCP-level concerns that work the
same regardless of how the instructions reach the agent.
