# Changelog

snakeboot follows [semantic versioning](https://semver.org/). While the version starts with `0.`,
a minor release may break the API: pin `snakeboot>=0.1,<0.2`.

## 0.1.0

First release.

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
