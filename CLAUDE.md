# OpenStack Development Guidelines for Claude Code

# OpenStack Python Comprehensive Style Guide for AI Code Generation

> **Comprehensive Guide**: Detailed explanations and examples for AI tools generating OpenStack-compliant Python code.
> **For quick reference**: See the [OpenStack Python Quick Rules for AI](quick-version)
> **For working templates**: See [docs/templates/](templates/) for ready-to-use code patterns
> **For validation workflows**: See [docs/checklists/](checklists/) for pre-submit and review procedures

## Overview for AI Assistants

This guide provides specific instructions for AI coding assistants (Claude Code, aider, etc.)
to generate Python code that meets OpenStack contribution standards. Follow these rules precisely
to ensure code passes OpenStack's strict linting and review processes.

## Project Structure

OpenStack projects typically follow standard Python project layout with:

- Main code in `<project_name>/` directory
- Tests in `<project_name>/tests/` directory
- Configuration files: `tox.ini`, `setup.cfg`, `pyproject.toml` etc.
- Many (but not all) projects use pre-commit. Where present, a `.pre-commit-config.yaml` file will be present. In this case, `pre-commit run` can typically be used to run linters, rather than using globally installed versions of e.g. `ruff`, `flake8`, `mypy` etc.
- `pre-commit` is installed globally on this system, so you don't need to activate a virtualenv to run it.

## Dependencies

OpenStack projects use `pbr` instead of `setuptools` for packaging. `pbr` expects dependencies to be listed in `requirements.txt`, `test-requirements.txt` and `doc/requirements.txt` files. This may change in the future as pbr evolves.

## Modernization

In addition to the addition of ruff and typing, we may wish to make other changes to projects to bring them up to modern standards. Below are guidelines for making these changes.

### Migration to `pyproject.toml`

As noted above, OpenStack projects use `pbr` for packaging. `pbr` supports the same `pyproject.toml` format as `setuptools`. All projects should have the following `pyproject.toml` at a minimum:

```toml
[build-system]
requires = ["pbr>=6.0.0", "setuptools>=64.0.0"]
build-backend = "pbr.build"
```

To migrate the rest of the commands, note the following mappings:

* Move `[metadata]` section in `setup.cfg` to `[project]` section
* Move `[entry_points]` section in `setup.cfg` to `[project.entry-points]` section
* Move `[extras]` section in `setup.cfg` to `[project.optional-dependencies]` section

Also note that `dependencies` and `version` must be treated as `dynamic` since these are managed by `pbr`.

The `setup.cfg` file must currently be retained as a stub file containing only the following:

```
[metadata]
name = <project-name>
```

The `setup.py` must be retained as-is.

**Never use `setuptools-scm` or similar tools**. pbr will handle versioning for us.

## 1. Critical Code Generation Rules

### ALWAYS Include Apache License Header

Every Python file MUST start with:

```python
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
```

### Line Length & Formatting

- **Maximum 79 characters per line** (strictly enforced)
- Use 4 spaces for indentation (never tabs)
- UNIX line endings (`\n`) only
- Break long lines using parentheses, not backslashes:

```python
# Correct:
result = some_function(
    argument_one,
    argument_two,
    argument_three
)

# Wrong:
result = some_function(argument_one, argument_two, \
                      argument_three)
```

## Style

### Overview

OpenStack projects have historically used hacking, a flake8 plugin, to enforce style across projects. Lately, a number of projects have migrated to ruff. This is typically run via pre-commit. If ruff configuration is present in `pyproject.toml` then ruff should be run after all changes. `ruff` can typically be run via pre-commit (`pre-commit run -a`).

### Adding ruff to a new project

If adding ruff to a new project, the following configuration should be used in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 79

[tool.ruff.format]
quote-style = "preserve"
docstring-code-format = true

[tool.ruff.lint]
select = ["E4", "E5", "E7", "E9", "F", "G", "LOG", "S", "UP"]
```

You should also enable the ruff pre-commit hooks by adding them to `.pre-commit-config.yaml`. This will look like so:

```
repos:
  # ... existing configuration
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.10
    hooks:
      - id: ruff-check
        args: ['--fix', '--unsafe-fixes']
      - id: ruff-format
  # ... existing configuration
```

These hooks should be placed before the hacking hook. The pyupgrade and bandit hooks should be removed if present.
Once the hook has been added, you should ensure we are using the latest version of the ruff hook and all other hooks by running `pre-commit autoupdate`.

Finally, you should disable all flake8 rules except the hacking rules. Do this in `tox.ini`:

```ini
[flake8]
# We only enable the hacking (H) checks
select = H
```

### Imports

- OpenStack projects group their imports into stdlib, third-party, and first-party groups.
- OpenStack projects try to avoid importing objects and instead import modules.

  Do:

    from foo import bar

  Don't do:

    from foo.bar import Baz

  The only command exceptions to this are:

  - `_` (from `<package>.i18n` or `<package>._i18n`
  - Imports from `typing`, unless the project is already using the `import typing as ty` pattern.

- OpenStack projects sort their imports by Python module path, treating `import foo.bar` and `from foo import bar` as identical.

## 2. Import Organization (Critical for AI)

Always organize imports in exactly this order with blank lines between groups:

```python
# Standard library (alphabetical)
import json
import os
import sys

