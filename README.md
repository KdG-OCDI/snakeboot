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
| `@application_module_listener`, the event publication registry | Spring Modulith's `@ApplicationModuleListener`, `EventPublicationRegistry` (a transactional outbox) | wireup; `snakeboot[data]` for the registry |
| `@configuration_properties`, `Section`, `application-<profile>.toml` | `@ConfigurationProperties`, profiles | `snakeboot[configuration]` |
| `ServerProperties`, `DatabaseProperties`, `CacheProperties` | `server.*`, `spring.datasource.*`, `spring.data.redis.*` | `snakeboot[configuration]` |
| `snakeboot.boot`: `run`, `python -m myapp serve` | `SpringApplication.run`, auto-configuration, the embedded server | `snakeboot[web]` |
| `@rest_controller`, `@route.get(status=...)`, `@rest_controller_advice`, `@exception_handler` | `@RestController`, `@GetMapping`, `@ResponseStatus`, `@RestControllerAdvice`, `@ExceptionHandler` | `snakeboot[web]` |
| `Principal`, `BearerAuthentication` | `@AuthenticationPrincipal`, a `SecurityFilterChain` bean | `snakeboot[web]` |
| `@roles_allowed`, `Principal.roles`, `SecurityContext` | `@RolesAllowed`, `hasRole`, `SecurityContextHolder` | `snakeboot[web]` |
| `[cors]`, `CorsProperties` | a `CorsRegistry` | `snakeboot[web]` |
| `/health`, `/health/liveness`, `/health/readiness`, `HealthIndicator` | Actuator's health endpoint and probes, `HealthIndicator` | `snakeboot[web]` |
| `/metrics`, `MeterRegistry` | Actuator's `/actuator/prometheus`, Micrometer | `snakeboot[web]` |
| `TraceContext`, `traceparent`, `[logging] format = "ecs"` | Micrometer Tracing, structured logging | `snakeboot[configuration]` |
| `InvalidRequestError`, `RequestProblem` | `MethodArgumentNotValidException` | `snakeboot[web]` |
| `ServerSentEvents`, `ServerSentEvent` | `SseEmitter`, `ServerSentEvent` | `snakeboot[web]` |
| `@entity`, `Id`, `Column`, `Index`, `CreatedDate`, `LastModifiedDate` | `@Entity`, `@Id`, `@Column`, `@Index`, `@CreatedDate`, `@LastModifiedDate` | `snakeboot[data]` |
| `UniqueConstraint`, `ForeignKey`, `BigInt`, `SmallInt` | `@UniqueConstraint`, `@JoinColumn` with `@ForeignKey` and `@OnDelete`, `long`, `short` | `snakeboot[data]` |
| `Version`, `CreatedBy`, `LastModifiedBy`, `OptimisticLockingFailureError` | `@Version`, `@CreatedBy`, `@LastModifiedBy`, `OptimisticLockingFailureException` | `snakeboot[data]` |
| `CrudRepository`, derived queries, `@query`, `@lock`, `PageRequest` | Spring Data's `CrudRepository`, query methods, `@Query`, `@Lock`, `Pageable` | `snakeboot[data]` |
| `migrate`, `make_migration`, `migrations/V1__*.sql` | Flyway | `snakeboot[data]` |
| `Vector` | Spring AI's pgvector store | `snakeboot[data,vector]` |
| `Cache`, `InMemoryCache` | Spring's `Cache`, `RedisCacheManager` | `snakeboot[cache]` for Redis |
| `JwtBearerAuthentication`, `OAuth2Properties` | `spring-boot-starter-oauth2-resource-server` | `snakeboot[oauth2]` |
| `CommandLineRunner`, `CommandLineError` | `CommandLineRunner`, Spring Shell's `@Command` | wireup |
| `Lifecycle`, `ApplicationReadyEvent`, `run_lifecycle` | `SmartLifecycle`, `ApplicationReadyEvent`, an application without the web starter | wireup |
| `@scheduled`, `SchedulingProperties` | `@Scheduled` | `snakeboot[configuration]` |
| `[events]`, `EventsProperties` | `spring.modulith.events.*` | `snakeboot[data]` |
| `@scheduler_lock` | ShedLock's `@SchedulerLock` | `snakeboot[data]` |
| `@rabbit_listener`, `RabbitTemplate`, `RejectAndDontRequeueError` | `@RabbitListener`, `RabbitTemplate`, `AmqpRejectAndDontRequeueException` | `snakeboot[rabbitmq]` |
| `@openapi_definition` | springdoc's `@OpenAPIDefinition` | nothing |
| `@application_test`, `Autowired`, `@test_component`, `TestApplication` | `@SpringBootTest`, `@Autowired`, `@TestComponent` with `@Primary`, `@AutoConfigureTestDatabase`, `TestRestTemplate` | `snakeboot[testing]` |
| `MockComponent`, `SpyComponent`, `when`, `verify` | `@MockitoBean`, `@MockitoSpyBean`, Mockito's `when` and `verify` | `snakeboot[testing]` |
| `signed_in_as`, `RecordingTransactionManager`, `declared_classes` | spring-security-test's `jwt()`, spring-test | `snakeboot[testing]` |
| `PublishedEvents`, `InProcessRabbitTemplate` | Spring's `ApplicationEvents`, Spring Modulith's `PublishedEvents`, Spring AMQP's `TestRabbitTemplate` | `snakeboot[testing]` |
| `PostgreSQLContainer`, `TestEnvironment` | Testcontainers' `PostgreSQLContainer` with `@ServiceConnection`, Flyway in tests, `ddl-auto=validate`, `@ActiveProfiles` | `snakeboot[testing,testcontainers]` |
| `@web_test`, `@application_module_test` | `@WebMvcTest`, Spring Modulith's `@ApplicationModuleTest` | `snakeboot[testing]` |
| `LocalServer`, `eventually`, `AuthorizationServer` | `webEnvironment = RANDOM_PORT`, `@LocalServerPort`, Awaitility, a mock JWT issuer | `snakeboot[testing]`, with `oauth2` for the issuer |

