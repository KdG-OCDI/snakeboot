# snakeboot

Spring Boot ergonomics for hexagonal Python applications, wired by [wireup](https://github.com/maldoinc/wireup)
and running on Django and Django Ninja underneath.

snakeboot imitates the basics of Spring Boot, not Spring itself. Each part is a handful of small
classes you can read in an afternoon, and none of them knows anything about your domain.

An application speaks snakeboot, not Django: its entry points, controllers, commands, listeners and configuration
import nothing of Django or Django Ninja, so snakeboot can bind another framework without changing them. Only the
persistence adapters, which hold the models and queries of the ORM, and the tests that use Django's database, still
see Django.

| snakeboot | Spring Boot | Needs |
|---|---|---|
| `@transactional`, `after_commit` | `@Transactional`, `@TransactionalEventListener(AFTER_COMMIT)` | nothing |
| `@application_root`, `ComponentScan` | `@SpringBootApplication`, `@ComponentScan` | nothing |
| `ApplicationEventPublisher`, `@event_listener`, `@transactional_event_listener` | the same names | wireup |
| `@rest_controller`, `@route.get(status=...)`, `@rest_controller_advice`, `@exception_handler` | `@RestController`, `@GetMapping`, `@ResponseStatus`, `@RestControllerAdvice`, `@ExceptionHandler` | `snakeboot[ninja]` |
| `Principal` | `@AuthenticationPrincipal` | `snakeboot[ninja]` |
| `InvalidRequestError`, `RequestProblem` | `MethodArgumentNotValidException` | `snakeboot[ninja]` |
| `ServerSentEvents`, `ServerSentEvent` | `SseEmitter`, `ServerSentEvent` | `snakeboot[ninja]` |
| `DjangoAtomicTransactionManager` | `PlatformTransactionManager` for JDBC | `snakeboot[django]` |
| `@configuration_properties`, `Section`, `load_configuration`, `application-<profile>.toml` | `@ConfigurationProperties`, `@ConfigurationPropertiesScan`, profiles | `snakeboot[configuration]` |
| `ServerProperties`, `DatabaseProperties`, `CacheProperties` | `server.*`, `spring.datasource.*`, `spring.data.redis.*` | `snakeboot[configuration]` |
| `snakeboot.boot`: `run`, `wsgi_application`, `asgi_application` | `SpringApplication.run`, auto-configuration | `snakeboot[configuration,django]` |
| `CommandLineRunner`, `CommandLineError` | `CommandLineRunner`, Spring Shell's `@Command` | `snakeboot[configuration,django]` |
| `DjangoConfigurer`, `django_settings` | `WebMvcConfigurer` | `snakeboot[configuration,django]` |
| `BearerAuthentication` | a `SecurityFilterChain` bean | `snakeboot[ninja]` |
| `JwtBearerAuthentication`, `OAuth2Properties` | `spring-boot-starter-oauth2-resource-server`, `spring.security.oauth2.resourceserver.jwt.*` | `snakeboot[oauth2]` |
| `Lifecycle`, `ApplicationReadyEvent`, `run_lifecycle` | `SmartLifecycle`, `ApplicationReadyEvent`, an application without the web starter | wireup |
| `@scheduled`, `SchedulingProperties` | `@Scheduled` | `snakeboot[configuration,django]` |
| `@rabbit_listener`, `RabbitTemplate`, `RabbitProperties`, `RejectAndDontRequeueError` | `@RabbitListener`, `RabbitTemplate`, `spring.rabbitmq.*`, `AmqpRejectAndDontRequeueException` | `snakeboot[rabbitmq]` |
| `@openapi_definition` | springdoc's `@OpenAPIDefinition` | nothing |
| `snakeboot.django_ninja` | the REST API and `/health` of the application, on Django Ninja | `snakeboot[ninja]` |
| `RecordingTransactionManager`, `declared_classes` | spring-test | nothing |

The transaction, component scan and testing packages import nothing but the standard library,
so the application layer of a hexagonal application can use `@transactional` without importing Django. The REST,
command line, event and lifecycle packages add wireup, and no web framework: a controller or a command is a module
that imports without Django.

## Install

```bash
uv add "snakeboot[configuration,django,ninja]"
uv add "snakeboot[configuration,django,ninja,rabbitmq]"   # with RabbitMQ
```

## A tour

**The application.** A class marked with `@application_root`, like `@SpringBootApplication`, is the application.
Its component scan decides what goes into the container: the package of the class, or the packages `base_packages`
names. The scan skips the server entry points (`wsgi.py`, `asgi.py`) and migrations, and adds the components snakeboot
provides itself (the event publisher, the lifecycle, the scheduler). `run` starts it, like `SpringApplication.run`;
the entry points import it from `snakeboot.boot`, which stays the same whatever framework runs underneath.

```python
# myapp/myapp_application.py
@openapi_definition(title="My service", version="1.0.0")
@application_root(base_packages=("myapp_core",))
class MyApplication: ...


# manage.py and myapp/__main__.py               # myapp/wsgi.py, for gunicorn
from snakeboot.boot import run                   application = wsgi_application(MyApplication)
                                                 # myapp/asgi.py, for uvicorn (streaming, server-sent events)
run(MyApplication)                               application = asgi_application(MyApplication)
```

The application writes no settings.py and no urls.py: snakeboot owns Django's settings module and builds every
setting from the application class and its `application.toml`, next to it (`django_settings`, below). Nothing can
change them after snakeboot. The URLs are the REST API under `/api/`, described by `@openapi_definition`, and
`/health`.

**Typed configuration.** A `Section` (a frozen Pydantic model that refuses unknown keys, the base class of every
configuration model) is bound to one table of `application.toml`, like `@ConfigurationProperties`. A section is a
component of the module that declares it: when the component scan puts that module in the container, the section
comes along, like `@ConfigurationPropertiesScan`, and an adapter asks for it by type.

```python
@configuration_properties("chatbot")
class ChatbotProperties(Section):
    model: str  # no default: the value is in application.toml
    llm: LanguageModelProperties  # a nested Section is the table [chatbot.llm]
```

**Django, configured.** `django_settings(MyApplication)` builds the settings, like Spring Boot's
auto-configuration: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` and `LOGGING` from `[server]`; `DATABASES` from
`[database]` (PostgreSQL) and `CACHES` from `[cache]` (Redis), when `application.toml` has those tables; the container
(`WIREUP`) from the component scan; and `INSTALLED_APPS`: snakeboot, wireup and every Django `AppConfig` of the
component scan. The scan finds them, and the models, by reading the source, so nothing is imported before Django
starts; a model outside every app stops the start. When Django starts, `snakeboot.django_application` reads the
sections declared in the modules of the container, checks every table and, with a database, installs the transaction
manager of `@transactional`.

Django apps and middleware from outside the project come from a `DjangoConfigurer`, like a `WebMvcConfigurer`.
snakeboot finds it in the component scan or next to the application class, as it finds an `AppConfig`, and imports
its module while it builds the settings, so that module holds strings only:

```python
class CorsConfigurer(DjangoConfigurer):
    installed_apps = ("corsheaders",)
    middleware = ("corsheaders.middleware.CorsMiddleware",)  # after wireup's, before CommonMiddleware
```

A test that needs a double takes the settings and replaces that one setting:

```python
# settings_under_test.py, the DJANGO_SETTINGS_MODULE of the tests
globals().update(django_settings(MyApplication))
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
```

Without Django, `load_configuration(ChatbotProperties, package="myapp")` reads the sections it is given.

The values come from three places, a later one overriding an earlier one key by key:

| Source | Holds | Spring Boot |
|---|---|---|
| `application.toml` in the package | every value the application runs with in production | `application.yml` |
| `application-<profile>.toml`, when `SNAKEBOOT_PROFILE` names one | what differs on a developer machine, say | `application-local.yml`, `SPRING_PROFILES_ACTIVE` |
| environment variables `SECTION__KEY__SUBKEY` | secrets and addresses of one deployment | relaxed binding |

Nothing else is read: no `.env` file, no default in code, no command line. The start stops when a model does
not extend `Section`, changes its `model_config` or has a default; when a file or a value is missing; when a key
or a table is unknown (a typo in `application.toml` or in `CHATBOT__LLM__MODLE`). Tables are merged, not replaced,
so put the variant without keys of its own in `application.toml` when a profile or the environment may choose
another.

**Transactions.** A use case declares its boundary; composition chooses the technology.

```python
@injectable
class CancelRegistrationUseCase:
    @transactional
    def execute(self, request: CancelRegistrationRequestDTO) -> None:
        workshop = self._workshops.get(...)
        workshop.cancel_registration(...)
        self._workshops.save(workshop)
        self._events.publish_all(workshop.pull_events())


# at start-up; snakeboot.django_application does this itself when the application has a database
TransactionManagerRegistry.install(DjangoAtomicTransactionManager())
```

**Application events.** Listeners react to facts after the commit, so a rolled-back change never
reaches anyone, and a failing listener cannot undo a committed one.

```python
@application_event_listener
class ParticipantNotificationListener:
    def __init__(self, notifications: NotificationPort) -> None:
        self._notifications = notifications

    @transactional_event_listener(WaitlistedParticipantPromoted)
    def notify_promoted(self, event: WaitlistedParticipantPromoted) -> None: ...
```

**REST controllers.** Singleton classes with constructor injection. `ControllerScan` finds them in the modules of
the component scan, the same modules that fill the container, and `snakeboot.django_ninja` publishes their routes.
A controller sees no request: an endpoint takes what the call carries (path and query parameters, a body as a
Pydantic model) and returns the body, whose type is its return annotation; `status=` sets the status of the answer,
like `@ResponseStatus`. A call that does not fit (a missing field, a wrong type) is an `InvalidRequestError`, which
an advice answers like any error, as with Spring's `MethodArgumentNotValidException`. Two endpoints for the same URL,
two answers for one error, or a method that takes `request` stop the start-up.

```python
@rest_controller("/workshops", tags=["workshops"])
class WorkshopRestController:
    def __init__(self, enrollment: EnrollmentFacadePort) -> None:
        self._enrollment = enrollment

    @route.get("/{workshop_id}")
    def get_workshop(self, workshop_id: str) -> WorkshopViewDTO: ...

    @route.post("", status=201)
    def create_workshop(self, body: NewWorkshopDTO) -> WorkshopViewDTO: ...


@rest_controller_advice
class EnrollmentRestErrorAdvice:
    @exception_handler(WorkshopNotFoundError, status=404)
    def answer_not_found(self, error: Exception) -> dict[str, str]:
        return error_answer(error)  # {"code": "workshop_not_found", "detail": "..."}

    @exception_handler(InvalidRequestError, status=422)
    def answer_invalid_request(self, error: Exception) -> dict[str, str]:
        return error_answer(error)  # {"code": "invalid_request", "detail": "body.body.title: Field required"}
```

**Server-sent events.** An endpoint that returns `ServerSentEvents` streams, like one that returns Spring's
`SseEmitter`: the web framework serves it as `text/event-stream`, uncached and unbuffered, and under ASGI a watching
client holds no thread. `ServerSentEvents.watching` covers what most streams do: it reads a value once in the call
(so an unknown id answers 404 as usual), then every `every`, and sends it whenever it changed, until `until` holds.
A silence of 15 seconds gets a comment that keeps proxies open, and a stream ends after 30 minutes, when the
browser's `EventSource` reconnects. The reads run as the framework runs synchronous code, between fresh database
connections; `ServerSentEvents(source)` takes an async iterable of `ServerSentEvent`s for any other stream.

```python
@route.get("/games/{game_id}/events")
def watch_game(self, game_id: str) -> ServerSentEvents:
    return ServerSentEvents.watching(
        lambda: self._get_game.execute(GetGameRequestDTO(game_id=game_id)),
        every=timedelta(milliseconds=500),
        until=lambda game: game.status in FINAL_STATUSES,
        as_event=lambda game: ServerSentEvent(game, event="game", id=str(game.version)),  # data as JSON
    )
```

**Authentication.** An adapter that extends `BearerAuthentication` is a component of the container, like a
`SecurityFilterChain` bean: its constructor receives sections and ports by type. With one in the component scan, every
endpoint needs `Authorization: Bearer <token>`, the OpenAPI document says so, and a parameter of type `Principal`
receives whom the token belongs to, like `@AuthenticationPrincipal`. `/health` stays open; an endpoint opts out with
`public=True`. A public endpoint that asks for a `Principal`, or a `Principal` in an API without authentication,
stops the start-up.

```python
class KeycloakTokens(BearerAuthentication):
    def __init__(self, properties: SecurityProperties) -> None:
        self._properties = properties

    @override
    def authenticate(self, token: str) -> str | None: ...  # the subject of a valid token, or None for 401


# in a controller
@route.post("/{workshop_id}/registrations", status=201)
def register(self, workshop_id: str, participant: Principal) -> RegistrationDTO:
    return self._enrollment.register(workshop_id, participant_id=participant.name)
```

**Tokens of an authorization server.** For the JWT access tokens of Keycloak or another OAuth2 server, extend
`JwtBearerAuthentication` (extra `snakeboot[oauth2]`) and add the table `[oauth2]`, like Spring Boot's resource
server. It fetches the issuer's public keys from `jwks_uri` and caches them, and accepts a token only when the
signature, the issuer, the audience and the expiry are right; its `sub` is the principal.

```python
class PlayerTokens(JwtBearerAuthentication):
    """The access tokens that Keycloak gives the platform's players."""
```

```toml
[oauth2]
issuer_uri = "http://localhost:8180/realms/kareldegames"   # the `iss` of the tokens
jwks_uri = "http://keycloak:8080/realms/kareldegames/protocol/openid-connect/certs"
audience = "tictactoe"                                     # the `aud` the tokens must hold
```

**What runs beside the requests.** Django knows no moment "the server starts"; uvicorn does, and says so with ASGI's
`lifespan`, which `asgi_application` answers. Then every `Lifecycle` component starts, like a `SmartLifecycle` bean,
and `ApplicationReadyEvent` goes to the event listeners; when uvicorn stops, they stop. Management commands
(`migrate`), WSGI and the tests start nothing. `python -m myapp run_lifecycle` runs the same lifecycle without a web
server, until SIGTERM: a process that only listens and schedules, like Spring Boot without the web starter.

```python
@application_event_listener
class RegisterOnStartup:
    @event_listener(ApplicationReadyEvent)  # once, when the application has started
    def register(self, _event: ApplicationReadyEvent) -> None: ...
```

**Commands.** A subclass of `CommandLineRunner` that names its command is a command of the application, like a
`CommandLineRunner` bean: a component whose constructor receives use cases and ports, with arguments declared as with
argparse in a classmethod, because they are parsed before the command is built: `--help` answers at once, even when
the command depends on a server that is down. `python -m myapp self_play --games 20` starts the application and runs
it; `python -m myapp help` lists the commands next to the framework's own (`migrate`, `run_lifecycle`), and
`help self_play` prints its help, which is its docstring. Unlike Spring Boot, which runs every runner at each start,
the first argument chooses one, as with Spring Shell's `@Command`.
A `CommandLineError` stops the command with its message and exit status 1; two commands of one name stop the start.

```python
class SelfPlayCommand(CommandLineRunner, command="self_play"):
    """Lets the AI levels play each other and prints how strong each one is."""

    def __init__(self, self_play: SelfPlayUseCase) -> None:
        self._self_play = self_play

    @classmethod
    @override
    def add_arguments(cls, parser: ArgumentParser) -> None:
        parser.add_argument("--games", type=int, default=20, help="Games per pairing.")

    @override
    def run(self, arguments: Namespace) -> None:
        if arguments.games < 1:
            raise CommandLineError("Play at least one game.")
        print(self._self_play.execute(SelfPlayRequestDTO(games=arguments.games)))
```

**Scheduled methods.** `@scheduled` on a method of a component runs it periodically, like `@Scheduled`: with a fixed
rate or a fixed delay, on one thread, each run between fresh database connections. A method that raises is logged and
runs again at its next turn. `[scheduling] auto_startup = false` keeps a process from running them.

```python
@injectable
class AbortExpiredGamesJob:
    @scheduled(fixed_delay=timedelta(seconds=2))
    def abort_expired_games(self) -> None: ...
```

**RabbitMQ.** With the table `[rabbitmq]` (extra `snakeboot[rabbitmq]`, through pika), `@rabbit_listener` makes a
method of a component consume a queue, like `@RabbitListener` with `@QueueBinding`: the durable topic exchange, the
queue and the binding are declared at start-up, the JSON body becomes the pydantic model, `dict` or `bytes` the method
takes, and each listener has a thread and a connection of its own. Returning acknowledges the message;
`RejectAndDontRequeueError` or an unreadable body refuses it for good; another failure is tried three times, a second
apart, then refused, as Spring Boot's `retry.enabled` does. The `RabbitTemplate` sends persistent JSON, confirmed by the
broker. `[rabbitmq.listener] auto_startup = false` keeps a process from consuming. Under uvicorn every worker process
runs its own listeners and scheduled methods, like Spring's `concurrency`: RabbitMQ gives each message to one of them,
and a scheduled method runs once per process.

```python
@injectable
class GameStartedListener:
    def __init__(self, start_game: StartGameUseCase) -> None:
        self._start_game = start_game

    @rabbit_listener(queue="tictactoe.game-started", exchange="games", routing_key="game.tictactoe.started")
    def on_game_started(self, message: GameStartedMessage) -> None: ...  # a pydantic model


# an adapter that sends
self._rabbit.convert_and_send("games", "game.tictactoe.finished", event, message_id=f"{game_id}.finished")
```

```toml
[rabbitmq]
host = "rabbitmq"
port = 5672
username = "guest"          # the password comes from RABBITMQ__PASSWORD
virtual_host = "/"

[rabbitmq.listener]
auto_startup = true
```

## Design rules

* Imitate the basics, not all of Spring: no AOP, no cron, no message broker other than RabbitMQ.
* Fail at start-up, not at the first request: a broken controller, command, listener, root or configuration stops the
  application.
* An application imports snakeboot, not the framework underneath: only the `django*` packages of snakeboot know Django
  or Django Ninja, so another framework means another binding, not other applications.
* Each package knows as little as possible; `uv run lint-imports` enforces it.

## Develop

```bash
uv sync
uv run pre-commit install
uv run pytest            # tests, including the import contracts
uv run ruff check        # Clean Code rules
uv run mypy              # strict
```