# Third-party libraries (alphabetical)
import oslo_config
import requests

# OpenStack libraries (alphabetical)
from oslo_config import cfg
from oslo_log import log

# Local project imports (alphabetical)
from nova import exception
from nova import utils
```

**AI Note**: Within each group, separate `import X` from `from X import Y` statements into sub-groups.

## 9. Naming Conventions

### Variable and Function Names

```python
# Correct:
user_count = 10
def get_active_users():
    pass

# Wrong:
userCount = 10  # camelCase not allowed
def GetActiveUsers():  # PascalCase for functions not allowed
```

### Class Names

```python
# Correct:
class DatabaseManager:
    pass

class HTTPSConnection:
    pass

# Exception classes:
class InvalidConfigurationError(Exception):
    pass
```

### Constants

```python
# Module-level constants:
DEFAULT_TIMEOUT = 30
MAX_RETRY_ATTEMPTS = 3
API_VERSION = '2.1'
```

## 3. Function & Method Definitions

### Docstring Format (H404/H405 Compliance)

```python
def fetch_resource(resource_id, timeout=30):
    """Fetch a resource from the database.

    :param resource_id: Unique identifier for the resource
    :param timeout: Request timeout in seconds
    :returns: Resource object or None if not found
    :raises: ResourceNotFound if resource doesn't exist
    """
```

### Argument Handling

```python
# Correct: Use None for mutable defaults
def process_items(items=None):
    items = items or []
    # process items

# Wrong: Mutable default arguments
def process_items(items=[]):  # NEVER do this
    # process items
```

## 6. Logging & String Formatting

### Logging with Delayed Interpolation

```python
# Correct (H702/H904 compliant):
LOG.info('Processing %d items', len(items))
LOG.error(_('Failed to connect to %s'), server)  # Translatable

# Wrong:
LOG.info(f'Processing {len(items)} items')  # Immediate interpolation
LOG.info('Processing {} items'.format(len(items)))
```

### String Formatting Preferences

```python
# Preferred for regular strings:
message = f'User {username} has {count} items'

# For logging (delayed interpolation):
LOG.debug('User %s has %d items', username, count)

# Multiline strings:
query = ("SELECT * FROM users "
         "WHERE active = true "
         "AND created_at > %s")
```

## 7. Data Structure Formatting

### Dictionary Formatting

```python
# One key-value pair per line for readability:
config = {
    'database_url': 'sqlite:///app.db',
    'debug': True,
    'timeout': 30,
}

# Trailing comma required for single-item tuples:
single_item = ('value',)  # Note the comma
```

### List Comprehensions (Keep Simple)

```python
# Acceptable:
results = [item.id for item in items if item.active]

# Too complex - use regular loop instead:
# results = [process(item) for sublist in nested_list
#           for item in sublist if complex_condition(item)]
```

## 4. Exception Handling (Strictly Enforced)

### Never Use Bare Except (H201)

```python
# Correct:
try:
    risky_operation()
except (ValueError, TypeError) as e:
    LOG.error('Operation failed: %s', e)

# Wrong:
try:
    risky_operation()
except:  # H201 violation - will fail CI
    LOG.error('Something went wrong')
```

### Specific Exception Patterns

```python
# Handle specific exceptions
try:
    data = json.loads(response)
except json.JSONDecodeError as e:
    raise InvalidDataError('Failed to parse JSON: %s' % e)

# For re-raising, catching BaseException is acceptable
try:
    critical_operation()
except BaseException:
    cleanup_resources()
    raise
```

## 8. Exception Design Patterns

### Custom Exception Classes

OpenStack projects use structured exception classes with message formatting:

```python
class ModuleError(exception.BaseException):
    """Base exception for MODULE_NAME errors."""
    msg_fmt = "An error occurred in MODULE_NAME: %(reason)s"

class ResourceNotFoundError(ModuleError):
    """Raised when a resource cannot be found."""
    msg_fmt = "Resource %(resource_id)s not found"

class InvalidConfigurationError(ModuleError):
    """Raised when configuration is invalid."""
    msg_fmt = "Invalid configuration: %(config_key)s = %(config_value)s"
```

**Key Pattern Rules:**

- Inherit from appropriate OpenStack exception base class
- Use `msg_fmt` for consistent message formatting
- Support parameter substitution with `%(param)s` syntax
- Create specific exception classes for different error types

### Exception Usage Patterns

```python
def get_resource(self, resource_id):
    if not resource_id:
        raise ValueError("resource_id cannot be empty")

    try:
        resource = self._fetch_from_database(resource_id)
        if not resource:
            raise ResourceNotFoundError(resource_id=resource_id)
        return resource
    except (ValueError, TypeError) as e:
        LOG.error("Invalid resource_id format: %s", e)
        raise InvalidInputError(reason=str(e))
    except Exception as e:
        LOG.exception("Unexpected error retrieving resource %s", resource_id)
        raise ModuleError(reason=str(e))