## Install

```bash
uv add "snakeboot[configuration,web,data]"
uv add "snakeboot[configuration,web,data,rabbitmq,oauth2]"   # with RabbitMQ and Keycloak's tokens
uv add --dev "snakeboot[testing,testcontainers]"            # @application_test, on PostgreSQL in Docker too
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

The application writes no settings and no URLs. `snakeboot.boot` reads `application.toml` in the application package,
builds wireup's container from the component scan, and adds what the tables ask for, like Spring Boot's
conditional auto-configuration: SQLAlchemy and the transaction manager of `@transactional` with `[database]`, Redis
with `[cache]`, RabbitMQ with `[rabbitmq]`. An application without a table imports none of those. The REST API lives
under `/api/` (Swagger UI at `/api/docs`), next to `/health` and `/metrics`.

**Where the files live.** The application package is the package of the class marked with `@application_root`, also
when `base_packages` names others: `myapp` in the example above, not `myapp_core`. It is to snakeboot what the root of
the classpath is to Spring Boot. Python compiles nothing apart, so there is no `src/main/resources`: snakeboot reads
its files as package data, and a source checkout and an installed wheel find them alike.

```text
myapp/                              the application package
├── __main__.py                     run(MyApplication)
├── myapp_application.py            @application_root
├── application.toml                every value the application runs with
├── application-local.toml          what the profile "local" changes
└── games/                          a bounded context
    ├── game_record.py              @entity
    └── migrations/
        └── V1__create_games.sql    next to the entities whose tables it creates
```

| File | Where | Spring Boot |
|---|---|---|
| `application.toml`, `application-<profile>.toml` | in the application package | `src/main/resources/application.yml`, `application-<profile>.yml` |
| `migrations/V<n>__<description>.sql` | next to the module of the entities whose tables they change | `src/main/resources/db/migration/` |
| `static/`, `templates/` | reserved in the application package, for when snakeboot serves pages | `src/main/resources/static/`, `templates/` |

The migrations stay with their entities rather than in one place, so each bounded context keeps its own schema;
`make_migration` writes into that directory, and `--into` chooses one when the entities live in several. Moving the
application class into another package moves where `application.toml` is looked for.

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
max_upload_size = "20MB"    # optional: the largest UploadedFile, 1 MiB without it

[database]                  # PostgreSQL; the password comes from DATABASE__PASSWORD
host = "db"
port = 5432
name = "tictactoe"
user = "tictactoe"
```

A service that runs on one machine (a demo, a small tool) keeps its database in one SQLite file instead:
`[database] file = "myapp.sqlite3"`, relative to the directory it starts in. A transaction then takes SQLite's write
lock when it begins, so threads that write at once wait for each other; the migrations are SQL in SQLite's dialect.

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
`@transactional`, or runs in one of its own. A `Version()` field guards against lost updates, like JPA's `@Version`:
saving an entity another transaction changed since it was read raises `OptimisticLockingFailureError` (answer it with
409), and a broken constraint is a `DataIntegrityViolationError`. `CreatedBy()` and `LastModifiedBy()` record who
saved, from the `SecurityContext`, next to `CreatedDate()` and `LastModifiedDate()`.

```python
class GameRecord:
    ...
    updated_by: Annotated[str | None, LastModifiedBy()] = None  # the principal of the call, or None
    version: Annotated[int | None, Version()] = None  # 1 for a new entity, one more per update
```

