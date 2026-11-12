# AGENTS.md

## Project

`snakeboot`: Spring Boot ergonomics for hexagonal Python applications (wireup, FastAPI, SQLAlchemy, Alembic).

## Rules

* Imitate the basics of Spring Boot, not Spring. A feature belongs here when two applications need it
  and it knows nothing of either application's domain.
* Each package knows as little as possible. `transaction`, `component_scan`, `openapi`, `cache`, `security`,
  `tracing` and `testing` use the standard library only; `events`, `rest`, `data`, `command_line` and `actuator` add
  wireup; `event_publication` and `scheduler_lock` keep snakeboot's own tables in snakeboot's terms, through `data`;
  `application` starts an application in no framework's terms. Each binding knows one framework: `fastapi_web`
  publishes `rest` and `actuator` on FastAPI, `sqlalchemy_data` binds `data` and `transaction` to SQLAlchemy and
  Alembic, `redis_cache` binds `cache` to Redis, `pytest_testing` binds `testing` to pytest (its plugin starts
  boot's `TestApplication` and imports nothing heavy until a test needs it); `boot` names the bindings an
  application starts on. The import-linter contracts in `pyproject.toml` enforce it.
* An application imports snakeboot, never the framework underneath. Only the bindings and `boot` know FastAPI,
  Starlette, SQLAlchemy, Alembic or Redis; whatever an application writes (entry points, controllers, entities,
  repositories, migrations, commands, listeners, sections, tests) is in snakeboot's terms, so a binding to another
  framework changes no application. `tests/test_without_a_web_framework.py` checks it at run time.
* Fail at start-up, not at the first request: a broken controller, advice, entity, repository, listener, scheduled
  method or root raises while the application starts.
* Clean Code (Ruff and mypy strict enforce most of it): names that reveal intent, one level of
  abstraction per function, at most three positional and five parameters in total, every `noqa`
  with a code and a reason, a purpose docstring on every public name, `@override` on every override.
* Code, docstrings and the README are English.
* Every change keeps the empty case working: no controllers, no advices, no listeners, no entities, no database.
  An application that has none of something is where such bugs hide.

## Commands

```text
uv sync                    install
uv run pre-commit install  once per clone
uv run pytest              tests, including the import contracts (SNAKEBOOT_TEST_POSTGRESQL_URL adds PostgreSQL's)
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

