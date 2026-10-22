# Changelog

snakeboot follows [semantic versioning](https://semver.org/). While the version starts with `0.`,
a minor release may break the API: pin `snakeboot>=0.1,<0.2`.

## 0.1.2

First release on PyPI. The library is the same as 0.1.0; only the release pipeline changed.

- Release pipeline: `astral-sh/setup-uv` is pinned to its full version (`v10.3.2`); since v8 it publishes
  no major-version tags such as `v10`, so the 0.1.1 release could not start.

## 0.1.1

Never published: its release could not resolve `astral-sh/setup-uv@v10`.

- Release pipeline: the smoke test downloads from TestPyPI with pip on Python 3.13 (on an older Python,
  pip skips snakeboot because of `Requires-Python >= 3.13`); publishing skips files already on the index,
  so a release can be re-run. GitHub Actions updated (checkout v7, setup-uv v10, upload-artifact v7,
  download-artifact v8).

## 0.1.0

Published on TestPyPI only: its release stopped at the smoke test, before PyPI.

- `snakeboot.transaction`: `@transactional` (refuses `async def`), `after_commit` (robust), `TransactionManager`,
  `TransactionManagerRegistry`.
- `snakeboot.component_scan`: `@application_root`, `ComponentScan`; Django entry points skipped by default,
  the event publisher added through auto-configuration.
- `snakeboot.events`: `ApplicationEventPublisher` (valid without listeners), `@application_event_listener`,
  `@event_listener`, `@transactional_event_listener`.
- `snakeboot.rest`: singleton `@rest_controller` classes, `@route`, `@rest_controller_advice`,
  `@exception_handler`, `error_answer`; ambiguous mappings stop the start-up.
- `snakeboot.django`: `DjangoAtomicTransactionManager`.
- `snakeboot.testing`: `RecordingTransactionManager`, `declared_classes`.