```

## 9. OpenStack-Specific Patterns

### Configuration Options

```python
from oslo_config import cfg

CONF = cfg.CONF

# Define options clearly:
api_opts = [
    cfg.IntOpt('timeout',
               default=30,
               help='API request timeout in seconds'),
    cfg.StrOpt('endpoint',
               help='Service endpoint URL'),
]

CONF.register_opts(api_opts, group='api')
```

### Context Managers for Resources

```python
# Always use context managers:
with open('/etc/nova/nova.conf') as config_file:
    config_data = config_file.read()

# For database connections:
with session.begin():
    instance = session.query(Instance).filter_by(uuid=uuid).one()
    instance.update(updates)
```

### Database Session Patterns

OpenStack uses oslo.db with proper transaction management:

```python
from oslo_db import exception as db_exception

def create_instance(self, instance_data):
    """Create a new database instance with proper error handling."""
    try:
        with self.session.begin():
            instance = Instance(**instance_data)
            self.session.add(instance)
            self.session.flush()  # Get ID without committing
            return instance
    except db_exception.DBDuplicateEntry:
        LOG.error("Instance %s already exists", instance_data['name'])
        raise InstanceExistsError(name=instance_data['name'])
    except db_exception.DBError as e:
        LOG.exception("Database error creating instance")
        raise DatabaseError(reason=str(e))

def update_instance(self, instance_id, updates):
    """Update instance with atomic transaction."""
    try:
        with self.session.begin():
            instance = self.session.query(Instance).filter_by(
                id=instance_id).with_for_update().one()
            if not instance:
                raise InstanceNotFoundError(instance_id=instance_id)
            instance.update(updates)
            return instance
    except db_exception.DBError as e:
        LOG.exception("Failed to update instance %s", instance_id)
        raise DatabaseError(reason=str(e))
```

### Database Query Patterns

```python
# Efficient querying with proper error handling
def get_active_instances(self, limit=None):
    """Get active instances with optional limit."""
    try:
        query = self.session.query(Instance).filter_by(
            deleted=False, active=True)
        if limit:
            query = query.limit(limit)
        return query.all()
    except db_exception.DBError as e:
        LOG.exception("Database error fetching active instances")
        raise DatabaseError(reason=str(e))

# Pagination for large result sets
def list_instances(self, marker=None, limit=None):
    """List instances with pagination support."""
    try:
        query = self.session.query(Instance).filter_by(deleted=False)
        if marker:
            query = query.filter(Instance.id > marker)
        if limit:
            query = query.limit(limit + 1)  # +1 to check for more
        instances = query.all()
        has_more = len(instances) > limit if limit else False
        if has_more:
            instances = instances[:-1]  # Remove the extra
        return instances, has_more
    except db_exception.DBError as e:
        LOG.exception("Error listing instances")
        raise DatabaseError(reason=str(e))
```

### API Service Method Patterns

OpenStack API controllers require specific error handling and response patterns:

```python
import webob.exc
from oslo_log import log

LOG = log.getLogger(__name__)

def api_method(self, request, resource_id):
    """Standard API method with proper error handling."""
    context = request.environ['context']

    try:
        resource = self.manager.get_resource(context, resource_id)
        return {'resource': resource}
    except ResourceNotFoundError as e:
        raise webob.exc.HTTPNotFound(
            explanation=e.msg_fmt % e.kwargs)
    except InvalidParameterError as e:
        raise webob.exc.HTTPBadRequest(
            explanation=e.msg_fmt % e.kwargs)
    except Exception as e:
        LOG.exception('Unexpected error in api_method')
        raise webob.exc.HTTPInternalServerError()

def create_resource(self, request, resource_data):
    """Create resource with validation and proper error handling."""
    context = request.environ['context']

    try:
        # Validate input
        if not resource_data.get('name'):
            raise InvalidParameterError(param='name', value='missing')

        resource = self.manager.create_resource(context, resource_data)
        return {'resource': resource}, 201  # Created status
    except ResourceAlreadyExistsError as e:
        raise webob.exc.HTTPConflict(
            explanation=e.msg_fmt % e.kwargs)
    except Exception as e:
        LOG.exception('Failed to create resource')
        raise webob.exc.HTTPInternalServerError()
```

**Key API Pattern Rules:**

- Extract context from `request.environ['context']`
- Catch specific exceptions and return appropriate HTTP status codes
- Use `webob.exc` for HTTP exceptions with proper explanations
- Log unexpected errors with `LOG.exception()`
- Return 201 status for resource creation
- Always include error explanations in exception messages

## Typing

OpenStack projects are adding slowly adding type hints to projects. Where type hints are already present in a project, hints should be added to any new code.

We use mypy as the type checker. **Always run mypy via tox** using `tox -e mypy`. Never run mypy directly or install it in a virtualenv manually. If type stub packages are missing (e.g., `types-requests`, `types-docutils`), add them to the `deps` section of the `[testenv:mypy]` environment in `tox.ini`.

For some projects that haven't migrated, mypy may be run via pre-commit (`pre-commit run -a mypy`). Where the latter is still used, you should offer to migrate things to tox as a secondary task.

All OpenStack projects require at least Python 3.10: therefore prefer native subscriptable types and other features added in that version. For example: prefer `list` over `typing.List`, `set` over `typing.Set`, and the pipe operator (`|`) over `typing.Union`

While OpenStack doesn't generally allow more than one import per line, the following libraries are exceptions and should always be grouped: `collections.abc`, `types`, `typing`, `typing-extensions`.

### Handling untyped libraries

The only mypy error code that may be disabled globally in `pyproject.toml` is `import-untyped`. All other errors must be handled with line-specific `# type: ignore[error-code]` comments.

