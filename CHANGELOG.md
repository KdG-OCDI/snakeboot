# Changelog

snakeboot follows [semantic versioning](https://semver.org/). While the version starts with `0.`,
a minor release may break the API: pin `snakeboot>=0.10,<0.11`.

## 0.10.0

What most enterprise applications need from Spring Boot next: authorization, reliable events, optimistic locking,
the actuator, traces and structured logs, a lock for scheduled work, and CORS.

- `snakeboot.security` (standard library only): `Principal` moved here and has `roles` (`has_role`,
  `has_any_role`); `SecurityContext`, like `SecurityContextHolder`, holds the principal of the call in hand.
  `snakeboot.rest.Principal` is the same class.
- `snakeboot.rest`: `@roles_allowed("admin", ...)` on an endpoint or a controller, like `@RolesAllowed`: a caller with
  none of the roles is answered 403 `{"detail": "Forbidden"}`. An endpoint's own roles replace its controller's; roles
  on a public endpoint, or without a `BearerAuthentication`, stop the start. `BearerAuthentication.authenticate` may
  return a `Principal` with roles instead of an id. The web binding signs the caller in to the `SecurityContext` while
  the endpoint runs.
- `snakeboot.oauth2`: `JwtBearerAuthentication` returns a `Principal` whose roles are Keycloak's realm roles, its client
  roles for the audience and a plain `roles` claim; `roles_of(claims)` may be overridden.
- `snakeboot.data`: `Version()`, like JPA's `@Version`: an update holds only while the row has the version the entity was
  read with, else `OptimisticLockingFailureError`. `CreatedBy()` and `LastModifiedBy()` fill a `str | None` with the
  signed-in principal's name. A broken constraint is a `DataIntegrityViolationError`. `LockMode.PESSIMISTIC_WRITE_SKIP_LOCKED`
  is `SELECT ... FOR UPDATE SKIP LOCKED`.
- `snakeboot.events`: `@application_module_listener`, like Spring Modulith's `@ApplicationModuleListener`: after the
  commit, on the application's `TaskExecutor` (eight threads), in a transaction of its own, in the trace of the
  publisher. `ListenerMapping.delivery` (`Delivery`) replaces `ListenerMapping.after_commit`.
- `snakeboot.event_publication`: with `[database]`, the event publication registry, a transactional outbox like Spring
  Modulith's JDBC registry. The publisher's transaction writes one row of `snakeboot_event_publication` per module
  listener (the event as JSON); the listener's transaction deletes it. A failed or lost publication is delivered again,
  ten times at most, by a lifecycle component that also shows `snakeboot_event_publications_incomplete`. The optional
  table `[events]` (`EventsProperties`: `resubmit_every`, `in_flight`, `retry_after`, `max_attempts`) sets that timing,
  like `spring.modulith.events.*`.
- `snakeboot.scheduling`: `@scheduler_lock(name, at_most_for=..., at_least_for=...)`, like ShedLock's
  `@SchedulerLock`: one replica runs a turn, the others skip it. Every scheduled run is a trace of its own.
- `snakeboot.scheduler_lock`: with `[database]`, the locks as rows of `snakeboot_scheduler_lock`.
- `snakeboot.actuator` (wireup only): `HealthIndicator`, `ApplicationHealth` and `MeterRegistry` (counters, timers as
  histograms, gauges, in Prometheus's text format, without a client library). The database, Redis and RabbitMQ bring
  their indicators.
- `snakeboot.fastapi_web`: `/health` checks every indicator and answers 503 when one is DOWN; `/health/liveness` and
  `/health/readiness` for Kubernetes's probes; `/metrics` for Prometheus, with `http_server_requests_seconds` per
  method, route and status. Every call runs in a span of the caller's `traceparent`, or of a new trace. `[cors]`
  (`CorsProperties`) names the origins whose pages may call the API.
- `snakeboot.tracing` (standard library only): `TraceContext`, W3C Trace Context. The `RabbitTemplate` sends the
  `traceparent`, a `@rabbit_listener` continues it, and every log line carries the trace id.
- `[logging] format = "ecs"` (`LoggingProperties`) writes every log line as JSON in the Elastic Common Schema.
- `TestApplication` runs the `@application_module_listener` methods on the caller's thread.
- The README says where an application's files live: `application.toml` and its profiles in the application package
  (the package of the `@application_root` class, snakeboot's classpath root), migrations next to their entities,
  `static/` and `templates/` kept free for pages.
- `make_migration` writes the tables of snakeboot's own entities (`snakeboot_event_publication`,
  `snakeboot_scheduler_lock`) into the application's migrations.

Moving an application from 0.9:

| 0.9 | 0.10 |
|---|---|
| `/health` answers `{"status": "ok", "service": ...}`, always 200 | `{"status": "UP", "service": ..., "components": {...}}`, 503 when a part is DOWN |
| a liveness probe on `/health` | a liveness probe on `/health/liveness`, a readiness probe on `/health/readiness` |
| `JwtBearerAuthentication.authenticate(token) == "ann"` | `== Principal("ann", roles=...)` |
| `ListenerMapping(event_types, after_commit=True)` | `ListenerMapping(event_types, Delivery.AFTER_COMMIT)` |
| `python -m myapp make_migration` with `[database]` | writes `snakeboot_event_publication` and `snakeboot_scheduler_lock` once; run `migrate` |

## 0.9.0

- `python -m myapp serve` starts the web server, like the server Spring Boot embeds: uvicorn, where `[server] host`
  and `port` say, with `[server] workers` processes, each building the application and its lifecycle; `--reload`
  restarts it when a source file changes. An application needs no asgi.py any more, and a Dockerfile names no server.
  `asgi_application` stays, for a deployment that runs an ASGI server of its own.
- `[server]` has `host`, `port` and `workers`, which every application writes (`host = "0.0.0.0"`, `port = 8000`,
  `workers = 1` say).
- The application context is a component of its own container, under `ApplicationContext`.

Moving an application from 0.8:

| 0.8 | 0.9 |
|---|---|
| `myapp/asgi.py` with `application = asgi_application(MyApplication)` | nothing |
| `uvicorn myapp.asgi:application --host 0.0.0.0 --port 8000 --workers 2` | `python -m myapp serve`, with `[server] host`, `port` and `workers` |
| `uvicorn myapp.asgi:application --reload` | `python -m myapp serve --reload` |

## 0.8.0

snakeboot runs on FastAPI, SQLAlchemy and Alembic instead of Django, and an application sees none of them: its
entities, repositories, migrations and tests are in snakeboot's terms now too. 0.7 stays on the branch `release-0.7`.

- `snakeboot.application`: the application context, like Spring's `ApplicationContext`. It reads the configuration,
  builds wireup's container from the component scan, installs the transaction manager when there is a database, and
  runs the commands; it knows no framework. `snakeboot.boot` names the bindings: FastAPI for the REST API, SQLAlchemy
  with `[database]`, Redis with `[cache]`, RabbitMQ with `[rabbitmq]`. An application without a table imports none of
  them, and `python -m myapp help` answers without loading a web framework.
- `snakeboot.fastapi_web`: the REST API on FastAPI, under /api with Swagger UI at /api/docs and /health beside it.
  Controllers, advices, `Principal`, `BearerAuthentication`, `InvalidRequestError` and `ServerSentEvents` work as
  they did; a stream is documented as `text/event-stream`. `[server] allowed_hosts` is enforced by Starlette's
  `TrustedHostMiddleware` (`*`, `games.example.com`, `*.example.com`).
- `snakeboot.data`: entities and repositories, like Spring Data. `@entity` on a dataclass, with `Id`, `Column`,
  `Index`, `CreatedDate`, `LastModifiedDate`, `Json` (any JSON value; `Any` is JSON too) and `Vector`; `CrudRepository[E, ID]` interfaces whose methods are
  derived from their names (`find_by_status_and_join_deadline_less_than_equal`, `find_top_100_by_..._order_by_id_asc`,
  `count_by`, `exists_by`, `delete_by`, a `PageRequest`), `@query` for SQL, `@lock` for `SELECT ... FOR UPDATE`.
  snakeboot implements an interface when its module is imported; a method it cannot implement stops the start.
- `snakeboot.sqlalchemy_data` (extra `data`): the entities mapped to SQLAlchemy without the classes knowing it,
  `@transactional` on SQLAlchemy's session (a nested call is a savepoint), and migrations as plain SQL scripts next to
  the entities, like Flyway: `python -m myapp migrate` runs them once each, `python -m myapp make_migration "..."`
  writes the next one from what Alembic finds missing. PostgreSQL through psycopg; pgvector with the extra `vector`.
- `snakeboot.cache` and `snakeboot.redis_cache` (extra `cache`): a `Cache` of JSON values, in Redis with `[cache]`, in
  memory for a test.
- `snakeboot.boot.testing.TestApplication`: starts the application as it runs, with doubles for components and a
  database in memory whose tables come from the entities, and calls its REST API in the same process, like
  `@SpringBootTest` with `@AutoConfigureTestDatabase` and `TestRestTemplate`. Every test gets a fresh application.
- `run_lifecycle` is a `CommandLineRunner` of snakeboot's, and `help` lists snakeboot's commands apart from the
  application's.
- `ApplicationComponents` finds marked classes too, and `get` takes abstract classes and Protocols as mypy expects.
- wireup 2.13.1 or later: 2.13.0 cannot build a container in which a component depends on the event publisher of
  an application without listeners.
- Gone: `snakeboot.django`, `snakeboot.django_application`, `snakeboot.django_ninja`, `wsgi_application`,
  `DjangoConfigurer`, `ComponentScan.classes_extending`, the extras `django` and `ninja`, and `[server] secret_key`.

Moving an application from 0.7:

| 0.7 | 0.8 |
|---|---|
| `snakeboot[configuration,django,ninja]` | `snakeboot[configuration,web,data]` (+ `vector`, `cache`, `testing`) |
| `wsgi_application(MyApplication)` under gunicorn | `asgi_application(MyApplication)` under uvicorn |
| `[server] secret_key`, `SERVER__SECRET_KEY` | nothing |
| a Django model in an app with an `AppConfig` | an `@entity` dataclass, with the same table and index names |
| `Model.objects.filter(...)`, `select_for_update()`, `save()` | a `CrudRepository` interface: derived methods, `@lock`, `save` |
| `CosineDistance`, `annotate`, `values` | `@query("... embedding <=> CAST(:embedding AS vector) ...")` |
| `auto_now`, `auto_now_add` | `LastModifiedDate()`, `CreatedDate()` |
| `transaction.atomic()` in an adapter | `@transactional` |
| Django migrations, `python -m myapp migrate` | `migrations/V1__....sql` next to the entities, `python -m myapp migrate` |
| `makemigrations` | `python -m myapp make_migration "description"` |
| `django.core.cache.caches["default"]` | an injected `Cache` |
| pytest-django, `settings_under_test.py`, `django_db` | `TestApplication.start(MyApplication, overrides={...})` |
| `django.test.Client`, `get_app_container().override(...)` | `app.client()`, `overrides=` |
| a 422's `loc` `["body", "body", "title"]` | `["body", "title"]` |
| `python -m myapp runserver` | `uvicorn myapp.asgi:application --reload` |

## 0.7.0

An application speaks snakeboot, not Django: its entry points, controllers, commands and configuration import
nothing of Django or Django Ninja any more, so snakeboot can bind another framework without changing them.

- `snakeboot.boot`: `run`, `wsgi_application` and `asgi_application`, where an application's entry points import
  them from. `snakeboot.django_application` still has them, as the binding that `boot` hands over today.
- `snakeboot.rest` knows no web framework. An endpoint takes no `request`: it takes path, query and body parameters,
  and a parameter of type `Principal` for whom the token belongs to, like `@AuthenticationPrincipal`. The body is the
  return annotation, `response=` only when it differs; `status=` sets the status of the answer, like
  `@ResponseStatus`; `public=True` opens an endpoint, like `permitAll()`. A route takes no other option. A method that
  takes `request`, a public endpoint that asks for a `Principal` and a `Principal` without a `BearerAuthentication`
  stop the start.
- `snakeboot.rest`: `ServerSentEvents`, like Spring's `SseEmitter`. An endpoint that returns it streams
  `text/event-stream`, uncached and unbuffered, with a heartbeat comment after 15 silent seconds and an end after 30
  minutes. `ServerSentEvents.watching(read, every=..., until=..., as_event=...)` reads a value in the call, then
  sends it whenever it changed; its reads run between fresh database connections. `ServerSentEvent` data that is no
  text is the JSON a REST answer would hold.
- `snakeboot.rest`: `InvalidRequestError`, like Spring's `MethodArgumentNotValidException`: a call that does not fit its
  endpoint (a missing field, a wrong type), with one `RequestProblem` per error. An advice answers it like any error,
  and `error_answer` makes it `{"code": "invalid_request", ...}`; without such an advice the framework answers 422 its
  own way.
- `snakeboot.django_ninja`: the REST API on Django Ninja (`rest_api`, `url_patterns`, `NinjaEndpointFactory`), which
  was part of `snakeboot.rest`. `ControllerScan(...).find()` returns the checked API without building anything.
- `snakeboot.command_line`: `CommandLineRunner`, like Spring Boot's, with constructor injection and argparse.
  `add_arguments` is a classmethod and `run_command(SelfPlayCommand, arguments, program=..., build=...)` parses before
  it builds, so `--help` and a wrong argument answer at once, whatever the command depends on.
  `python -m myapp self_play --games 20` runs the one its first argument names; `help` lists them next to Django's
  commands, those of its apps (`run_lifecycle`) included, and names the program `python -m myapp`.
  `CommandLineError` stops a command with a message and status 1.
- `snakeboot.configuration`: the table `[django]` is `[server]` (`ServerProperties`, environment `SERVER__*`), with
  the same keys. `DatabaseProperties` and `CacheProperties` lost `as_django_database` and `as_django_cache`;
  `snakeboot.django_application.django_settings` converts them.
- `snakeboot.component_scan` knows no Django: `DJANGO_ENTRY_POINTS` is `DEFAULT_EXCLUDE`, and `app_configs()` and
  `models()` are gone (`classes_extending("AppConfig")` finds what they found).

Moving an application from 0.6:

| 0.6 | 0.7 |
|---|---|
| `from snakeboot.django_application import run` (and `asgi_application`, `wsgi_application`) | `from snakeboot.boot import run` |
| `def get_game(self, request: HttpRequest, game_id: str)` | `def get_game(self, game_id: str)` |
| `authenticated_principal(request)` | a parameter `player: Principal`, then `player.name` |
| `@route.get("/x", response=GameDTO)` with `-> GameDTO` | `@route.get("/x")` |
| `@route.post("/x", response={201: MoveDTO})`, `return Status(201, move)` | `@route.post("/x", status=201)`, `return move` |
| `@route.get("/x", auth=None)` | `@route.get("/x", public=True)` |
| `class BodyDTO(ninja.Schema)` | `class BodyDTO(pydantic.BaseModel)` |
| `StreamingHttpResponse(events, content_type="text/event-stream")` with `sync_to_async` reads | `-> ServerSentEvents`, `ServerSentEvents.watching(...)` |
| `@exception_handler(ninja.errors.ValidationError, status=422)` | `@exception_handler(InvalidRequestError, status=422)` |
| `class Command(BaseCommand)` with `@inject_app` and an `apps.py` for the commands | `class X(CommandLineRunner, command="...")`, no `apps.py` |
| `[django]`, `DJANGO__SECRET_KEY`, `DjangoProperties` | `[server]`, `SERVER__SECRET_KEY`, `ServerProperties` |

## 0.6.0

- `snakeboot.lifecycle`: components that start and stop with the server, like Spring's `SmartLifecycle`. A subclass
  of `Lifecycle` is a component; `ApplicationLifecycle` starts every one in phase order and stops them in reverse,
  then publishes `ApplicationReadyEvent` to the event listeners. A listener of that event that raises stops the
  start-up, as in Spring Boot.
- `snakeboot.django_application`: `asgi_application` answers uvicorn's `lifespan`, which Django's handler refuses, and
  runs the lifecycle around Django's handler; it returns a `LifecycleAsgiApplication` instead of Django's
  `ASGIHandler`. `python -m myapp run_lifecycle` runs the lifecycle without a web server until SIGTERM or SIGINT.
  Threads outside a request get their components and fresh database connections from `background_work`.
- `snakeboot.scheduling`: `@scheduled(fixed_rate=..., fixed_delay=..., initial_delay=...)`, like `@Scheduled`, on one
  thread. `[scheduling] auto_startup = false` (`SchedulingProperties`) keeps a process from running them.
- `snakeboot.rabbitmq` (extra `rabbitmq`): `@rabbit_listener` and `RabbitTemplate` on RabbitMQ through pika, like
  Spring AMQP, with the section `[rabbitmq]` (`RabbitProperties`); only an application with that section gets them.
  A listener declares its exchange, queue and binding, converts the JSON body, acknowledges on return, refuses for good
  on `RejectAndDontRequeueError` or an unreadable body, and tries another failure three times before refusing it. The
  template sends persistent JSON with publisher confirms and tries a fresh connection once.
- `snakeboot.component_scan`: `classes_marked` and `methods_marked` find what decorators marked, like Spring's
  `MethodIntrospector`; `ControllerScan` uses them, and so do the scheduler and the listeners.
- pika's own log messages start at WARNING, so a listener's connection does not fill the log.

## 0.5.2

- `snakeboot.rest`: a controller is resolved under ASGI too. Under `asgi_application` wireup's request scope is
  asynchronous and its `get` returns a coroutine, so 0.5.0 and 0.5.1 answered every call with a 500 ("The container
  gave <coroutine ...> as the BearerAuthentication"). A synchronous endpoint now resolves synchronously, as wireup's own
  class-based views do.
- The release workflow downloads the new version from TestPyPI through the JSON API of that version, not through the
  index, which the CDN may keep for ten minutes.

## 0.5.1

- `snakeboot.rest`: `class X(BearerAuthentication, component=False)` marks a base meant to be extended; it is not
  registered with the container. `JwtBearerAuthentication` is such a base, so a module that imports it to extend it
  holds one `BearerAuthentication`, not two (0.5.0 stopped such an application with
  `DuplicateServiceRegistrationError`).

## 0.5.0

- `snakeboot.oauth2` (extra `oauth2`): `JwtBearerAuthentication`, like Spring Boot's oauth2 resource server. An adapter
  that extends it accepts the signed JWT access tokens of one authorization server (Keycloak, for example): the
  issuer's public keys come from `jwks_uri` and are cached, and a token needs the right signature, `iss`, `aud` and an
  `exp` in the future; its `sub` is the principal.
- `snakeboot.configuration`: `OAuth2Properties`, the section `[oauth2]` (`issuer_uri`, `jwks_uri`, `audience`).
  `django_settings` reads it when the table is there, like `[database]` and `[cache]`, so it joins the container.
- `snakeboot.django_application`: `asgi_application(MyApplication)` for uvicorn, next to `wsgi_application`. Under
  ASGI a response streams from an async iterator, such as server-sent events, without holding a thread.

## 0.4.0

- `snakeboot.configuration`: a section is a component of the module that declares it. `@configuration_properties`
  puts a wireup provider next to the section, so the section enters the container with its module, like
  `@ConfigurationPropertiesScan`. `Configuration.injectables()` is gone.
- `snakeboot.configuration`: the configuration is read in two steps. `begin_configuration` reads the sections known
  before the container is built (`optional` ones only when their table is there) and leaves the other tables;
  `Configuration.complete` reads everything again with the sections of the container and refuses a table that no
  section claims. `load_configuration` takes both steps at once, as before. `sections_declared_in(module)` finds the
  sections a module declares.
- An application is a class marked with `@application_root`, like `@SpringBootApplication`, started with
  `run(MyApplication)` (manage.py, `python -m`) or `wsgi_application(MyApplication)` (gunicorn), like
  `SpringApplication.run`. It writes no settings.py and no urls.py: snakeboot owns Django's settings module
  (`snakeboot.django_application.settings`), so nothing can change the settings after snakeboot.
- `@application_root(base_packages=...)` names the packages of the container, like `scanBasePackages`;
  `application_package(cls)` is the package of the application, where `application.toml` lies.
- `snakeboot.django_application` (extras `configuration` and `django`): `django_settings(MyApplication)` builds every
  Django setting: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `LOGGING`, `DATABASES` and `CACHES` from `application.toml`,
  `WIREUP` from the component scan, `INSTALLED_APPS` from the Django `AppConfig`s in the component scan, and Django's
  defaults for the rest. When Django starts, the app reads the sections of the container and, with a database,
  installs `DjangoAtomicTransactionManager` for `@transactional`. A model outside every app stops the start.
- `snakeboot.django_application`: a `DjangoConfigurer` in the component scan or next to the application class adds
  Django apps (`installed_apps`) and middleware (`middleware`, between wireup's and CommonMiddleware), like a
  `WebMvcConfigurer`; snakeboot finds it by reading the source, like an `AppConfig`.
- `snakeboot.rest`: an adapter that extends `BearerAuthentication` is a component of the container, like a
  `SecurityFilterChain` bean; with one in the component scan, every endpoint needs a bearer token it accepts.
- `snakeboot.component_scan`: `ComponentScan.classes_extending(base)` lists the classes written as subclasses of
  `base`, by reading the source.
- `snakeboot.openapi` (standard library only): `@openapi_definition(title, version, description)` describes the
  API, like springdoc's `@OpenAPIDefinition`. `snakeboot.rest`: `rest_api(MyApplication)` builds it, and `snakeboot.rest.urls` serves it under `/api/`, next
  to `/health` (`{"status": "ok", "service": "<package>"}`).
- `snakeboot.component_scan`: `ComponentScan.app_configs()` and `ComponentScan.models()` list the Django `AppConfig`s
  and models under the base packages, by reading the source: nothing is imported, so settings can use them.
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