For a version column that is `NOT NULL`, as in a schema another tool made, declare `Annotated[int, Version()] = 0`:
a new entity still gets 1.

An entity also declares the constraints that keep its rows consistent, with the names the schema gives them, so that
`make_migration` and the schema checks of the tests find nothing to change in a schema that migrations made, an
existing one included. `UniqueConstraint` is JPA's `@UniqueConstraint`, over one column or more; an `Index` with
`unique=True` is a unique index, and with `where` a partial one, which holds only the rows of its condition (on
PostgreSQL a unique index is no unique constraint: declare the one the schema has). `ForeignKey` makes a column refer
to another entity's table, like `@JoinColumn` with `@ForeignKey`, and `on_delete` says what happens to the rows that
refer to a deleted one, like Hibernate's `@OnDelete`; without it the delete is a `DataIntegrityViolationError`.
`deferred=True` checks the key at the commit, as Django declares every foreign key on PostgreSQL. There are no
relationships: a repository loads the rows that refer to another, as in Spring Data JDBC. An `int` is an INTEGER;
`BigInt()` and `SmallInt()` make it a BIGINT or a SMALLINT, like Java's `long` and `short`. The schema checks compare
neither a foreign key's name nor a partial index's condition.

```python
@entity(
    "funding_deadline",
    indexes=(Index("funding_deadline_open_uniq", "funding_call_id", unique=True, where="closed_at IS NULL"),),
    unique_constraints=(UniqueConstraint("funding_deadline_call_stage_uniq", "funding_call_id", "stage"),),
)
@dataclass
class FundingDeadlineRecord:
    id: Annotated[int | None, Id(generated=True)]  # a BIGINT the database numbers
    funding_call_id: Annotated[int, BigInt(), ForeignKey("funding_call.id", on_delete="cascade")]
    stage: Annotated[int, SmallInt()]
    closed_at: datetime | None
```

A repository method whose last parameter is a `PageRequest` returns one page. On PostgreSQL a `Vector(384)` field
(extra `snakeboot[vector]`) holds an embedding for pgvector's similarity search in a `@query`.

**Migrations.** The schema comes from SQL scripts, like Flyway's: `V1__create_tictactoe_game.sql`,
`V2__add_a_winner.sql` in a `migrations` directory next to the entities. `python -m myapp migrate` runs the scripts the
database has not run, in version order, each in a transaction, remembering them with their checksum; a script that
changed after it ran stops it, and on PostgreSQL two processes never migrate at once. `python -m myapp make_migration
"add a winner"` writes the SQL the entities need as the next script, by letting Alembic compare them with the
database. A migration is plain SQL, so it stays valid when the persistence framework changes.

A database whose schema was made before its migrations (by another tool, an earlier version of the application, or
by hand) is baselined, like Flyway's `baseline-on-migrate` with `baseline-version`: `V1__...sql` holds that schema,
and `[database] baseline_version = 1` makes `migrate` record V1 as run, without running it, when it finds tables but
no history of migrations; the later migrations run as usual. A fresh database (a test, a new developer) has no
tables, so it runs V1 and gets the same schema; a database with a history is never baselined. Like Flyway, the history
keeps no checksum for a baselined script, so V1 may still be corrected for the fresh databases. Without the key,
`migrate` runs V1 there as before, and when V1 fails on those tables, its error names `baseline_version`.

**Moving an existing database to snakeboot.** An application that leaves another framework (Django, or snakeboot
before 0.8) keeps its schema and its data where they are: no export, no import.

1. `V1__...sql` is the schema as it is, from `pg_dump --schema-only --no-owner --no-privileges`: the application's own
   tables, not those of the framework it leaves (`django_migrations`, `auth_*`, `django_session`). Leave out psql's
   meta-commands, such as the `\restrict` lines newer versions of `pg_dump` write; its `SET` lines may stay, as
   `migrate` resets the session after every script.
2. The entities describe that schema with its own names: the table, every `Index` and `UniqueConstraint` by the name
   the schema has, a `ForeignKey` with its `on_delete` and `deferred=True` (Django declares every key that way),
   `BigInt()` where a column is a `bigint`. A generated key is a BIGINT, as Django's `BigAutoField` is; a key Django
   made `integer` shows as a change. `make_migration` against a database that ran V1 writes what the entities and the
   schema still disagree on, and the schema check of `PostgreSQLContainer` stops the tests on it, so both find
   nothing once the entities are right.
3. The production configuration sets `[database] baseline_version = 1`: the first `migrate` there records V1 and runs
   only what comes after it.
