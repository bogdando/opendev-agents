---
name: generate-openstack-commit-message
description: Fast auto-generation of OpenStack-style git commit messages from code changes. Analyzes diffs and creates properly formatted messages.
when_to_use: Use when the user mentions commits, commit messages, git changes, staging files, wants to commit code, asks about message format, shows git diffs, or says "write a commit message", "create commit", "commit this".
argument-hint: [interactive]
allowed-tools:
  - Bash(git *)
  - Bash(python ${CLAUDE_SKILL_DIR}/tools/*)
  - Read
  - Grep
---

# OpenStack Commit Message Generator

Auto-generates OpenStack-style commit messages from git changes.

## Security

This skill executes read-only git commands:
- `git rev-parse`, `git config`, `git diff`, `git log`, `git status`
- No destructive operations without user confirmation
- Validation scripts in `tools/` directory for review

## Modes

**Fast mode (default)**: Auto-generate without questions
**Interactive mode**: Ask questions one by one about bugs, impacts, co-authors

Invoke: `/generate-openstack-commit-message` or `/generate-openstack-commit-message interactive`

## Workflow

### Step 1: Validate prerequisites and gather info

Check git repository and user config:
```bash
git rev-parse --git-dir
git config user.name
git config user.email
```

If any fails:
- Not a git repo: "Error: Not a git repository. Run 'git init' or navigate to a git repo."
- No user config: "Error: Git user not configured. Run:\n  git config --global user.name 'Your Name'\n  git config --global user.email 'you@example.com'"

### Step 2: Auto-detect and analyze changes

Check staged then unstaged changes:
```bash
git diff --staged --stat || git diff --stat
```

If no changes: "Error: No changes to commit. Make changes and try again."

Analyze:
- Files changed (detect component from paths: tests/ → "tests:", api/ → "api:")
- Type of change (bugfix, feature, cleanup, refactor, etc.)
- Auto-detect component prefix if obvious

### Step 3: Generate message

**Mode detection**: Check if "interactive" in args

**Fast mode**:
- Auto-generate subject (≤50 chars, imperative mood, no period)
- Write body explaining WHY (72-char wrap, 2-3 paragraphs)
- Add only: Assisted-By and Signed-off-by tags

**Interactive mode**:
- See [interactive_mode.md](interactive_mode.md) for detailed workflow
- Ask 9 questions ONE AT A TIME
- Wait for response between questions
- Questions: component, bugs, DocImpact, APIImpact, SecurityImpact, UpgradeImpact, co-authors, sign-offs, test plan

### Step 4: Self-verify format and content

Before presenting, verify ALL of these:

**Format checks**:
- ✅ Subject ≤ 50 chars
- ✅ No period at end of subject
- ✅ Blank line after subject (line 2 empty)
- ✅ Body lines ≤ 72 chars
- ✅ Blank line before metadata
- ✅ Contains Assisted-By and Signed-off-by

**Content checks**:
- ✅ Subject accurately describes the change
- ✅ Explains WHY, not just WHAT
- ✅ Matches the actual diff
- ✅ Problem statement clear
- ✅ Solution described
- ✅ No assumptions about reviewer knowledge
- ✅ Imperative mood in subject
- ✅ Component prefix matches files (if used)

If ANY check fails, fix and re-verify. Only present validated messages.

### Step 5: Present message

Show message in code block.

Say: "Validated format and content. Adjust anything?"

## Additional Resources

- **Format specifications**: See [formatting_rules.md](formatting_rules.md)
- **Examples**: See [examples.md](examples.md)
- **Interactive workflow**: See [interactive_mode.md](interactive_mode.md)

## Key Points

- Fast by default, interactive on request
- Only Assisted-By and Signed-off-by in fast mode
- All output self-verified before presentation
- Explains WHY, not just WHAT
- 50-char subject, 72-char body wrapping
- Component prefix optional, must match files changed

Remember: You only generate the message. The user will copy it and commit manually.