When a dependency has untyped functions (triggering `no-untyped-call` errors):

1. First, check if the library is installed in the mypy tox environment: `.tox/mypy/bin/pip show <library>`
2. Check if a type stub package exists: `.tox/mypy/bin/pip index versions types-<library>`
3. If a type stub exists, add it to the `deps` section of `[testenv:mypy]` in `tox.ini`
4. If no type stub exists, add `# type: ignore[no-untyped-call]` to the specific lines that call untyped functions

This approach keeps type checking strict while only ignoring errors for specific calls that cannot be typed.

### Type hint best practices

When adding type hints:

1. **Avoid `typing.Any`** - Use specific types wherever possible. `Any` defeats the purpose of type checking. Only use it as a last resort when the type is truly dynamic or unknowable.

2. **Fix errors properly** - Don't add blanket `disable_error_code` entries to `pyproject.toml` as a permanent solution. These are acceptable as intermediate steps but should be resolved. Instead:

   - For `import-not-found`: This normally indicates a missing type stubs package or optional dependency. Add the missing package to `tox.ini` `deps` or use `# type: ignore[import-not-found]` if absolutely necessary.
   - For `attr-defined`: Check if you're accessing the correct attribute; if the code is correct, use a line-specific ignore
   - For `arg-type`/`assignment`: Fix the type mismatch, or use `cast()` if the types are actually compatible at runtime

   The only exception for this is `import-untyped` since we do have some dependencies that are untyped.

3. **Preserve implementation behavior** - Never change the implementation or behavior of code just to satisfy mypy. Exhaust all typing solutions first (proper annotations, `cast()`, `TYPE_CHECKING` imports, Protocol classes, etc.)

4. **Use `TYPE_CHECKING` for circular imports** - When type hints create circular imports, use:
   ```python
   from typing import TYPE_CHECKING
   if TYPE_CHECKING:
       from module import SomeClass
   ```

5. **Use `cast()` sparingly** - When you know a type is correct but mypy can't infer it, use `typing.cast()` rather than `# type: ignore`. This documents intent.

### Adding type hints to a new project

Most projects should use ruff before adding typing. If the project doesn't have ruff, you should ask whether this should be integrated first or not. If it should, follow the steps in `Add ruff to a new project`.

In addition, before you begin you should ensure that the relevant scaffolding is in place for the project. This requires changes to a number of files. First, to `pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.10"
show_column_numbers = true
show_error_context = true
strict = true
disable_error_code = ["import-untyped"]
exclude = '(?x)(doc | releasenotes)'

[[tool.mypy.overrides]]
module = ["{module}.tests.*"]
disallow_untyped_calls = false
disallow_untyped_defs = false
disallow_subclassing_any = false
```

(replace `{module}` with the relevant module).

You should also add the `Typing :: Typed` classifier in `[project] classifiers` in this file. Next, `tox.ini`:

```ini
[testenv:pep8]
description =
  Run style checks.
deps =
  pre-commit
  {[testenv:mypy]deps}
commands =
  pre-commit run -a
  {[testenv:mypy]commands}

[testenv:mypy]
description =
  Run type checks.
deps =
  {[testenv]deps}
  mypy
  types-docutils
commands =
  mypy --cache-dir="{envdir}/mypy_cache" -p {module} {posargs}
```

(once again replace `{module}` with the relevant module)

Note: Use the `-p {module}` (package) syntax rather than a directory path, as editable installs can cause issues with directory-based invocation.

You should also create a `{module}/py.typed` file.

## Testing

OpenStack projects use `tox` with `stestr` for testing, not `pytest`.

### Running Tests

- To run all tests: `tox -e py312`
- To run specific tests by file name: `tox -e py312 -- -n <test_file_path>`
    - Example: `tox -e py312 -- -n openstack_releases/tests/test_requirements.py`
- To run specific tests by module name: `tox -e py312 -- <module_path>`
    - Example: `tox -e py312 -- openstack_releases.tests.test_requirements`

In the rare case that a test relies on an unreleased feature in another library, you can modify the virtualenv and install the local copy first. You can do this with the following steps:

- Create the tox virtualenv but don't run tests: `tox -e py312 --notest`
- Activate the tox virtualenv: `source .tox/py312/bin/activate`
- Install the WIP version of the library from the local repo clone: `pip install -e ../<name-of-other-library>`
- Deactivate the tox virtualenv: `deactivate`
- Run tests as usual: `tox -e py313`

