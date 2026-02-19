# OpenStack Development Guidelines for Claude Code

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
