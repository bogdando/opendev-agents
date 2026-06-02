# OpenStack Commit Message Examples

Auto-generated examples following OpenStack format.

## Example 1: Test cleanup

```
Remove deprecated Selenium integration tests

The Selenium-based integration test infrastructure has been
deprecated and is no longer maintained. This removes the
entire integration_tests directory and jasmine test runner.

Assisted-By: Claude Code (claude-sonnet-4-5@20250929)
Signed-off-by: Jane Doe <jane@example.com>
```

## Example 2: Bug fix with component

```
libvirt: Fix memory leak in instance cleanup

The instance cleanup code was not properly releasing memory
allocated for device metadata, causing gradual memory growth
in the compute service over time.

This ensures all device metadata is freed when instances are
deleted by adding proper cleanup calls.

Assisted-By: Claude Code (claude-sonnet-4-5@20250929)
Signed-off-by: Jane Doe <jane@example.com>
```

## Example 3: Simple refactor

```
Refactor config parsing to reduce duplication

The configuration parsing logic had significant duplication
across three modules, making it hard to maintain and prone to
inconsistencies.

This extracts the common logic into a shared utility function
while maintaining backward compatibility.

Assisted-By: Claude Code (claude-sonnet-4-5@20250929)
Signed-off-by: Jane Doe <jane@example.com>
```
