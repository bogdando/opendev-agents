# OpenStack Commit Message Format

Comprehensive formatting rules for OpenStack-style commit messages.

## Subject Line

- **Maximum 50 characters** (hard limit)
- **No period at the end**
- **Imperative mood**: "Add" not "Added", "Fix" not "Fixed"
- **Optional component prefix**: `component: Description`
  - Examples: `tests:`, `api:`, `libvirt:`, `docs:`
  - Component must match the files being changed

## Body

- **Blank line after subject** (line 2 must be empty)
- **72 character line wrapping** for all body text
- **Focus on WHY, not WHAT** - explain motivation and context
- **Provide background** - don't assume reviewers know the context
- **Multiple paragraphs OK** - separate with blank lines for readability

### What to include in body

1. **What problem does this solve?** - Context for why this change exists
2. **How does it solve it?** - High-level approach (not line-by-line code)
3. **Are there limitations?** - Known issues or future work needed
4. **How was it tested?** - If applicable, evidence it works

## Metadata Tags

- **Come at the very end** of the message
- **Each on its own line**
- **Blank line before metadata section** if there's body content
- **Always end with Assisted-By then Signed-off-by**

### Required Tags

Always include:
- `Assisted-By: <Tool> (<model>)` - Credits AI assistance
- `Signed-off-by: <Name> <email>` - Primary author from git config

### Optional Tags

Only include when relevant:

**Bug references:**
- `Closes-Bug: #123` - Full fix
- `Partial-Bug: #123` - Partial fix
- `Related-Bug: #123` - Related change

**Impact flags (simple):**
- `DocImpact` - Affects documentation
- `APIImpact` - Modifies public APIs

**Impact flags (detailed):**
```
SecurityImpact:

Detailed explanation of security implications...

UpgradeImpact:

Explanation for operators: what changes, what to configure...
```

**Co-authorship:**
- `Co-Authored-By: Name <email>` - Can have multiple

**Additional sign-offs:**
- `Signed-off-by: Name <email>` - Additional signers after primary

### Tag Order (bottom to top)

1. Signed-off-by lines (primary first, then additional)
2. Assisted-By (just above all Signed-off-by lines)
3. Co-Authored-By lines (one per co-author)
4. Impact tags with details (SecurityImpact:, UpgradeImpact:)
5. Simple impact flags (DocImpact, APIImpact)
6. Bug references (Closes-Bug, Partial-Bug, Related-Bug)
7. Test Plan section (if included)

## Common Mistakes to Avoid

### Format mistakes:
- Exceeding 50 chars on subject
- Exceeding 72 chars on body lines
- Period at end of subject line
- Missing blank line after subject
- Missing blank line before metadata
- Missing required tags (Assisted-By, Signed-off-by)

### Content mistakes:
- Vague subjects: "Fix bug" → "Fix race condition in task scheduler"
- Describing WHAT instead of WHY: "Removed file" → "Remove deprecated test infrastructure that is no longer maintained"
- Assuming context: "Fix the issue" → "Fix memory leak causing gradual memory growth"
- Mismatching the diff: Subject says "Add tests" but diff removes tests
- Past tense in subject: "Fixed bug" → "Fix bug" (imperative mood)
- Wrong component: Using "api:" when changing tests/

### Process mistakes:
- Skipping format verification
- Adding metadata tags unnecessarily (in fast mode, only Assisted-By and Signed-off-by)