4. A `V1` from `pg_dump` holds PostgreSQL's own SQL (`GENERATED BY DEFAULT AS IDENTITY`, `::text` casts), which the
   SQLite of `@application_test` refuses, so the tests run with `@application_test(database=PostgreSQLContainer())`
   and `@application_module_test(..., database=PostgreSQLContainer())`. A `@web_test` runs no migrations, so it stays
   on SQLite.
5. Leave the old framework's tables in place until the move has proven itself: while the later migrations only add,
   the previous version still runs on the same database, and going back is deploying it again, without a restore.

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

A listener may inject any component, also a use case that publishes events of its own, as a listener between two
bounded contexts often does: the publisher depends on no listener. Like Spring's `EventListenerMethodProcessor`, the
start-up builds every listener once the container is built and registers it with the publisher, so a listener that
cannot be built stops the start, not the first event.

A `@transactional_event_listener` that fails, or a process that stops before it ran, loses the event. For what must
arrive, an `@application_module_listener` is Spring Modulith's `@ApplicationModuleListener`: it receives the event after
the commit, on a thread of its own, in a transaction of its own, so one module reacts to another without slowing it
down or rolling it back. With `[database]` the publisher's transaction also writes the publication into
`snakeboot_event_publication`, the transactional outbox, and the listener's transaction deletes it. A publication whose
listener failed, or whose process stopped first, is delivered again (after 30 seconds, then longer, ten times at most),
so the event arrives at least once and the listener must bear receiving it twice. What keeps failing waits in the
table, with its last failure, for a person; the gauge `snakeboot_event_publications_incomplete` shows how many wait.
The event is kept as JSON, so it is a dataclass or a Pydantic model; another type stops the start. The table belongs
to the schema once the application has an `@application_module_listener`, as Spring Modulith's `event_publication`
comes with its starter: `make_migration` then writes it into the application's migrations, and the tests check that
they build it; an application without one needs no such table. The optional table `[events]` sets the timing,
like Spring Modulith's `spring.modulith.events.*`; without it, the values below hold.

```toml
[events]
resubmit_every = 30      # seconds, or an ISO 8601 duration: how often the registry is asked what is due
in_flight = "PT5M"       # longer than the slowest listener: a delivery not done by then was lost
retry_after = 30         # after a failure, times the tries so far: 30 s, 1 min, 1.5 min, ...
max_attempts = 10        # then the publication waits in the table for a person
```

```python
@application_event_listener
class InvoiceOnOrderPlaced:
    @application_module_listener(OrderPlaced)
    def create_invoice(self, event: OrderPlaced) -> None: ...
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

**Files.** A parameter of type `UploadedFile` takes a file from a `multipart/form-data` form, like Spring's
`MultipartFile`: the part of the same name fills it, with its `filename`, `content_type`, `size` and `content` (the
bytes), and the endpoint's other parameters outside the path are fields of the same form. A file larger than
`[server] max_upload_size` (a number of bytes, "20MB" or "20MiB"; 1 MiB without it, as Spring Boot's `max-file-size`)
never reaches the endpoint: it is an `UploadTooLargeError`, which an advice answers like any error, and without one
413 `{"code": "upload_too_large", "detail": "..."}`. Swagger UI shows the form with a file picker; a test sends it
with `client.post(url, files={"document": ("form.pdf", content, "application/pdf")}, data={"title": "..."})`.

An endpoint that returns a `FileDownload` answers with a file, like `ResponseEntity<Resource>`: its bytes, its media
type as `Content-Type`, and `Content-Disposition: attachment` (`inline=True` shows it in the browser) with the file
name, in UTF-8 in `filename*` when it has accents and as near as ASCII gets in `filename`, as RFC 6266 advises.
`produces` on the route names the media type in the OpenAPI document, like `@GetMapping(produces = ...)`. An upload
on a GET or DELETE, a list of files, or `produces` on an endpoint that answers JSON stops the start.

```python
@route.post("/{call_id}/application-forms", status=201)
def upload_application_form(self, call_id: str, document: UploadedFile, title: str) -> ApplicationFormDTO:
    return self._forms.store(call_id, title, document.filename, document.content)


@route.get("/{proposal_id}/document", produces=WORD)  # "application/vnd.openxmlformats-...document"
def download_proposal(self, proposal_id: str) -> FileDownload:
    proposal = self._proposals.render(proposal_id)
    return FileDownload(proposal.content, WORD, filename=f"{proposal.title}.docx")  # "Begroting café.docx"
