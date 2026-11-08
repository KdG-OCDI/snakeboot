<p align="center">
  <img src="https://raw.githubusercontent.com/KdG-OCDI/snakeboot/main/docs/logo.png" alt="snakeboot: a snake coiled into a boot" width="320">
</p>

# snakeboot

Spring Boot ergonomics for hexagonal Python applications, wired by [wireup](https://github.com/maldoinc/wireup),
with FastAPI, SQLAlchemy and Alembic underneath.

snakeboot imitates the basics of Spring Boot, not Spring itself. Each part is a handful of small
classes you can read in an afternoon, and none of them knows anything about your domain.

An application speaks snakeboot, never the frameworks underneath: its entry points, controllers, entities,
repositories, migrations, commands, listeners, configuration and tests import nothing of FastAPI, Starlette,
SQLAlchemy or Alembic. snakeboot binds them, so another framework means another binding, not other applications.

| snakeboot | Spring Boot | Needs |
|---|---|---|
| `@transactional`, `after_commit` | `@Transactional`, `@TransactionalEventListener(AFTER_COMMIT)` | nothing |
| `@application_root`, `ComponentScan` | `@SpringBootApplication`, `@ComponentScan` | nothing |
| `ApplicationEventPublisher`, `@event_listener`, `@transactional_event_listener` | the same names | wireup |
| `@configuration_properties`, `Section`, `application-<profile>.toml` | `@ConfigurationProperties`, profiles | `snakeboot[configuration]` |
| `ServerProperties`, `DatabaseProperties`, `CacheProperties` | `server.*`, `spring.datasource.*`, `spring.data.redis.*` | `snakeboot[configuration]` |
| `snakeboot.boot`: `run`, `python -m myapp serve` | `SpringApplication.run`, auto-configuration, the embedded server | `snakeboot[web]` |
| `@rest_controller`, `@route.get(status=...)`, `@rest_controller_advice`, `@exception_handler` | `@RestController`, `@GetMapping`, `@ResponseStatus`, `@RestControllerAdvice`, `@ExceptionHandler` | `snakeboot[web]` |
| `Principal`, `BearerAuthentication` | `@AuthenticationPrincipal`, a `SecurityFilterChain` bean | `snakeboot[web]` |
| `InvalidRequestError`, `RequestProblem` | `MethodArgumentNotValidException` | `snakeboot[web]` |
| `ServerSentEvents`, `ServerSentEvent` | `SseEmitter`, `ServerSentEvent` | `snakeboot[web]` |
| `@entity`, `Id`, `Column`, `Index`, `CreatedDate`, `LastModifiedDate` | `@Entity`, `@Id`, `@Column`, `@Index`, `@CreatedDate`, `@LastModifiedDate` | `snakeboot[data]` |
| `CrudRepository`, derived queries, `@query`, `@lock`, `PageRequest` | Spring Data's `CrudRepository`, query methods, `@Query`, `@Lock`, `Pageable` | `snakeboot[data]` |
| `migrate`, `make_migration`, `migrations/V1__*.sql` | Flyway | `snakeboot[data]` |
| `Vector` | Spring AI's pgvector store | `snakeboot[data,vector]` |
| `Cache`, `InMemoryCache` | Spring's `Cache`, `RedisCacheManager` | `snakeboot[cache]` for Redis |
| `JwtBearerAuthentication`, `OAuth2Properties` | `spring-boot-starter-oauth2-resource-server` | `snakeboot[oauth2]` |
| `CommandLineRunner`, `CommandLineError` | `CommandLineRunner`, Spring Shell's `@Command` | wireup |
| `Lifecycle`, `ApplicationReadyEvent`, `run_lifecycle` | `SmartLifecycle`, `ApplicationReadyEvent`, an application without the web starter | wireup |
| `@scheduled`, `SchedulingProperties` | `@Scheduled` | `snakeboot[configuration]` |
| `@rabbit_listener`, `RabbitTemplate`, `RejectAndDontRequeueError` | `@RabbitListener`, `RabbitTemplate`, `AmqpRejectAndDontRequeueException` | `snakeboot[rabbitmq]` |
| `@openapi_definition` | springdoc's `@OpenAPIDefinition` | nothing |
| `TestApplication`, `RecordingTransactionManager`, `declared_classes` | `@SpringBootTest`, `@AutoConfigureTestDatabase`, `TestRestTemplate`, spring-test | `snakeboot[testing]` |

## Install

```bash
uv add "snakeboot[configuration,web,data]"
uv add "snakeboot[configuration,web,data,rabbitmq,oauth2]"   # with RabbitMQ and Keycloak's tokens
```

## A tour

**The application.** A class marked with `@application_root`, like `@SpringBootApplication`, is the application.
Its component scan decides what goes into the container: the package of the class, or the packages `base_packages`
names. The scan skips the server entry points (`wsgi.py`, `asgi.py`) and adds the components snakeboot provides
itself (the event publisher, the lifecycle, the scheduler, `serve`, `run_lifecycle`). `run`, from
`snakeboot.boot`, runs a command, like `SpringApplication.run`: `python -m myapp serve` starts the web server where
`[server]` says, as Spring Boot starts its embedded server, so the application holds no server entry point.
`snakeboot.boot` is the one place that names the frameworks underneath.

```python
# myapp/myapp_application.py
@openapi_definition(title="My service", version="1.0.0")
@application_root(base_packages=("myapp_core",))
class MyApplication: ...


# myapp/__main__.py: python -m myapp serve, python -m myapp migrate, python -m myapp help
from snakeboot.boot import run

run(MyApplication)
```

The application writes no settings and no URLs. `snakeboot.boot` reads `application.toml` next to the application
class, builds wireup's container from the component scan, and adds what the tables ask for, like Spring Boot's
conditional auto-configuration: SQLAlchemy and the transaction manager of `@transactional` with `[database]`, Redis
with `[cache]`, RabbitMQ with `[rabbitmq]`. An application without a table imports none of those. The REST API lives
under `/api/` (Swagger UI at `/api/docs`), next to `/health`.

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

```toml
[server]
host = "0.0.0.0"            # where `serve` listens: every interface, as in a container
port = 8000
workers = 2                 # processes, each with its own listeners and scheduled methods
debug = false
allowed_hosts = ["*"]       # or "games.example.com", "*.example.com"
log_level = "INFO"

[database]                  # PostgreSQL; the password comes from DATABASE__PASSWORD
host = "db"
port = 5432
name = "tictactoe"
user = "tictactoe"
```

The values come from three places, a later one overriding an earlier one key by key:

| Source | Holds | Spring Boot |
|---|---|---|
| `application.toml` in the package | every value the application runs with in production | `application.yml` |
| `application-<profile>.toml`, when `SNAKEBOOT_PROFILE` names one | what differs on a developer machine, say | `application-local.yml`, `SPRING_PROFILES_ACTIVE` |
| environment variables `SECTION__KEY__SUBKEY` | secrets and addresses of one deployment | relaxed binding |

Nothing else is read: no `.env` file, no default in code, no command line. The start stops when a model does
not extend `Section`, changes its `model_config` or has a default; when a file or a value is missing; when a key
or a table is unknown (a typo in `application.toml` or in `CHATBOT__LLM__MODLE`). Outside an application,
`load_configuration(ChatbotProperties, package="myapp")` reads the sections it is given.

**Entities and repositories.** An entity is a plain dataclass that a table keeps, like a JPA `@Entity`; a repository is
an interface, a Protocol that extends `CrudRepository`, which snakeboot implements when its module is imported, like
Spring Data. Its methods are derived from their names (`find_by`, `count_by`, `exists_by`, `delete_by`, conditions
joined by `_and_` and `_or_`, keywords such as `less_than_equal`, `in`, `is_null` and `containing`, then `order_by`);
the return annotation says what a method returns. `@query` writes the SQL itself, `@lock` locks the rows read. A name
snakeboot cannot read, a field the entity lacks or a parameter too many stops the start. The implementation is the
component of the interface, so an adapter asks for the interface by type and maps its records to the domain.

```python
@entity("tictactoe_game", indexes=(Index("tictactoe_game_waiting_idx", "status", "join_deadline"),))
@dataclass
class GameRecord:
    game_id: Annotated[UUID, Id()]  # Id(generated=True) for a number the database gives
    status: Annotated[str, Column(length=16)]
    board: list[str]  # list, dict and Any are JSON; Json() makes any field JSON
    join_deadline: datetime | None  # with its time zone; None is an empty column
    updated_at: Annotated[datetime | None, LastModifiedDate()] = None


class GameRecords(CrudRepository[GameRecord, UUID], Protocol):
    @lock(LockMode.PESSIMISTIC_WRITE)
    def find_by_status_and_join_deadline_less_than_equal(self, status: str, deadline: datetime) -> list[GameRecord]: ...

    def find_first_by_order_by_updated_at_desc(self) -> GameRecord | None: ...

    def count_by_status(self, status: str) -> int: ...

    @query("SELECT status, COUNT(*) AS games FROM tictactoe_game GROUP BY status")
    def games_per_status(self) -> list[StatusCount]: ...  # any class made from the columns by name
```

`save` inserts or updates by identifier, like Spring Data's; every call joins the transaction of the running
`@transactional`, or runs in one of its own. A last parameter of type `PageRequest` returns one page. On PostgreSQL a
`Vector(384)` field (extra `snakeboot[vector]`) holds an embedding for pgvector's similarity search in a `@query`.

**Migrations.** The schema comes from SQL scripts, like Flyway's: `V1__create_tictactoe_game.sql`,
`V2__add_a_winner.sql` in a `migrations` directory next to the entities. `python -m myapp migrate` runs the scripts the
database has not run, in version order, each in a transaction, remembering them with their checksum; a script that
changed after it ran stops it, and on PostgreSQL two processes never migrate at once. `python -m myapp make_migration
"add a winner"` writes the SQL the entities need as the next script, by letting Alembic compare them with the
database. A migration is plain SQL, so it stays valid when the persistence framework changes.

**Transactions.** A use case declares its boundary; snakeboot chooses the technology, SQLAlchemy's session when the
application has `[database]`. A nested `@transactional` call is a savepoint; `after_commit` waits for the outermost
commit and is dropped by a rollback.

```python
@injectable
class CancelRegistrationUseCase:
    @transactional
    def execute(self, request: CancelRegistrationRequestDTO) -> None:
        workshop = self._workshops.get(...)
        workshop.cancel_registration(...)
        self._workshops.save(workshop)
        self._events.publish_all(workshop.pull_events())
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
the component scan, the same modules that fill the container, and `snakeboot.fastapi_web` publishes their routes.
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
        return error_answer(error)  # {"code": "invalid_request", "detail": "body.title: Field required"}
```

**Server-sent events.** An endpoint that returns `ServerSentEvents` streams, like one that returns Spring's
`SseEmitter`: it is served as `text/event-stream`, uncached and unbuffered, and a watching client holds no thread.
`ServerSentEvents.watching` covers what most streams do: it reads a value once in the call (so an unknown id answers
404 as usual), then every `every`, and sends it whenever it changed, until `until` holds. A silence of 15 seconds gets
a comment that keeps proxies open, and a stream ends after 30 minutes, when the browser's `EventSource` reconnects.
Each read runs on the server's thread pool, in a transaction of its own.

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
`public=True`. A refused token answers 401 `{"detail": "Unauthorized"}`.

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
`JwtBearerAuthentication` (extra `snakeboot[oauth2]`) and add the table `[oauth2]` (`issuer_uri`, `jwks_uri`,
`audience`), like Spring Boot's resource server. It fetches the issuer's public keys and caches them, and accepts a
token only when the signature, the issuer, the audience and the expiry are right; its `sub` is the principal.

**What runs beside the requests.** When `serve` starts the server, and in each of its processes, every `Lifecycle`
component starts, like a `SmartLifecycle` bean, and
`ApplicationReadyEvent` goes to the event listeners. Commands and tests start nothing. `python -m myapp run_lifecycle`
runs the same lifecycle without a web server, until SIGTERM: a process that only listens and schedules, like Spring
Boot without the web starter.

**Commands.** A subclass of `CommandLineRunner` that names its command is a command of the application, like a
`CommandLineRunner` bean: a component whose constructor receives use cases and ports, with arguments declared as with
argparse in a classmethod, because they are parsed before the command is built: `--help` answers at once, even when
the command depends on a server that is down. `python -m myapp self_play --games 20` runs it; `python -m myapp help`
lists the application's commands and snakeboot's own (`serve`, `run_lifecycle`, `migrate`, `make_migration`). A
`CommandLineError` stops the command with its message and exit status 1; two commands of one name stop the start.

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
        print(self._self_play.execute(SelfPlayRequestDTO(games=arguments.games)))
```

**Scheduled methods.** `@scheduled` on a method of a component runs it periodically, like `@Scheduled`: with a fixed
rate or a fixed delay, on one thread. A method that raises is logged and runs again at its next turn.
`[scheduling] auto_startup = false` keeps a process from running them.

**RabbitMQ.** With the table `[rabbitmq]` (extra `snakeboot[rabbitmq]`, through pika), `@rabbit_listener` makes a
method of a component consume a queue, like `@RabbitListener` with `@QueueBinding`: the durable topic exchange, the
queue and the binding are declared at start-up, the JSON body becomes the pydantic model, `dict` or `bytes` the method
takes, and each listener has a thread and a connection of its own. Returning acknowledges the message;
`RejectAndDontRequeueError` or an unreadable body refuses it for good; another failure is tried three times, then
refused. The `RabbitTemplate` sends persistent JSON, confirmed by the broker. `[rabbitmq.listener] auto_startup =
false` keeps a process from consuming.

```python
@injectable
class GameStartedListener:
    @rabbit_listener(queue="tictactoe.game-started", exchange="games", routing_key="game.tictactoe.started")
    def on_game_started(self, message: GameStartedMessage) -> None: ...  # a pydantic model
```

**A cache.** An adapter asks for `Cache` by type: values JSON can hold, kept by key for a while. With `[cache]
redis_url = "redis://redis:6379/1"` (extra `snakeboot[cache]`) it is Redis; a test gives an `InMemoryCache`.

```python
self._cache.put(question, {"text": answer, "sources": sources}, time_to_live=timedelta(hours=1))
```

**Tests.** `TestApplication` starts the application as it runs, from its `application.toml`, with two differences, like
`@SpringBootTest` with `@AutoConfigureTestDatabase`: `overrides` replace components with doubles, and the database is a
fresh SQLite in memory whose tables come from the entities. `client()` calls the REST API in the same process, like
`TestRestTemplate`; used as a context manager, the lifecycle runs around it.

```python
def test_a_started_game_can_be_read() -> None:
    with TestApplication.start(TictactoeApplication, overrides={GamePlatformPort: FakePlatform()}) as app:
        client = app.client()
        created = client.post("/api/tictactoe/games", json={"players": ["ann", "bob"]})

        assert client.get(f"/api/tictactoe/games/{created.json()['game_id']}").status_code == 200
        assert app.get(GameRecords).count() == 1
```

`RecordingTransactionManager` runs `@transactional` use cases without a database, and `declared_classes` lets an
architecture test compare what the source declares with what the component scan found.

## Design rules

* Imitate the basics, not all of Spring: no AOP, no cron, no message broker other than RabbitMQ.
* Fail at start-up, not at the first request: a broken controller, repository, command, listener, root or
  configuration stops the application.
* An application imports snakeboot, never the framework underneath: only `snakeboot.fastapi_web`,
  `snakeboot.sqlalchemy_data`, `snakeboot.redis_cache` and `snakeboot.boot` know FastAPI, SQLAlchemy, Alembic or Redis,
  so another framework means another binding, not other applications.
* Each package knows as little as possible; `uv run lint-imports` enforces it.

## Develop

```bash
uv sync
uv run pre-commit install
uv run pytest            # tests, including the import contracts
uv run ruff check        # Clean Code rules
uv run mypy              # strict
```

The PostgreSQL tests (migrations, JSONB, pgvector) run when `SNAKEBOOT_TEST_POSTGRESQL_URL` names a database they may
fill and empty:

```bash
docker run -d --rm -p 55432:5432 -e POSTGRES_PASSWORD=snakeboot pgvector/pgvector:pg17
SNAKEBOOT_TEST_POSTGRESQL_URL=postgresql+psycopg://postgres:snakeboot@localhost:55432/postgres uv run pytest
```
