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
| `RecordingTransactionManager`, `declared_classes` | spring-test | nothing |

The transaction, component scan and testing packages import nothing but the standard library,
so the application layer of a hexagonal application can use `@transactional` without importing Django.

## Install

```bash
uv add "snakeboot[django,ninja]"
```

## A tour

**The application root.** The component scan starts in the package of the marked class, like
`@SpringBootApplication`. It skips Django's entry points (`wsgi.py`, `asgi.py`, migrations) and
adds the components snakeboot provides itself (the event publisher).

```python
# myapp/myapp_application.py
@application_root
class MyApplication: ...


# settings.py: the setting wireup needs anyway
WIREUP = WireupSettings(injectables=[*ComponentScan.of(MyApplication).module_names()], auto_inject_views=False)
```

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


# composition, at start-up
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

**REST controllers.** Singleton classes with constructor injection, found by the component scan.
Two endpoints for the same URL, or two answers for one error, stop the start-up.

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


# urls.py
mounted = RestControllerMounter().mount(api, scan=settings.WIREUP.injectables or ())
```

## Design rules

* Imitate the basics, not all of Spring: no AOP, no profiles, no scheduling, no message brokers.
* Fail at start-up, not at the first request: a broken controller, listener or root stops the application.
* Each package knows as little as possible; `uv run lint-imports` enforces it.

## Develop

```bash
uv sync
uv run pre-commit install
uv run pytest            # tests, including the import contracts
uv run ruff check        # Clean Code rules
uv run mypy              # strict
```