Before doing this, you should ask me for the path to the local copy of the module.

### Writing Tests

All OpenStack projects use the standard Python `unittest` module for writing tests, with the following `unittest`-compatible libraries providing additional functionality:

- `fixtures`: which are similar to pytest fixtures
- `testtools`: which extends `unittest` to allow use of `fixtures`, among other things
- `testscenarios`: to build matrices of tests, similar to parametrized test functions in pytest
- `ddt`: a simpler alternatives to `testscenarios`
- `oslotest`: a collection of utilities that are used across most OpenStack services

Before using such a library when writing tests, you should ensure the given library is already in use in the project. We should avoid bringing in new dependencies unless necessary.

### Test Environment

- Use Python 3.12 environment (`py312`) by default. This will change in the future as new version of Python are released and supported by OpenStack.
- All OpenStack projects follow this pattern consistently
- Tests are executed via `stestr` runner through `tox`

## 5. Testing Code Generation

### Test Structure with oslotest

OpenStack projects use oslotest for consistent test patterns:

```python
from oslotest import base
from unittest import mock

class TestResourceManager(base.BaseTestCase):
    """Test cases for ResourceManager class."""

    def setUp(self):
        """Set up test fixtures."""
        super(TestResourceManager, self).setUp()
        self.mock_session = mock.MagicMock()
        self.manager = ResourceManager(session=self.mock_session)

    def test_method_success(self):
        """Test successful operation."""
        # Setup
        expected_result = mock.MagicMock()
        self.mock_session.query.return_value.filter_by.return_value.first\
            .return_value = expected_result

        # Execute
        result = self.manager.get_resource('test-id')

        # Verify
        self.assertEqual(expected_result, result)
        self.mock_session.query.assert_called_once()
```

### Mock Usage (H210 - Recommended)

```python
# Always use autospec=True (recommended practice)
@mock.patch('nova.utils.execute', autospec=True)

# Exception: When editing existing code that doesn't follow this pattern
# maintain consistency with existing code rather than forcing changes unless:
# 1. The existing mock pattern is causing test failures
# 2. You're adding new tests or substantially refactoring existing ones
def test_command_execution(self, mock_execute):
    mock_execute.return_value = ('output', '')
    # test code

# Mock object methods with autospec
with mock.patch.object(self.manager, '_save_to_database', autospec=True) as mock_save:
    mock_save.return_value = expected_resource
    result = self.manager.create_resource('test')
    mock_save.assert_called_once()

# Wrong - will fail H210 check:
@mock.patch('nova.utils.execute')  # Missing autospec=True
```

### Advanced Assertion Patterns

```python
# Correct assertions (H203, H214, H212 compliant):
self.assertIsNone(result)                    # Not assertEqual(None, result)
self.assertIn('key', dictionary)             # Not assertTrue('key' in dictionary)
self.assertEqual(expected, actual)            # Order matters
self.assertIsInstance(obj, MyClass)            # Not assertEqual(type(obj), MyClass)
self.assertRaises(SpecificException, func)     # Not generic Exception

# Exception testing with context manager
with self.assertRaises(ResourceNotFoundError):
    self.manager.get_resource('nonexistent')

# Multiple assertions in logical groups
self.assertEqual(2, len(results))
self.assertIn('item1', [r.id for r in results])
self.assertIn('item2', [r.id for r in results])
```

### Database Testing Patterns

```python
def test_database_transaction_rollback(self):
    """Test transaction rollback on error."""
    with mock.patch.object(self.manager.session, 'begin') as mock_begin:
        mock_begin.side_effect = db_exception.DBError("Connection failed")

        self.assertRaises(DatabaseError, self.manager.create_resource,
                         {'name': 'test'})

        # Verify transaction was attempted
        mock_begin.assert_called_once()

def test_pagination_logic(self):
    """Test pagination edge cases."""
    # Test limit boundary
    instances, has_more = self.manager.list_instances(limit=10)
    self.assertLessEqual(len(instances), 10)

    # Test marker functionality
    with mock.patch.object(self.manager, 'session') as mock_session:
        mock_session.query.return_value.filter_by.return_value.filter\
            .return_value.limit.return_value.all.return_value = []

        self.manager.list_instances(marker='last-id')
        mock_session.query.return_value.filter_by.return_value.filter\
            .assert_called_with(Instance.id > 'last-id')
```

### Import unittest.mock (H216)

```python
# Correct:
from unittest import mock

# Wrong:
from mock import patch  # H216 violation
```

## 4. Context-Aware Best Practices

### When Editing Existing Code

When modifying existing OpenStack code files, follow these guidelines:

#### Maintain Consistency Over Perfection

- **Preserve existing patterns** even if they don't follow current recommendations
- **Don't force refactors** just to align with best practices unless there's a compelling reason
- **Match local conventions** used throughout the specific file or module

#### Exceptions to Recommendations

You may deviate from recommended practices when:

