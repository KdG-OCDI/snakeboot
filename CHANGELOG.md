# Changelog

snakeboot follows [semantic versioning](https://semver.org/). While the version starts with `0.`,
a minor release may break the API: pin `snakeboot>=0.4,<0.5`.

## 0.4.0

- `snakeboot.configuration`: a section is a component of the module that declares it. `@configuration_properties`
  puts a wireup provider next to the section, so the section enters the container with its module, like
  `@ConfigurationPropertiesScan`. `Configuration.injectables()` is gone.
- `snakeboot.configuration`: the configuration is read in two steps. `begin_configuration` reads the sections known
  before the container is built (`optional` ones only when their table is there) and leaves the other tables;
  `Configuration.complete` reads everything again with the sections of the container and refuses a table that no
  section claims. `load_configuration` takes both steps at once, as before. `sections_declared_in(module)` finds the
  sections a module declares.
- `snakeboot.django_application` (extras `configuration` and `django`): `configure_django`, at the bottom of
  settings.py, sets `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `LOGGING`, `DATABASES` and `CACHES` from
  `application.toml`, and `WIREUP` from the component scan; the app reads the sections of the container when Django
  starts. A setting that settings.py sets too stops the start.
- `snakeboot.rest`: `ControllerScan(component_scan).add_to(api)` replaces `RestControllerMounter().mount(api, scan=...)`
  and `RestControllerScanner`. It finds the controllers and advices in the modules of the component scan, the same
  modules that fill the container, instead of scanning packages a second time. `MountedRestComponents` is now
  `ScannedControllers`.
- `snakeboot.configuration`: extending `Section` is the contract, as 0.3.0 documented, and it is checked by class.
  `@configuration_properties` marks only a `Section` (also in its type), and `load_configuration` refuses a nested
  model that does not extend `Section`, even when it is frozen and refuses unknown keys, and a `Section` that changes
  its `model_config`. That no field has a default stays a separate rule of `load_configuration`.

## 0.3.0

- `snakeboot.configuration`: `Section`, the base class of every configuration model (frozen, unknown keys refused),
  so a model no longer repeats `model_config`; the error for a model that is not a `Section` says so.
- `DatabaseProperties` (`[database]`, a PostgreSQL database, `as_django_database()`) and `CacheProperties`
  (`[cache]`, Redis, `as_django_cache()`) next to `DjangoProperties`: the sections Django itself needs, so that
  an application declares only the sections of its own contexts.

## 0.2.0

- Add `snakeboot.configuration` (extra `configuration`, Pydantic Settings): `@configuration_properties`
  binds a Pydantic model to a table of `application.toml`; `load_configuration` reads that file, the
  profile named by `SNAKEBOOT_PROFILE` (`application-<profile>.toml`) and environment variables
  `SECTION__KEY__SUBKEY`, and nothing else; `Configuration.injectables()` hands every section to wireup
  by its type. `DjangoProperties` is the section `[django]`.
- The start stops on a default in code, a model that ignores unknown keys or is mutable, an unknown key
  or table, a missing file and a missing or invalid value.

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
