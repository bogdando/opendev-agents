# Long-Running Subagents and Instructional Drift

> **Note**: This document describes patterns observed in production
> deep agent systems. The SCAN protocol references are from public
> implementations; integration with the persona + search() pattern
> in this repo is untested.

## The problem: attention decay

As an agent's conversation context grows (e.g. code review iterations over
new patch-sets), the system prompt's relative attention weight drops:

```
Session start:    1K prompt / 2K context  = 50% attention
After 20K tokens: 1K prompt / 20K context = 5% attention
After 80K tokens: 1K prompt / 80K context = ~1% attention
```

The agent gradually stops following its initial instructions -
naming conventions, required parameters, review checklists. This
is **attention decay**, a property of transformer architectures,
not a bug.

Symptoms:

- Agent omits `vector_store_id` despite the advisory rule
- Security auditor stops checking for RBAC bypass
- Issues resolver skips severity classification
- Agent generates Python when told to use curl
- Agent guesses store IDs instead of discovering them

## Standard subagents vs deep agents

| Aspect | Standard subagent | Deep agent |
|--------|-------------------|------------|
| **Lifecycle** | Spawned per task, discarded after | Persistent across tasks and sessions |
| **Context** | Fresh window each invocation | Accumulated context with checkpoint resume |
| **System prompt** | Static frontmatter (`.cursor/agents/*.md`) | Structured "context engineering document" with tool-use examples, behavioral rules, few-shot patterns |
| **Memory** | None between invocations | Multi-layer: conversation → checkpoints → AGENTS.md → long-term knowledge |
| **Loop** | Receive task → execute → return | Plan → Act → Observe → Reflect (autonomous) |
| **Drift risk** | Low (short-lived, small context) | High (long sessions, large context) |

Standard Cursor/Claude subagents are short-lived - the context
never grows large enough for drift to matter. Deep agents run long
sessions where drift is inevitable without countermeasures.

## Three layers of defense

### Layer 1: Dedicated system prompt

The `.cursor/agents/*.md` file is a dedicated system prompt
injected at the start of the subagent's context, separate from
the task description. It acts as an anchor:

```markdown
---
name: security-auditor
description: ...
---

You are an OpenStack security auditor...
Always call:
    search(query="...", vector_store_id="nova-dev", top_k=5)
```

**Effective for**: Short-lived subagents where context stays
small. The persona prompt maintains high attention weight
throughout the task.

**Breaks when**: The subagent runs a long session (e.g. reviewing
multiple patches, accumulating findings). The system prompt's
relative weight decays as conversation grows.

### Layer 2: Server-side enforcement

The MCP server rejects calls that violate constraints:

- `vector_store_id` is required - omitting it returns an error
  with available stores listed
- Unknown store IDs return an error suggesting discovery
- Recovery hints on empty results guide the agent to try
  different stores

This works regardless of drift - even if the agent forgets
the rules, the server's error messages force it back on track.
The agent cannot silently do the wrong thing.

**Effective for**: Enforcing hard constraints (required params,
valid values). The error-correction loop is automatic.

**Breaks when**: The constraint is behavioral, not structural.
Server-side enforcement can't make the agent "think like a
security auditor" - it can only reject malformed tool calls.

### Layer 3: SCAN protocol (for long sessions)

For agents running 100K+ token sessions, a lightweight protocol
maintains instruction compliance through **active engagement**
rather than passive re-reading.

The key insight: output token generation creates fresh attention
links to instructions. Passive re-reading (repeating the system
prompt) does not - the model skims over familiar text.

#### How SCAN works

1. **Mark** key instruction sections with scan markers:

```markdown
You are a security auditor for OpenStack Nova.

@@SCAN_1 - What parameters are required for search()?
Always call search() with vector_store_id. Never omit it.

@@SCAN_2 - What severity levels do you report?
Report findings as Critical, High, or Medium.

@@SCAN_3 - What must you NOT do?
Never guess store IDs. Never search multiple stores in parallel.
```