1. **Consistency would be broken** - Existing code uses a different pattern consistently
2. **Risk of introducing bugs** - Changing patterns could destabilize working code
3. **Limited scope** - You're only fixing a specific bug, not refactoring
4. **Downstream dependencies** - Other code depends on current implementation

#### When to Apply Recommendations

For new code or substantial refactors:

1. **New files** - Follow all recommended practices
2. **New methods/classes** - Use recommended patterns even in existing files
3. **Test additions** - Apply best practices to new test code
4. **Security fixes** - Update to current security practices
5. **Performance improvements** - Modernize patterns for better performance

### Error Prevention Checklist

Before generating code, verify:

- [ ] Line length ≤ 79 characters
- [ ] No bare `except:` statements
- [ ] `autospec=True` in all `@mock.patch` decorators (for new code)
- [ ] Proper logging interpolation (use `%s`, not f-strings)
- [ ] Specific exception handling
- [ ] Apache license header present
- [ ] Imports properly organized
- [ ] "Generated-By:" or "Assisted-By:" label prepared for commit message
- [ ] AI tool configured for open source compatibility
- [ ] **DCO sign-off ready** (git commit -s)
- [ ] Commit subject line ≤ 50 characters, imperative mood
- [ ] Commit body explains WHY and WHAT, wrapped at 72 characters

## 12. Common Anti-Patterns to Avoid

For complete examples of anti-patterns to avoid, see
[docs/examples/bad/anti_patterns.py](examples/bad/anti_patterns.py) which demonstrates
all common violations with explanations.

### Critical Violations (Will Fail CI)

```python
# H201 - Bare except (CRITICAL)
try:
    operation()
except:  # NEVER use bare except
    pass
# Fix: except (ValueError, TypeError) as e:

# H210 - Missing autospec in mock (CRITICAL)
@mock.patch('module.function')  # Missing autospec=True
def test_method(self, mock_func):
    pass
# Fix: @mock.patch('module.function', autospec=True)

# H216 - Wrong mock import (CRITICAL)
from mock import patch  # Third-party mock library
# Fix: from unittest import mock

# H304 - Relative imports
from .utils import helper  # Don't use relative imports
# Fix: from package.utils import helper

# H702 - String formatting in logging (CRITICAL)
LOG.info(f"Value: {val}")  # Immediate interpolation
LOG.info("Value: {}".format(val))  # Also wrong
# Fix: LOG.info("Value: %s", val)  # Delayed interpolation
```

### Code Quality Violations

```python
# H101 - TODO format
# TODO fix this  # Missing author name
# Fix: # TODO(yourname): Fix this issue

# H105 - Author tags (don't use)
# Author: Jane Doe  # Use version control instead
# Fix: Remove author tags entirely

# H106 - Vim configuration (don't use)
# vim: syntax=python:tabstop=4:shiftwidth=4
# Fix: Remove vim configuration entirely

# H212 - Type checking with assertEqual
assertEqual(type(obj), MyClass)  # Wrong approach
# Fix: assertIsInstance(obj, MyClass)

# H213 - Deprecated assertRaisesRegexp
self.assertRaisesRegexp(ValueError, "pattern", func)  # Deprecated
# Fix: self.assertRaises(ValueError, func)  # Or with context manager

# H232 - Mutable default arguments
def process_items(items=[]):  # Dangerous!
    items.append('new')
    return items
# Fix: def process_items(items=None):
#          items = items or []

# H501 - locals() usage
msg = "Error: %(error)s" % locals()  # Unclear what's being used
# Fix: msg = "Error: %s" % error  # Explicit

# H903 - UNIX line endings only
# Files with Windows line endings (\r\n) will fail
# Fix: Use UNIX line endings (\n) only
```

### Testing Violations

```python
# H202 - Testing for generic Exception
def test_operation(self):
    with self.assertRaises(Exception):  # Too broad
        risky_operation()
# Fix: with self.assertRaises(SpecificException):

# H203 - Use assertIsNone/assertIsNotNone
self.assertEqual(None, result)  # Less specific
# Fix: self.assertIsNone(result)

# H204 - Use assertEqual/assertNotEqual
self.assertTrue(a == b)  # Less specific
# Fix: self.assertEqual(a, b)

# H205 - Use assertGreater/assertLess
self.assertTrue(a > b)  # Less specific
# Fix: self.assertGreater(a, b)

# H211 - Use assertIsInstance
self.assertTrue(isinstance(obj, MyClass))  # Verbose
# Fix: self.assertIsInstance(obj, MyClass)

# H214 - Use assertIn/assertNotIn
self.assertTrue('key' in dictionary)  # Less specific
# Fix: self.assertIn('key', dictionary)
```

#### Common Commit Message Anti-Patterns to Avoid

```text
# Too vague - doesn't explain what or why
Fix bug

# Missing component context
Update configuration

# Past tense instead of imperative
Fixed the memory leak issue

# Too long subject line (>50 chars)
Fix the memory leak that occurs in compute manager during instance deletion

# No explanation of AI usage
Add new feature
Generated-By: claude-code

# Missing why/context
Switch to new libvirt reset API
```

## 10. OpenInfra Foundation AI Policy and DCO Compliance

