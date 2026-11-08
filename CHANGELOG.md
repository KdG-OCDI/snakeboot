# Changelog

snakeboot follows [semantic versioning](https://semver.org/). While the version starts with `0.`,
a minor release may break the API: pin `snakeboot>=0.6,<0.7`.

## Unreleased

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
  commands, those of its apps (`run_lifecycle`) included, and names the program `python -m myapp`. `CommandLineError` stops a command with a message and status 1.
- `snakeboot.configuration`: the table `[django]` is `[server]` (`ServerProperties`, environment `SERVER__*`), with
  the same keys. `DatabaseProperties` and `CacheProperties` lost `as_django_database` and `as_django_cache`;
  `snakeboot.django_application.django_settings` converts them.
- `snakeboot.component_scan` knows no Django: `DJANGO_ENTRY_POINTS` is `DEFAULT_EXCLUDE`, and `app_configs()` and
  `models()` are gone (`classes_extending("AppConfig")` finds what they found).

Moving an application from 0.6:

| 0.6 | now |
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
