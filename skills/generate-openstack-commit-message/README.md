# OpenStack Commit Message Generator

A Claude Code skill that generates properly formatted OpenStack-style git commit messages following the [OpenStack Git Commit Message Guidelines](https://wiki.openstack.org/wiki/GitCommitMessages).

## Features

✅ **Automatic formatting**:
- Subject line ≤ 50 characters, no period
- Body wrapped at 72 characters
- Proper blank line separation
- Automated format validation

✅ **Two modes**:
- **Fast mode (default)**: Auto-generate without questions
- **Interactive mode**: Full control over bugs, impacts, co-authors, test plans

✅ **Interactive metadata collection**:
- Bug references (Closes-Bug, Partial-Bug, Related-Bug)
- Impact tags (DocImpact, APIImpact, SecurityImpact, UpgradeImpact)
- Co-authors and additional sign-offs
- Optional test plan section

✅ **Automatic attribution**:
- `Assisted-By: <Tool> (<model>)` - AI assistance credit
- `Signed-off-by:` from git config
- Support for multiple co-authors and sign-offs

✅ **Smart scoping**:
- Requires git repository
- Optional OpenStack project detection
- Configurable strictness

✅ **Optimized for efficiency** (v2.0):
- Progressive disclosure (60% token reduction)
- Pre-approved git commands (no permission prompts)
- Automated validation scripts
- Self-verifying (checks format before presentation)
- Supporting files loaded on-demand

## Installation

```bash
# Package the skill (if not already packaged)
claude-skill package /path/to/openstack-commit-message

# Install the skill
claude-skill install openstack-commit-message.skill
```

## Usage

### Automatic Invocation

The skill triggers automatically when you:
- Mention "commit message" or "write a commit message"
- Reference git changes or diffs
- Say "commit this" or "create a commit"

Example:
```
User: "Write me a commit message for my staged changes"
Claude: *uses openstack-commit-message skill automatically*
```

### Explicit Invocation

You can also explicitly request the skill:
```
User: "Use the openstack-commit-message skill to generate a commit message"
```

### Typical Workflow

1. Make your changes and stage them:
   ```bash
   git add file1.py file2.py
   ```

2. Ask Claude to generate a commit message:
   ```
   "Write a commit message for my staged changes"
   ```

3. Claude will:
   - Check git repository status
   - Analyze your diff
   - Ask about component prefix (optional)
   - Ask about bugs, impacts, co-authors, etc.
   - Generate a properly formatted message

4. Copy the generated message and commit:
   ```bash
   git commit -m "$(cat << 'EOF'
   <paste commit message here>
   EOF
   )"
   ```

## Configuration

### Scoping Modes

**Current mode: FLEXIBLE** (works in any git repo)

#### FLEXIBLE Mode (Default)
- ✅ Works in any git repository
- ⚠️ Shows gentle warning if not an OpenStack project
- 👍 Best for: Mixed environments, learning, non-OpenStack projects using OpenStack style

#### STRICT Mode (OpenStack projects only)
To enable strict mode, edit `SKILL.md` and change the description to include:
> "Only use this skill in OpenStack projects with .gitreview or .zuul.yaml files"

Then add to Step 0:
> "If no OpenStack markers found, exit with error message"

- ✅ Only works in directories with `.gitreview`, `.zuul.yaml`, or `.zuul.d/`
- 🚫 Refuses to run in non-OpenStack projects
- 👍 Best for: Dedicated OpenStack developers

### OpenStack Project Detection

The skill looks for these markers:
- `.gitreview` - Gerrit review configuration
- `.zuul.yaml` - OpenStack CI configuration
- `.zuul.d/` - OpenStack CI configuration directory
- `tox.ini` - May contain OpenStack-specific test jobs

## Examples

### Example 1: Bug Fix with Component

**User**: "Write a commit message for my staged changes. Fixed a memory leak in nova, bug #1847392, component is 'nova'"

**Generated**:
```
nova: Fix memory leak in instance cleanup

The instance cleanup code was not properly releasing memory
allocated for device metadata, causing gradual memory growth
in the compute service over time. This was particularly
noticeable in environments with high instance churn.

This change ensures all device metadata is freed when
instances are deleted by adding proper cleanup calls in the
_cleanup_instance_devices method.

Closes-Bug: #1847392
Assisted-By: Claude Code (claude-sonnet-4-5@20250929)
Signed-off-by: Jane Doe <jane@example.com>
```

### Example 2: Feature with Multiple Impacts

**User**: "Generate commit message. Added API validation for project names. Bug #2019456. This affects API and docs."

**Generated**:
```
Add validation for project names in API

Previously the API accepted any string as a project name,
leading to database errors when invalid characters were used.
This caused confusing error messages for users.

This change adds validation to ensure project names contain
only alphanumeric characters, hyphens, and underscores, with
a maximum length of 64 characters. Clear error messages are
returned when validation fails.

Closes-Bug: #2019456
APIImpact
DocImpact
Assisted-By: Claude Code (claude-sonnet-4-5@20250929)
Signed-off-by: Jane Doe <jane@example.com>
```

### Example 3: Security Fix with UpgradeImpact

**User**: "Commit message for security fix in keystone token validation. Bug #2087123. This has security and upgrade impacts."

**Generated**:
```
keystone: Fix expired token acceptance vulnerability

The token validation code was accepting expired tokens in
certain edge cases, potentially allowing unauthorized access
with expired credentials.

This change ensures all tokens are properly validated for
expiration regardless of the code path taken.

Closes-Bug: #2087123
SecurityImpact:

Previously expired tokens could be accepted in certain edge
cases, potentially allowing unauthorized access. This fix
ensures strict validation in all code paths.

UpgradeImpact:

The stricter token validation will reject previously accepted
expired tokens. If you have services relying on the previous
(incorrect) behavior during token expiration edge cases, they
may experience authentication failures during upgrade. To
minimize impact, ensure all services are using fresh tokens
before upgrading.

Assisted-By: Claude Code (claude-sonnet-4-5@20250929)
Signed-off-by: Jane Doe <jane@example.com>
```

## OpenStack Commit Message Format

### Structure

```
[component: ]Subject line (≤50 chars, no period)

Detailed body explaining WHY the change was needed and WHAT
problem it solves. Lines wrapped at 72 characters. Can have
multiple paragraphs.

Additional context about the implementation approach,
limitations, or future work.

Test Plan:
- Test case 1 (optional)
- Test case 2

Closes-Bug: #1234567
Related-Bug: #7654321
APIImpact
DocImpact
SecurityImpact:

Detailed security impact explanation if needed...

UpgradeImpact:

Detailed upgrade impact explanation...

Co-Authored-By: Alice Smith <alice@example.com>
Co-Authored-By: Bob Johnson <bob@example.com>
Assisted-By: Claude Code (claude-sonnet-4-5@20250929)
Signed-off-by: Primary Author <author@example.com>
Signed-off-by: Additional Signer <signer@example.com>
```

### Metadata Tags

**Bug References**:
- `Closes-Bug: #123` - Fully fixes the bug
- `Partial-Bug: #123` - Partially fixes the bug
- `Related-Bug: #123` - Related but doesn't fix

**Impact Flags** (simple):
- `DocImpact` - Documentation needs updating
- `APIImpact` - Public API changes

**Impact Tags** (detailed):
- `SecurityImpact:` + explanation
- `UpgradeImpact:` + explanation

**Attribution**:
- `Co-Authored-By: Name <email>` - Multiple allowed
- `Assisted-By: Tool (model)` - AI assistance
- `Signed-off-by: Name <email>` - Multiple allowed, primary first

## Customization

### Change Git Config

The skill uses your git configuration for Signed-off-by:
```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### Adjust Triggering

Edit the `description` field in `SKILL.md` to control when the skill triggers:

- **More selective**: Add specific keywords or contexts
- **More broad**: Add more trigger phrases
- **OpenStack only**: Add "Only in OpenStack projects with .gitreview"

### Disable OpenStack Project Check

In `SKILL.md`, remove or comment out Step 0's OpenStack project detection section.

## Troubleshooting

### "This directory is not a git repository"

Make sure you're in a git repository:
```bash
git rev-parse --git-dir
```

### "Git config not set"

Configure your git identity:
```bash
git config user.name "Your Name"
git config user.email "your.email@example.com"
```

### Skill doesn't trigger automatically

Try being more explicit:
- "Write an OpenStack commit message"
- "Use the openstack-commit-message skill"

Or check that the skill is installed:
```bash
claude-skill list
```

## Contributing

To improve this skill:

1. Edit `SKILL.md` with your changes
2. Test with various commit scenarios
3. Update examples if needed
4. Repackage: `claude-skill package openstack-commit-message`

## License

This skill follows the same license as Claude Code.

## References

- [OpenStack Git Commit Messages Guidelines](https://wiki.openstack.org/wiki/GitCommitMessages)
- [Example: Swift Parallel Task Container Iteration](https://review.opendev.org/c/openstack/swift/+/918366/62//COMMIT_MSG)