```

**Authentication.** An adapter that extends `BearerAuthentication` is a component of the container, like a
`SecurityFilterChain` bean: its constructor receives sections and ports by type. With one in the component scan, every
endpoint needs `Authorization: Bearer <token>`, the OpenAPI document says so, and a parameter of type `Principal`
receives whom the token belongs to, like `@AuthenticationPrincipal`. `/health` stays open; an endpoint opts out with
`public=True`. A refused token answers 401 `{"detail": "Unauthorized"}`. `authenticate` returns the caller's id, or a
`Principal` with the roles the token grants; `@roles_allowed` on an endpoint or a whole controller lets in only a caller
with one of its roles, like `@RolesAllowed`, and answers anybody else 403 `{"detail": "Forbidden"}`. While an endpoint
runs, its caller is signed in to the `SecurityContext`, like Spring's `SecurityContextHolder`.

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


@route.delete("/{workshop_id}", status=204)
@roles_allowed("organizer")
def cancel(self, workshop_id: str) -> None: ...
```

**Tokens of an authorization server.** For the JWT access tokens of Keycloak or another OAuth2 server, extend
`JwtBearerAuthentication` (extra `snakeboot[oauth2]`) and add the table `[oauth2]` (`issuer_uri`, `jwks_uri`,
`audience`), like Spring Boot's resource server. It fetches the issuer's public keys and caches them, and accepts a
token only when the signature, the issuer, the audience and the expiry are right; its `sub` is the principal, and
its roles are Keycloak's realm roles, its client roles for the audience, and a plain `roles` claim (override
`roles_of` for another authorization server).

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
`[scheduling] auto_startup = false` keeps a process from running them. Every replica runs its own scheduler;
`@scheduler_lock`, like ShedLock's `@SchedulerLock`, lets the replica that takes the lock run a turn and the others
skip it. The lock is a row of `snakeboot_scheduler_lock` in the database, held for at most `at_most_for` (the lock of
a process that died frees itself) and at least `at_least_for`. Like ShedLock's `shedlock`, the table belongs to the
schema once a method has `@scheduler_lock`: `make_migration` then writes it, and an application without one needs
none.

```python
@scheduled(fixed_rate=timedelta(hours=1))
@scheduler_lock("hourly-report", at_most_for=timedelta(minutes=50), at_least_for=timedelta(minutes=5))
def send_hourly_report(self) -> None: ...
```

**RabbitMQ.** With the table `[rabbitmq]` (extra `snakeboot[rabbitmq]`, through pika), `@rabbit_listener` makes a
method of a component consume a queue, like `@RabbitListener` with `@QueueBinding`: the durable topic exchange, the
queue and the binding are declared at start-up, the JSON body becomes the pydantic model, `dict` or `bytes` the method
takes, and each listener has a thread and a connection of its own. Returning acknowledges the message;
`RejectAndDontRequeueError` or an unreadable body refuses it for good at once; another failure, such as a database
that is down, is tried again as `[rabbitmq.listener.retry]` says, like `spring.rabbitmq.listener.simple.retry.*`
(without the table three times, a second apart), then refused. RabbitMQ drops a refused message, unless the listener
has `dead_letter=True`: then it moves to the durable queue `<queue>.dead-letter`, as Spring's
`RejectAndDontRequeueRecoverer` does with a queue's `x-dead-letter-exchange`, to be looked at or moved back by hand,
with RabbitMQ's `x-death` header saying where and why. The `RabbitTemplate` sends persistent JSON, confirmed by the
broker. `[rabbitmq.listener] auto_startup = false` keeps a process from consuming.

```python
@injectable
class GameStartedListener:
    @rabbit_listener(
        queue="tictactoe.game-started",
        exchange="games",
        routing_key="game.tictactoe.started",
        dead_letter=True,  # what it refuses is kept in tictactoe.game-started.dead-letter
    )
    def on_game_started(self, message: GameStartedMessage) -> None: ...  # a pydantic model
```

```toml
[rabbitmq.listener.retry]   # optional, all four keys
max_attempts = 6            # then the message is refused for good
initial_interval = 2        # seconds, or "PT2S"; then 4, 8, 16 and 30 s: a database may be down for a minute
multiplier = 2
max_interval = 30
```

The listener holds the message while it waits (prefetch 1), so the messages behind it wait too, and its connection
keeps answering the broker's heartbeats. Before any listener consumes, the start-up declares every exchange, queue
and binding, and a declaration RabbitMQ refuses stops it (`AmqpDeclarationError`). RabbitMQ does not change the
arguments of a queue that exists, so turning `dead_letter` on, or off, for a queue that is there already stops the
start-up with RabbitMQ's `PRECONDITION_FAILED` and two ways to migrate the queue:

* Delete it while it is empty, and start the new version, which declares it anew: `rabbitmqctl delete_queue
  tictactoe.game-started --if-empty`, or the management UI. A message sent in between reaches no queue, so do it while
  the senders are quiet.
