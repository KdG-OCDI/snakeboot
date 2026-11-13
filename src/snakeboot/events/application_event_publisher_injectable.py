"""Registers the one ApplicationEventPublisher with wireup, so no application has to.

Spring always provides an `ApplicationEventPublisher`, with or without listeners; this
module is the library's equivalent. A component scan that covers the library finds it;
otherwise an application lists this module among wireup's injectables.
"""

from collections.abc import Iterator, Sequence

from wireup import injectable

from snakeboot.events.application_event_listener import ApplicationEventListener, InvalidApplicationEventListenerError
from snakeboot.events.application_event_publisher import ApplicationEventPublisher
from snakeboot.events.event_listener_method_processor import EventListenerMethodProcessor
from snakeboot.events.event_publication_registry import EventPublicationRegistry
from snakeboot.events.task_executor import TaskExecutor, ThreadPoolTaskExecutor


@injectable(as_type=TaskExecutor)
def task_executor() -> Iterator[TaskExecutor]:
    """Provides the pool of threads of the `@application_module_listener` methods, like Spring Boot's
    `applicationTaskExecutor`; closing the container lets their work finish."""
    executor = ThreadPoolTaskExecutor()
    yield executor
    executor.shutdown()


@injectable
def application_event_publisher(
    executors: Sequence[TaskExecutor] = (),
    registries: Sequence[EventPublicationRegistry] = (),
) -> ApplicationEventPublisher:
    """Provides the publisher, which depends on no listener: `event_listener_method_processor` registers them.

    So a listener may depend on a use case that publishes events, where a publisher built with every listener would
    close a cycle. The executor is `task_executor`'s, or the caller's thread for a container without it; the event
    publication registry is there when the application has a database.
    """
    if len(registries) > 1 or len(executors) > 1:
        raise InvalidApplicationEventListenerError("The application has one executor and one registry, not several.")
    executor, registry = next(iter(executors), None), next(iter(registries), None)
    return ApplicationEventPublisher(executor=executor, registry=registry)


@injectable
def event_listener_method_processor(
    publisher: ApplicationEventPublisher, listeners: Sequence[ApplicationEventListener] = ()
) -> EventListenerMethodProcessor:
    """Provides what registers every `@application_event_listener` wireup knows with the publisher at start-up.

    Wireup only creates `Sequence[ApplicationEventListener]` when at least one listener
    exists. Without the default, an application without listeners would not even start;
    with it, wireup leaves the parameter out and the publisher simply has nobody to tell.
    """
    return EventListenerMethodProcessor(publisher, listeners)
