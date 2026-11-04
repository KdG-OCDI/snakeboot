# snakeboot

Spring Boot ergonomics for hexagonal Python applications built with Django, Django Ninja and
[wireup](https://github.com/maldoinc/wireup).

snakeboot imitates the basics of Spring Boot, not Spring itself. Each part is a handful of small
classes you can read in an afternoon, and none of them knows anything about your domain.

| snakeboot | Spring Boot | Needs |
|---|---|---|
| `@transactional`, `after_commit` | `@Transactional`, `@TransactionalEventListener(AFTER_COMMIT)` | nothing |
| `@application_root`, `ComponentScan` | `@SpringBootApplication`, `@ComponentScan` | nothing |
| `ApplicationEventPublisher`, `@event_listener`, `@transactional_event_listener` | the same names | wireup |
| `@rest_controller`, `@route.get`, `@rest_controller_advice`, `@exception_handler` | `@RestController`, `@GetMapping`, `@RestControllerAdvice`, `@ExceptionHandler` | `snakeboot[ninja]` |
| `DjangoAtomicTransactionManager` | `PlatformTransactionManager` for JDBC | `snakeboot[django]` |
| `@configuration_properties`, `Section`, `load_configuration`, `application-<profile>.toml` | `@ConfigurationProperties`, `@ConfigurationPropertiesScan`, profiles | `snakeboot[configuration]` |
| `DjangoProperties`, `DatabaseProperties`, `CacheProperties` | `server.*`, `spring.datasource.*`, `spring.data.redis.*` | `snakeboot[configuration]` |
| `run`, `wsgi_application`, `django_settings` | `SpringApplication.run`, auto-configuration | `snakeboot[configuration,django]` |
| `DjangoConfigurer` | `WebMvcConfigurer` | `snakeboot[configuration,django]` |
| `BearerAuthentication` | a `SecurityFilterChain` bean | `snakeboot[ninja]` |
| `@openapi_definition` | springdoc's `@OpenAPIDefinition` | nothing |
| `rest_api`, `snakeboot.rest.urls` | the REST API and `/health` of the application | `snakeboot[ninja]` |
| `RecordingTransactionManager`, `declared_classes` | spring-test | nothing |

The transaction, component scan and testing packages import nothing but the standard library,
so the application layer of a hexagonal application can use `@transactional` without importing Django.

## Install

```bash
uv add "snakeboot[configuration,django,ninja]"
```

## A tour

**The application.** A class marked with `@application_root`, like `@SpringBootApplication`, is the application.
Its component scan decides what goes into the container: the package of the class, or the packages `base_packages`
names. The scan skips Django's entry points (`wsgi.py`, `asgi.py`, migrations) and adds the components snakeboot
provides itself (the event publisher). `run` starts it, like `SpringApplication.run`.

```python
# myapp/myapp_application.py
@openapi_definition(title="My service", version="1.0.0")
@application_root(base_packages=("myapp_core",))
class MyApplication: ...


# manage.py and myapp/__main__.py               # myapp/wsgi.py, for gunicorn
run(MyApplication)                               application = wsgi_application(MyApplication)
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
auto-configuration: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` and `LOGGING` from `[django]`; `DATABASES` from
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
the component scan, the same modules that fill the container, and adds their routes to the API. Two endpoints for
the same URL, or two answers for one error, stop the start-up.

```python
@rest_controller("/workshops", tags=["workshops"])
class WorkshopRestController:
    def __init__(self, enrollment: EnrollmentFacadePort) -> None:
        self._enrollment = enrollment

    @route.get("/{workshop_id}", response=WorkshopViewDTO)
    def get_workshop(self, request: HttpRequest, workshop_id: str) -> WorkshopViewDTO: ...


@rest_controller_advice
class EnrollmentRestErrorAdvice:
    @exception_handler(WorkshopNotFoundError, status=404)
    def answer_not_found(self, error: Exception) -> dict[str, str]:
        return error_answer(error)  # {"code": "workshop_not_found", "detail": "..."}


# what snakeboot.rest.urls does for the application
ControllerScan(ComponentScan.of(MyApplication)).add_to(api)
```

**Authentication.** An adapter that extends `BearerAuthentication` is a component of the container, like a
`SecurityFilterChain` bean: its constructor receives sections and ports by type. With one in the component scan, every
endpoint needs `Authorization: Bearer <token>`, the OpenAPI document says so, and `authenticated_principal(request)`
returns whom the token belongs to. `/health` stays open; an endpoint opts out with `auth=None`.

```python
class KeycloakTokens(BearerAuthentication):
    def __init__(self, properties: SecurityProperties) -> None:
        self._properties = properties

    @override
    def authenticate(self, token: str) -> str | None:
        ...  # the subject of a valid token, or None for 401
```

## Design rules

* Imitate the basics, not all of Spring: no AOP, no scheduling, no message brokers.
* Fail at start-up, not at the first request: a broken controller, listener, root or configuration stops the application.
* Each package knows as little as possible; `uv run lint-imports` enforces it.

## Develop

```bash
uv sync
uv run pre-commit install
uv run pytest            # tests, including the import contracts
uv run ruff check        # Clean Code rules
uv run mypy              # strict
```
