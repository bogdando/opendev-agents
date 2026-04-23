# Declarative Config and Install

You might need a declarative installer that wires misc knowledge sources,
agent rules, personas, skills, workflows and whatnot into workspaces and targets -
targeting Cursor (`.cursor/`), Claude Code (`.claude/`) or other tools.

This document shows an example configuration approach and the
resulting directory layout - how it would look like for a Nova repository
clonned locally.

## Overview

In a hypothetical `knowledge-installer` repository:
* A single YAML config describes **what** to install and **where**.
* An install script handles the **how** part of the job.

The installer produces three things in the local directory or installer repo tree (should be .gitignore'd then):

1. **Knowledge stores** - by each store name, a set of markdown/RST/adoc/txt files
   served by the RAG MCP server's mock backend. Each directory name becomes a
   `vector_store_id`.
2. **Generated agent files** - (sub)agent persona definitions, workflows scaffolding,
   and rules.
3. **Workspace symlinks** - all of the above symlinked into each defined target
   workspace's `.cursor/`, `.claude/`, you name it, directories for AI agents.

## Configuration format

### Global settings

An example YAML config structure may look like this:
```yaml
pull_updates: false
purge_monolithic_agents_md: true
rag_mcp_server_stores_path: ./stores

root_instructions: baseline

install_rules_targets:
  - /home/user/src/openstack/*/
```

| Field | Purpose |
|-------|---------|
| `pull_updates` | `git pull` existing cached clones on re-run |
| `purge_monolithic_agents_md` | Remove legacy monolithic `CLAUDE.md` / `AGENTS.md` from workspace targets before installing lean replacements |
| `rag_mcp_server_stores_path` | Where stores are materialized (becomes `RAG_MCP_KNOWLEDGE_DIR`) |
| `root_instructions` | Store target whose `CLAUDE.md` is copied into each workspace target's `.claude/CLAUDE.md` and symlinked as `.cursor/AGENTS.md`.  Must match a `stores[].target`.  If absent, skip — no baseline is installed.  Keep it brief; the content is always in-context for every prompt. |
| `install_rules_targets` | Glob patterns matching workspaces to populate |

### Stores

Each store entry clones or copies a local dir content into `stores/{target}/` and
optionally generates an advisory `.mdc` rule.

```yaml
stores:
  # Git repo - full clone
  - source: https://opendev.org/openstack/nova
    subdir: doc/source
    branch: main
    type: directory
    target: openstack-nova-docs
    rule: |
      ---
      description: Nova documentation (admin, config, contributor, CLI)
      globs: []
      ---

      For Nova documentation questions, call rag-knowledge MCP:

          search(query="<your query>", vector_store_id="openstack-nova-docs", top_k=5)

      The vector_store_id="openstack-nova-docs" parameter is REQUIRED.

  # Local directory in knowledge-installer repo tree - copied via rsync
  - source: ./k8s
    subdir: security
    type: directory
    target: k8s-secrets-rotation

  # Special store matching root_instructions — its CLAUDE.md becomes
  # the baseline copied into every workspace target
  - source: https://github.com/bogdando/opendev-agents
    subdir: knowledge/baseline
    type: directory
    target: baseline

  #... (openstack-dev-guidelines, openstack-project-reference, ...)
```

The `subdir` field lets multiple stores share a single cached clone of a git repo.
The `branch` field pins a specific ref.

### Personas

A persona composes multiple stores into a named agent identity with
YAML frontmatter that Cursor and Claude Code interpret.

```yaml
personas:
  - name: openstack-developer
    description: >
      SME in Nova architecture, conductor boundary, API
      microversions, object versioning, RPC patterns, DCO compliance,
      commit message conventions, and upstream OpenStack documentation.
    model: inherit
    readonly: true
    stores:
      - openstack-project-reference
      - openstack-nova-docs
      - openstack-dev-guidelines
    sme_domains:
      - openstack-project-reference
      - openstack-dev-guidelines/base.mdc
```

| Field | Purpose |
|-------|---------|
| `stores` | Listed stores' rules are inlined as search instructions |
| `sme_domains` | Emitted as `@../rules/{store}.mdc` for inline rule context |
| `model` | `inherit`, `fast`, or a model ID |
| `readonly` | Cursor only - restricts to read-only tools |
| `tools` | Claude Code only - comma-separated tool allowlist |

### Skills

Skills are reusable procedures (slash commands).  Same `source`/`subdir`
mechanics as stores:

```yaml
skills:
  - source: https://github.com/sbauza/openstack-agentic-workflows
    subdir: workflows/nova-review/.claude/skills/nova-code-review
    branch: main
    type: directory
    target: nova-code-review
```

This lets us consume and adjust the contents of existing rules/skills
definition systems like [openstack-agentic-workflows](https://github.com/sbauza/openstack-agentic-workflows), or the upstream OpenDev project called
`openstack/agentic-workflows`.

### Workflows

Workflows wire a persona to skills with optional inline rules:

```yaml
workflows:
  - name: nova-review
    description: >
      Review Nova code changes and nova-specs proposals against
      project conventions, versioning rules, and coding standards.
    persona: openstack-developer
    skills:
      - nova-code-review
      - nova-spec-review
    rules: |
      # Nova Review Workflow Rules
      ## Spec Summarizer Skill (`/sor`)
      Use this template to summarize a Nova spec:
      ```
      /nova-code-review https://review.opendev.org/<CHANGE_ID>
      ```
```

When a workflow sets `persona:`, the installer back-links its `rules.md`
into the persona file, so selecting `@openstack-developer` in Cursor
automatically loads the workflow-specific rules.

## What `install.sh` produces

Given the snippets above with `install_rules_targets: [/home/user/src/openstack/*/]`,
the installer creates:

### Knowledge repo layout

```
knowledge-installer/
├── install.yaml
├── install.sh
├── templates/
│   └── mcp.json                          ← patched with stores path + envsubst of env VARS
│
├── stores/
│   ├── openstack-nova-docs/              ← cloned from opendev.org/openstack/nova doc/source
│   │   ├── AGENTS.md -> ../../rules/openstack-nova-docs.mdc
│   │   ├── admin/
│   │   ├── configuration/
│   │   └── ...rst files...
│   ├── openstack-project-reference/      ← from sbauza/openstack-agentic-workflows + subdir
│   │   └── ...md files...
│   └── k8s-secrets-rotation/         ← copied from local ./k8s/security
│       └── ...md files...
│
├── rules/
│   ├── openstack-nova-docs.mdc           ← generated from stores[].rule
│   └── openstack-project-reference.mdc
│
├── agents/
│   └── openstack-developer.md            ← generated from personas[]
│
├── skills/
│   ├── nova-code-review/                 ← cloned from external source
│   │   └── SKILL.md
│   └── nova-spec-review/
│       └── SKILL.md
│
├── workflows/
│   └── nova-review/
│       ├── AGENTS.md                     ← references @../../agents/openstack-developer.md
│       ├── CLAUDE.md                     ← @AGENTS.md
│       ├── rules.md                      ← from workflows[].rules
│       └── .claude/skills/
│           ├── nova-code-review -> ../../../skills/nova-code-review
│           └── nova-spec-review -> ../../../skills/nova-spec-review
│
└── .cache/
    ├── opendev-agents/                   ← global rules source
    └── nova/                             ← cached git clone
```

### Workspace target layout

Each glob-matched workspace (e.g. `/home/user/src/openstack/nova/`)
gets identical `.cursor/` and `.claude/` trees:

```
/home/user/src/openstack/nova/
├── .cursor/
│   ├── mcp.json                          ← copy (patched template)
│   ├── AGENTS.md -> ../.claude/CLAUDE.md
│   ├── rules/
│   │   ├── base.mdc -> /path/to/knowledge/.cache/opendev-agents/.cursor/rules/base.mdc
│   │   ├── openstack-nova-docs.mdc -> /path/to/knowledge/rules/openstack-nova-docs.mdc
│   │   └── openstack-project-reference.mdc -> /path/to/knowledge/rules/openstack-project-reference.mdc
│   ├── agents/
│   │   └── openstack-developer.md -> /path/to/knowledge/agents/openstack-developer.md
│   ├── skills/
│   │   ├── nova-code-review -> /path/to/knowledge/skills/nova-code-review
│   │   ├── nova-spec-review -> /path/to/knowledge/skills/nova-spec-review
│   │   └── nova-review-nova-code-review -> /path/to/knowledge/skills/nova-code-review
│   └── workflows/
│       └── nova-review -> /path/to/knowledge/workflows/nova-review
│
└── .claude/
    ├── mcp.json -> ../.cursor/mcp.json
    ├── CLAUDE.md                         ← copy (from root_instructions store, if set)
    ├── rules/
    │   ├── base.md -> .../opendev-agents/.cursor/rules/base.mdc
    │   ├── base.mdc -> .../opendev-agents/.cursor/rules/base.mdc
    │   ├── openstack-nova-docs.md -> /path/to/knowledge/rules/openstack-nova-docs.mdc
    │   └── openstack-nova-docs.mdc -> /path/to/knowledge/rules/openstack-nova-docs.mdc
    ├── agents/
    │   └── openstack-developer.md -> /path/to/knowledge/agents/openstack-developer.md
    └── skills/
        ├── nova-code-review -> /path/to/knowledge/skills/nova-code-review
        └── nova-spec-review -> /path/to/knowledge/skills/nova-spec-review
```

Key differences between the two:

| Aspect | `.cursor/` | `.claude/` |
|--------|-----------|-----------|
| Rules extension | `.mdc` | `.md` + `.mdc` (duplicated link for '@../*.mdc' dereference) |
| MCP config | Copy | Symlink to `.cursor/mcp.json` |
| Baseline | Symlink to `.claude/CLAUDE.md` | Copy |
| Workflows | Symlinked | Not supported |
| Skill prefixed aliases | `{wf}-{skill}` aliases present | Not present |

Each skill can be used by its original name, or within a workflow + persona context added for it.

## Generated persona file

The `openstack-developer.md` persona file looks like this after
generation:

```markdown
---
name: openstack-developer
description: >-
  SME in Nova architecture, conductor boundary...
model: inherit
readonly: true
---

## Knowledge stores

### openstack-project-reference

For upstream OpenStack project questions (architecture, versioning...),
call rag-knowledge MCP exactly like this template -

    search(query="<your query here>", vector_store_id="openstack-project-reference", top_k=5)

The vector_store_id="openstack-project-reference" parameter is REQUIRED.

### openstack-nova-docs

For Nova documentation questions (admin guides, configuration...),
call rag-knowledge MCP exactly like this template -

    search(query="<your query here>", vector_store_id="openstack-nova-docs", top_k=5)

The vector_store_id="openstack-nova-docs" parameter is REQUIRED.

## SME domains

@../rules/openstack-project-reference.mdc
@../rules/openstack-dev-guidelines.mdc

## Other knowledge stores (MANDATORY)

Always check other instances of `rag-knowledge*` MCP
servers: discover via `knowledge://stores` for all
mcp instances concurrently in subagents; merge
results; pick the best-matching stores (at least one
for each mcp instance) and search() consequently.

## Workflows

@../workflows/nova-review/rules.md
```

The `@` references are resolved by Cursor and Claude Code at load time,
pulling in the referenced files' content as inline context.

## Usage

```bash
bash install.sh                       # uses ./install.yaml
bash install.sh /path/to/custom.yaml  # custom config

# Run tests
bats tests/install.bats
```

### Requirements

* `yq` ([kislyuk/yq](https://github.com/kislyuk/yq))
* `jq`
* `envsubst` (`gettext-base` on Debian/Ubuntu, `gettext` on RHEL/Fedora)
* `git`, `rsync`

The `templates/mcp.json` uses `${VAR}` placeholders expanded by
`envsubst` at install time - export your credentials before running.

## Relationship to opendev-agents

The [opendev-agents](https://github.com/bogdando/opendev-agents) repo
provides:

* The RAG MCP server (`rag-mcp-server`) that serves knowledge stores
* Global `.cursor/rules/*.mdc` files (base coding guidelines)
* Skills (`skills/`) for code review, spec summarization, etc.
* The MCP server spec and backend implementations (mock, confluence, solr)

The knowledge-installer repo is a consumer of opendev-agents: it clones it
into `.cache/opendev-agents/` and symlinks its rules and skills into
workspace targets alongside the stores and personas defined in
`install.yaml`.