2. **Scan** before each subtask (~120-300 tokens):

```
SCAN:
@@SCAN_1: search() requires vector_store_id="nova-dev"
@@SCAN_2: severity levels are Critical, High, Medium
@@SCAN_3: must discover stores, never guess or parallelize
```

3. **Check** after each subtask:

```
CHECK: @@SCAN_1 applied (used vector_store_id="nova-dev")
CHECK: @@SCAN_2 applied (reported 1 High, 2 Medium)
MISSED: @@SCAN_3 - searched two stores in parallel
```

#### Overhead

- Full scan: ~300 tokens (~0.3% of 100K context)
- Mini scan (between subtasks): ~120 tokens
- CHECK/MISSED report: ~50-100 tokens per subtask

#### What SCAN prevents

- **Parameter omission**: Agent re-confirms required params
  before each search
- **Behavioral drift**: Agent actively re-engages with its
  persona constraints
- **Prompt injection**: Maintained instruction weight resists
  adversarial context
- **Cross-agent inconsistency**: CHECK/MISSED reports propagate
  compliance status to orchestrators

## Applying to persona + search()

| Defense | Short-lived subagent | Long-running deep agent |
|---------|---------------------|------------------------|
| System prompt (`.cursor/agents/*.md`) | Sufficient | Necessary but not sufficient |
| Server enforcement (`vector_store_id` required) | Catches omissions | Same - catches omissions |
| SCAN protocol | Not needed | Essential for behavioral consistency |
| Memory / checkpoints | Not needed | Maintains state across session restarts |

### Short-lived pattern (current)

```
User: /security-auditor review this patch
  → subagent spawns with fresh context
  → system prompt dominates (high attention weight)
  → search(vector_store_id="nova-dev") - correct
  → returns findings
  → subagent context discarded
```

No drift risk - the context never grows beyond a few thousand
tokens. The system prompt stays dominant.

### Long-running pattern (deep agent)

```
User: /security-auditor review all patches in this PR series
  → deep agent spawns, persists across multiple reviews
  → patch 1: system prompt = 30% of context - correct behavior
  → patch 5: system prompt = 5% of context - starting to skip steps
  → patch 10: system prompt = 1% of context - omits vector_store_id
  → server rejects call → agent recovers (Layer 2)
  → but behavioral drift (severity classification, RBAC checks)
    is not caught by server enforcement

With SCAN:
  → before patch 5: SCAN refreshes instruction attention
  → before patch 10: SCAN refreshes again
  → behavioral compliance maintained throughout
  → CHECK/MISSED reports catch any remaining drift
```

## When to use which

**Use standard subagents** (no SCAN) when:

- Each task is bounded (one patch, one bug, one query)
- Context stays under ~20K tokens
- Server-side enforcement covers your hard constraints
- Behavioral drift doesn't have serious consequences

**Add SCAN protocol** when:

- The agent runs continuously across multiple subtasks
- Context grows beyond ~50K tokens
- Behavioral consistency matters (security audits, compliance)
- You need audit trails (CHECK/MISSED reports)
- Multiple agents coordinate and need compliance visibility

## Relationship to knowledge stores

SCAN and `search()` complement each other:

- **SCAN** maintains the agent's *behavioral* consistency - it
  keeps following its rules about *how* to search (discovery
  first, one store at a time, required parameters)
- **search()** provides *factual* consistency - the agent
  retrieves current knowledge rather than relying on stale
  training data
- **Server enforcement** provides *structural* consistency -
  malformed calls are rejected regardless of drift

Together, a long-running security auditor persona with SCAN +
search() + server enforcement maintains:

1. Behavioral compliance (SCAN: "I must check RBAC, rate
   severity, cite sources")
2. Factual accuracy (search: "What are the current Nova
   security conventions?")
3. Parameter correctness (server: "vector_store_id is required")
