# AGENTS.md

## Project

`snakeboot`: Spring Boot ergonomics for hexagonal Python applications (Django, Django Ninja, wireup).

## Rules

* Imitate the basics of Spring Boot, not Spring. A feature belongs here when two applications need it
  and it knows nothing of either application's domain.
* Each package knows as little as possible. `transaction`, `component_scan` and `testing` use the standard
  library only; `events` adds wireup; `rest` adds Django Ninja; `django` adapts `transaction` to Django.
  The import-linter contracts in `pyproject.toml` enforce it.
* Fail at start-up, not at the first request: a broken controller, advice, listener or root raises
  while the application starts.
* Clean Code (Ruff and mypy strict enforce most of it): names that reveal intent, one level of
  abstraction per function, at most three positional and five parameters in total, every `noqa`
  with a code and a reason, a purpose docstring on every public name, `@override` on every override.
* Code, docstrings and the README are English.
* Every change keeps the empty case working: no controllers, no advices, no listeners.
  An application that has none of something is where such bugs hide.

## Commands

```text
uv sync                    install
uv run pre-commit install  once per clone
uv run pytest              tests, including the import contracts
uv run ruff format         format (line length 120)
uv run ruff check          lint
uv run mypy                strict type check
uv build                   wheel and sdist
```

## Release

1. Raise `version` in `pyproject.toml` (`uv version --bump minor` or `patch`) and add the entry to `CHANGELOG.md`.
2. Commit, then tag and push the tag: `git tag v0.2.0 && git push origin v0.2.0`.
3. `.github/workflows/publish.yml` runs the checks, builds, publishes to TestPyPI, installs and imports
   from there, and only then publishes to PyPI (trusted publishing, no tokens).

While the version starts with `0.`, a minor release may break the API; users pin `>=0.x,<0.(x+1)`.