### Commit Message Requirements (MANDATORY)

All AI-generated contributions MUST include proper commit message labeling per OpenInfra
Foundation AI Policy AND Developer Certificate of Origin (DCO) sign-off:

#### OpenStack Commit Message Structure

Follow this exact format for all commits:

```text
Subject line: imperative, < 50 chars, no period

Body paragraph explaining the WHY and WHAT of the change.
Wrap at 72 characters. Include enough detail for reviewers
to understand the problem being solved and how the fix works.

For AI contributions, explain the context and approach
used with the AI tool, focusing on the technical decisions
and reasoning behind the implementation.

Generated-By: claude-code (or Assisted-By: github-copilot)
Signed-off-by: Jane Doe <jane.doe@example.com>
Closes-Bug: #1234567
Change-Id: I1234567890abcdef1234567890abcdef12345678
```

#### Subject Line Rules (First Line - CRITICAL)

- **Imperative mood**: "Add user auth" not "Added user auth" or "Adding user auth"
- **Maximum 50 characters** (strictly enforced)
- **No period** at the end
- **Mention affected component**: Include "libvirt", "nova", "api", etc. when relevant
- **Be specific**: "Fix memory leak in compute manager" not "Fix bug"

#### Body Content Requirements

- **Explain WHY first**: What problem does this solve?
- **Explain WHAT**: What changes were made?
- **Explain HOW**: Overall approach (for complex changes)
- **Self-contained**: Don't assume reviewer has access to external bug trackers
- **Include limitations**: Mention known issues or future improvements needed
- **Wrap at 72 characters**

#### For Generative AI

```text
Add user authentication module

This module implements OAuth2 authentication for the API service
to address security requirements for multi-tenant access. The
implementation follows the existing Nova auth patterns but adds
support for token refresh and role-based permissions.

I used Claude Code to generate the initial implementation based on
the existing auth patterns in Nova. The generated code included
the OAuth2 flow, token validation, and basic error handling.
Manual modifications were made for OpenStack-specific configuration
handling, integration with existing keystone middleware, and
custom error messages and logging.

Generated-By: claude-4.6-opus-high
Signed-off-by: Jane Doe <jane.doe@example.com>
Closes-Bug: #2001234
Implements: blueprint oauth2-authentication
Change-Id: I1234567890abcdef1234567890abcdef12345678
```

#### For Predictive AI (code/auto completion)

```text
Fix memory leak in compute manager

The compute manager was not properly releasing resources when
instances were deleted, causing memory usage to grow over time
in long-running compute services. This was particularly visible
in environments with high instance turnover.

The fix ensures that all event listeners and cached objects
are properly cleaned up in the instance deletion path. Added
explicit resource cleanup in the _delete_instance method and
improved error handling to prevent partial cleanup states.

I used GitHub Copilot suggestions for the resource cleanup
patterns and error handling blocks. The core logic and OpenStack-
specific integration was written manually.

Assisted-By: claude-4.6-sonnet-medium
Signed-off-by: Jane Doe <jane.doe@example.com>
Closes-Bug: #2001235
Change-Id: I1234567890abcdef1234567890abcdef12345678
```

#### External References and Flags

Place all metadata at the end in this order:

```text
# AI labeling (always first in metadata section)
Generated-By: tool-name
# or
Assisted-By: tool-name

# DCO sign-off (required after July 1, 2025)
Signed-off-by: Real Name <email@domain.com>

# Bug references
Closes-Bug: #1234567      # Fully fixes the bug
Partial-Bug: #1234567     # Partial fix, more work needed
Related-Bug: #1234567     # Related but doesn't fix

# Blueprint reference
Implements: blueprint feature-name

# Impact flags (when applicable)
DocImpact: Changes require documentation updates
APIImpact: Modifies public HTTP API
SecurityImpact: Has security implications
UpgradeImpact: Affects upgrade procedures

# Gerrit tracking (auto-generated)
Change-Id: I1234567890abcdef1234567890abcdef12345678
```
**Never** add `JIRA:`, `rhbz#` references for git repositories in opendev or
openstack namespaces. Only references to Launchpad bugs `*-Bug: #`, or blueprints
`Implements: blueprint` are allowed.

#### DCO Sign-off Requirements (REQUIRED)

- **Every commit** must include `Signed-off-by: Bohdan Dobrelia <bdobreli@redhat.com>`
- **Use real name** (no pseudonyms or anonymous contributions)
- **Email must match** the Git configuration and Gerrit account
- **Always use the -s flag** when committing:

```bash
git config --global user.name "Bohdan Dobrelia"
git config --global user.email "bdobreli@redhat.com"
git commit -s  # The -s flag adds Signed-off-by automatically
```

### AI Policy: Generated-By vs Assisted-By

#### When to Use "Generated-By:"

Use **"Generated-By:"** for **generative AI** tools that produce substantial code artifacts:

- AI generated complete functions, classes, or modules
- AI created the initial implementation that you then modified
- Substantial portions of the code came from AI prompts
- Examples: Claude Code, ChatGPT, GitHub Copilot (when accepting large completions)