* Or keep it, leave `dead_letter` out, and give it the dead-letter queue through a policy, which RabbitMQ applies to
  a queue that exists; declare `tictactoe.game-started.dead-letter` too (the refused start-up did). A queue follows one
  policy, the one with the highest priority, so add these keys to a policy that applies already.

```bash
rabbitmqctl set_policy tictactoe.game-started.dead-letter '^tictactoe\.game-started$' \
  '{"dead-letter-exchange": "", "dead-letter-routing-key": "tictactoe.game-started.dead-letter"}' --apply-to queues
```

**Health and metrics.** Like Spring Boot's actuator, the server answers beside the API, without a token:
`/health/liveness` is UP while the process answers (Kubernetes's livenessProbe); `/health` and `/health/readiness`
check every `HealthIndicator` and answer 503 when one part is DOWN (the readinessProbe). The bindings bring the checks
of the database, Redis and RabbitMQ; an adapter that extends `HealthIndicator` adds its own. `/metrics` answers
Prometheus with every meter of the `MeterRegistry`, which times every call as `http_server_requests_seconds` by
method, route and status; an adapter injects it for counters, timers and gauges of its own. The metrics are those of
one process: scale with replicas of one worker.

```python
class PaymentGatewayHealthIndicator(HealthIndicator):
    @override
    def check(self) -> None:
        self._gateway.ping()  # raises when the gateway is down


self._meters.counter("games_started", "Games started", tags={"game": "tictactoe"}).increment()
```

**Traces and logs.** Every call runs in a span of the caller's trace when it sends a W3C `traceparent`, or of a new
trace; so does every message a `@rabbit_listener` receives, every scheduled run, and every
`@application_module_listener`. The `RabbitTemplate` sends the `traceparent` along, and every log line carries the trace
id, so one request can be followed through every service. `[logging] format = "ecs"` writes every line as JSON in the
Elastic Common Schema, for Loki or Elasticsearch, like Spring Boot's structured logging.

**CORS.** With `[cors]`, the pages of the origins it names may call the API from a browser, like a `CorsRegistry`;
without it, none of another origin may. `*` with `allow_credentials = true` stops the start, as in Spring.

```toml
[cors]
allowed_origins = ["https://games.example.com"]
allowed_methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]
allowed_headers = ["Authorization", "Content-Type"]
allow_credentials = false
```

**A cache.** An adapter asks for `Cache` by type: values JSON can hold, kept by key for a while. With `[cache]
redis_url = "redis://redis:6379/1"` (extra `snakeboot[cache]`) it is Redis; a test gives an `InMemoryCache`.

```python
self._cache.put(question, {"text": answer, "sources": sources}, time_to_live=timedelta(hours=1))
```

**Tests.** `@application_test` is `@SpringBootTest`: every test it marks gets the application, started anew, and the
components it asks for by type. A test component replaces a component in every test, like a `@TestComponent` with
`@Primary`; a `MockComponent` replaces one for a single test, like `@MockitoBean`.

```python
# tests/doubles/fixed_clock.py
@test_component(replaces=ClockPort)  # found in the source; built anew for every test
class FixedClock(ClockPort):
    def __init__(self, now: datetime = NOW) -> None: ...
    def advance(self, duration: timedelta) -> None: ...


# tests/test_orders.py
@application_test
class TestOrders:
    client: Autowired[RestClient]  # @Autowired: calls the REST API in this process
    clock: Autowired[FixedClock]  # a test component, by its own type
    payments: MockComponent[PaymentPort]  # @MockitoBean; SpyComponent[...] is @MockitoSpyBean

    def test_an_order_waits_while_the_payments_are_down(self) -> None:
        when(self.payments.charge).then_raise(ConnectionError("down"))

        response = self.client.post(
            "/api/orders", json={"item": "book"}, headers=signed_in_as("ann", roles={"customer"})
        )

        assert response.json()["status"] == "WAITING"
        verify(self.payments.charge).called_once_with("book")
```

There is nothing to configure: no conftest.py, no fixtures. pytest loads snakeboot's plugin by itself, and the plugin
reads the project's source, as Spring Boot searches for the `@SpringBootConfiguration`: the one `@application_root` is
the application, every `@test_component` a test component. `@application_test(application=...)` names the application
where the source holds more than one. On a function, the parameters are filled instead of fields, and its other
parameters stay pytest's fixtures. Every test gets an application of its own, with fresh test components and mocks,
so nothing needs to be emptied between tests, where Spring keeps one context.

* `signed_in_as("ann", roles={"customer"})` are the headers of a call by ann, like spring-security-test's `jwt()`: the
  application of a test accepts them next to its own tokens, and its own `@roles_allowed` decide. Keycloak never runs.
* `when(...)` and `verify(...)` are Mockito's, in the types of the port: `then_return("no")` where the port returns a
  `bool`, or `called_once_with` with an argument of the wrong type, is refused by the type checker.
* `@application_test(profile="test", properties={"scheduling.auto_startup": False})` activates a profile, like
  `@ActiveProfiles`, and sets properties that win over the files and the environment, like
  `@SpringBootTest(properties = ...)`.
* An unknown type, a test component without a constructor without arguments or two test components for one component
  stop the test before it runs.

A test component nested in a test class holds for that class only, like a static nested `@TestConfiguration`: a
hand-written fake for a few tests, where the project's own test component, or the application's component, holds for
the others. A class nested in it sees it too, as a JUnit `@Nested` class does, and for one component the innermost
wins. Beside a `MockComponent` of the same component in the same class, it stops the test.

```python
@application_test
class TestWithARepositoryThatLosesTheUpdate:
    @test_component(replaces=AuctionRepositoryPort)  # for the tests of this class only
    class RepositoryThatLosesTheUpdate:
        def get(self, auction_id: AuctionId) -> Auction:
            return an_auction()

        def save(self, auction: Auction) -> None:
            raise AuctionChangedMeanwhileError("Another bid came in meanwhile.")

    client: Autowired[RestClient]

    def test_a_lost_update_answers_409(self) -> None:
        response = self.client.post(f"/api/auctions/{AUCTION}/bids", json={"amount": 120}, headers=signed_in_as(...))

        assert response.status_code == 409
```

The infrastructure of a test is snakeboot's own, so nothing outside the test runs:

* **The database** is a fresh SQLite in memory, built by the application's own migrations, like Flyway's on H2 in
  Spring Boot's tests: the scripts `migrate` runs, all of them, also in a module slice (a web slice runs none, below).
  They run once per process, and every test gets a copy of the result. First the migrated schema is compared with the
  entities, like Hibernate's `ddl-auto=validate`: a table, column, NOT NULL or index the migrations lack stops the
  tests, with the SQL `make_migration` would still write. SQLite takes the type names of a migration as they come and
  does not show every unique constraint or foreign key, so those are compared on PostgreSQL; its foreign keys are on,
  so a delete cascades or is refused as in production. An application without migrations gets the tables of its
  entities.
* What SQLite cannot run or show (a migration in PostgreSQL's own SQL, a `Vector`'s similarity search, `@lock`,
  PostgreSQL's own SQL in an `@query`) runs on PostgreSQL, in a container, like Testcontainers' `PostgreSQLContainer`
  with `@ServiceConnection`: `@application_test(database=PostgreSQLContainer("pgvector/pgvector:pg17"))`. A migration
  that SQLite rejects stops the tests on SQLite with its name. On PostgreSQL the migrations build the schema once per
  process too, and every test gets a copy of it (`CREATE DATABASE ... TEMPLATE`, a tenth of a second); the comparison
  with the entities includes the types, the unique constraints and the foreign keys. It needs Docker and
  `snakeboot[testcontainers]`.
* **The events**: `Autowired[PublishedEvents]` holds every event the application published during the test, like
  Spring's `ApplicationEvents` and Spring Modulith's `PublishedEvents`: `[closed] = events.of_type(AuctionClosed)`.
* **The broker**: with `[rabbitmq]`, the `RabbitTemplate` is an `InProcessRabbitTemplate`, like Spring AMQP's
  `TestRabbitTemplate`. It keeps every message in `sent` and hands it, as the same JSON, to the application's own
  `@rabbit_listener` methods whose queue a topic exchange would route it to, once the sender's transaction committed;
  what a listener refuses lands in `refused` after one attempt, without the retries, and never fails the sender.
  What a listener with `dead_letter=True` refuses is in `dead_lettered` too, as its dead-letter queue would keep it.
* **The cache** is an `InMemoryCache`; the `@application_module_listener` methods run on the caller's thread, so what
  they did is there when the call that published returns.

```python
@application_test(database=PostgreSQLContainer())
def test_an_auction_closes_with_its_winner(
    client: Autowired[RestClient], events: Autowired[PublishedEvents], rabbit: Autowired[InProcessRabbitTemplate]
) -> None:
    close(client, auction_id)

    [closed] = events.of_type(AuctionClosed)
    assert closed.winner == "bob"
    assert rabbit.sent[0].json() == {"auction_id": auction_id, "recipient": "bob"}
```

A slice starts part of the application, as Spring Boot's test slices and Spring Modulith do:

* `@web_test` is `@WebMvcTest`: the modules that declare a `@rest_controller`, a `@rest_controller_advice` or the
  API's `BearerAuthentication`, and nothing else; a controller's use cases are `MockComponent`s, and so is a
  repository that an advice or the authentication asks. Its `@roles_allowed`, its advices and `signed_in_as` work as in
  the whole application. Like `@WebMvcTest`, which configures no datasource, it runs no migrations: its SQLite in
  memory has only the tables of the entities in the slice (snakeboot's own), made from the entities, so a migration
  in PostgreSQL's own SQL does not stop it.
* `@application_module_test("auction_house.invoicing")` is `@ApplicationModuleTest`: those packages and the modules
  right in the application's package (its root and its tokens), without the other bounded contexts; whatever they are
  used for is a `MockComponent`. It runs every migration of the application, as `migrate` does, so snakeboot's own
  tables and those another context's migrations change are there; `database=PostgreSQLContainer()` runs them on
  PostgreSQL.

```python
@web_test
class TestAuctionRestController:
    client: Autowired[RestClient]
    place_bid: MockComponent[PlaceBidUseCase]

    def test_a_bid_that_is_too_low_answers_409(self) -> None:
        when(self.place_bid.execute).then_raise(BidTooLowError("The highest bid is 150."))

        response = self.client.post(f"/api/auctions/{AUCTION}/bids", json={"amount": 120}, headers=signed_in_as(...))

        assert (response.status_code, response.json()["code"]) == (409, "bid_too_low")
```

A dependency that nobody gave stops the test and names it, as Spring's context does that does not load: `Parameter
'open_auction' of AuctionRestController has an unknown dependency on OpenAuctionUseCase`. A module that declares a
section stays in every slice, since the configuration reads every table: give sections a module of their own. And
what a slice leaves out stays out, even where a module it holds imports it: wireup registers a module's imports too,
so snakeboot leaves out every member defined in a module the scan excludes.

Three more things a test may ask for:

* `Autowired[LocalServer]` serves the application over HTTP on a free port, like
  `@SpringBootTest(webEnvironment = RANDOM_PORT)` with `@LocalServerPort`: `server.url`, and `server.client()` calls it
  over the network, with the lifecycle running. For what the client in the test's process cannot show: a browser,
  CORS, a stream of server-sent events as it arrives.
* With `[oauth2]`, `Autowired[AuthorizationServer]` (`snakeboot.oauth2.testing`) stands in for Keycloak: it signs real
  JWTs, `keycloak.signed_in("carol", realm_access={"roles": ["auctioneer"]})`, which the application's own
  `JwtBearerAuthentication` checks and its own `roles_of` maps, as in production; `exp=` or `iss=` shows what it
  refuses. `signed_in_as` keeps working beside it.
* `eventually(check, within=5)` tries a check until it holds, like Awaitility, for code on a thread of its own: the
  scheduler, listeners with the lifecycle running, a `LocalServer`.

Underneath, `TestApplication` starts the application as it runs, from its `application.toml`, like `@SpringBootTest`
with `@AutoConfigureTestDatabase`, with that infrastructure: `overrides` replace components with doubles, or with
`SPY` wrap them in a spy before anything that depends on them is built (`overrides={PaymentPort: SPY}`, what a
`SpyComponent` does), `environment=TestEnvironment(profile=..., properties=..., database=...)` says where it runs and
`only=WebSlice()` or `only=ModuleSlice(("...",))` how much of it. `client()` calls the REST API in the same process,
like `TestRestTemplate`; used as a context manager, the lifecycle runs around it. A test may use it directly:

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
  and only `snakeboot.pytest_testing` knows pytest, so another framework means another binding, not other applications.
* Each package knows as little as possible; `uv run lint-imports` enforces it.

## Develop

```bash
uv sync
uv run pre-commit install
uv run pytest            # tests, including the import contracts
uv run ruff check        # Clean Code rules
uv run mypy              # strict
```

The PostgreSQL tests (migrations, JSONB, pgvector, `SKIP LOCKED`, the scheduler locks) run when `SNAKEBOOT_TEST_POSTGRESQL_URL` names a database they may
fill and empty:

```bash
docker run -d --rm -p 55432:5432 -e POSTGRES_PASSWORD=snakeboot pgvector/pgvector:pg17
SNAKEBOOT_TEST_POSTGRESQL_URL=postgresql+psycopg://postgres:snakeboot@localhost:55432/postgres uv run pytest
```

The RabbitMQ tests (dead letters, queue arguments, heartbeats during a back-off) run when `SNAKEBOOT_TEST_RABBITMQ_URL`
names a broker on which they may declare and delete queues:

```bash
docker run -d --rm -p 55672:5672 rabbitmq:4-management
SNAKEBOOT_TEST_RABBITMQ_URL=amqp://guest:guest@localhost:55672/%2F uv run pytest
```