#### When to Use "Assisted-By:"

Use **"Assisted-By:"** for **predictive AI** tools that provide suggestions or minor edits:

- AI provided autocomplete suggestions you accepted
- AI helped with minor refactoring or renaming
- AI made small targeted changes based on prompts
- Examples: GitHub Copilot (autocomplete), Tabnine, code formatting tools

#### Key Principles (ALL AI Usage)

- **Human must be in the loop** - Always review and understand AI-generated code
- **Treat as untrusted source** - Apply the same scrutiny as code from unknown contributors
- **Ensure open source compatibility** - Configure tools to respect licensing
- **Document AI contributions** - Explain what AI generated and what you modified
- **Take responsibility** - Your DCO sign-off certifies you reviewed and approved all content

## 11. AI-Specific Generation Guidelines

### When Generating New Files

1. Start with Apache license header
2. Add module docstring
3. Place module-level constants after docstring, before imports
4. Organize imports per section 2
5. Define classes and functions with proper docstrings

### When Modifying Existing Files

1. Preserve existing license headers
2. Maintain import organization
3. Follow existing code style in the file
4. Add appropriate docstrings to new functions

### AI-Specific Commit Message Guidelines

When using AI tools, ALWAYS include:

1. **Context provided**: Brief description of what guidance was given to the AI
2. **AI contributions**: Which parts used AI assistance (structure, logic, patterns, etc.)
3. **Manual modifications**: What you changed, added, or customized manually
4. **Technical reasoning**: Explain the approach and decisions made
5. **Review confirmation**: Implicitly demonstrate you reviewed all AI-generated code through your explanations

## 13. Comprehensive Checklists

### Legal Compliance Checklist (ALL REQUIRED)

- [ ] AI tool configured for open source compatibility
- [ ] Generated code reviewed for copyright issues
- [ ] No proprietary claims by AI vendor on output
- [ ] Code is compatible with Apache 2.0 license
- [ ] Proper "Generated-By:" or "Assisted-By:" label added to commit
- [ ] Context explanation included in commit message
- [ ] **DCO sign-off included** (`Signed-off-by: Your Name <email>`)
- [ ] **Real name and valid email** used in sign-off (no pseudonyms)
- [ ] Commit message follows OpenStack structure (50 char subject, 72 char body)
- [ ] Commit message explains WHY, WHAT, and HOW of the change
- [ ] AI usage and technical approach documented in commit message

## 14. Validation Workflows and Commands

### Pre-Commit Validation

After generating code, run these validation commands:

```bash
# Syntax check all Python files
python -m py_compile $(find . -name "*.py")

# Style checks
tox -e pep8
# OR
flake8 .

# License header verification
find . -name "*.py" -exec grep -L "Apache License" {} \;

# Line length verification
flake8 --select=E501 .

# Import order verification
flake8 --select=H301,H303,H304,H306 .

# Hacking rules verification
flake8 --select=H201,H210,H216,H501,H105,H106,H212 .

# DCO sign-off verification
git log -1 --pretty=%B | grep "Signed-off-by:"
```

### Git Hook Setup for Change-Id

Install Gerrit Change-Id hook:

```bash
# Install commit-msg hook
scp -p -P 29418 bogdando@review.opendev.org:hooks/commit-msg .git/hooks/
chmod +x .git/hooks/commit-msg

# Verify Change-Id is present
git log -1 --pretty=%B | grep "Change-Id:"
```

### Full Validation Pipeline

```bash
# Complete validation before pushing
python -m py_compile $(find . -name "*.py") && \
tox -e pep8 && \
tox -e py3 && \
git log -1 --pretty=%B | grep "Signed-off-by:" && \
git log -1 --pretty=%B | grep "Change-Id:" && \
echo "✓ Ready to push!"
```

### CI Failure Troubleshooting

**Common pep8 failures:**

```bash
# Fix locally
tox -e pep8
# Address all issues
git commit --amend -s
```

**Unit test failures:**

```bash
# Run specific failing test
tox -e py3 -- path/to/test_file.py:TestClass.test_method
# Fix failing tests
git commit --amend -s
```

**Missing DCO sign-off:**

```bash
# Amend commit with sign-off
git commit --amend -s
```

**Missing Change-Id:**

```bash
# Install hook and amend
scp -p -P 29418 bogdando@review.opendev.org:hooks/commit-msg .git/hooks/
chmod +x .git/hooks/commit-msg
git commit --amend -s
```

## 15. IDE Integration Notes

For AI assistants working with IDEs:

- Set line length markers at 79 characters
- Configure to show whitespace and line endings
- Enable PEP 8 checking plugins
- Set Python indent to 4 spaces, no tabs
- Configure AI tools for open source compatibility mode
- Enable code duplication detection features

---

**AI Assistant Note**: This guide prioritizes the most common OpenStack CI failures AND
compliance with OpenInfra Foundation AI Policy. When in doubt, err on the side of being
more explicit and verbose rather than concise, as OpenStack values clarity and
maintainability over brevity. Always include proper AI attribution in commit messages.
