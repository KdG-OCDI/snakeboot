"""Technical library: in-process application events, like Spring's `ApplicationEventPublisher`.

    @application_event_listener                                    # a @Component with listener methods
    class ParticipantNotificationListener:
        def __init__(self, notifications: NotificationPort) -> None:   # constructor injection
            self._notifications = notifications

        @transactional_event_listener(WaitlistedParticipantPromoted)    # @TransactionalEventListener
        def notify_promoted(self, event: WaitlistedParticipantPromoted) -> None: ...

        @application_module_listener(WorkshopCancelled)                 # Spring Modulith's @ApplicationModuleListener
        def refund(self, event: WorkshopCancelled) -> None: ...         # own thread, own transaction, at least once

    # in a @transactional use case, after saving the aggregate:
    self._events.publish_all(workshop.pull_events())

Events are facts, never requests: a caller that needs an outcome calls a facade instead. With a database, the
publications of the `@application_module_listener` methods are kept in the `EventPublicationRegistry` until they
were delivered (`snakeboot.event_publication`), so they arrive at least once. The publisher depends on no listener:
the start-up builds every listener once the container is built and registers it (`EventListenerMethodProcessor`), so a
listener may inject a use case that publishes events, and one that cannot be built stops the start.
The library knows wireup, `snakeboot.transaction` and `snakeboot.tracing`, but no framework and no bounded context.
"""

from snakeboot.events.application_event_listener import (
    ApplicationEventListener,
    InvalidApplicationEventListenerError,
    application_event_listener,
)
from snakeboot.events.application_event_publisher import ApplicationEventPublisher
from snakeboot.events.event_listener_markers import (
    Delivery,
    ListenerMapping,
    application_module_listener,
    event_listener,
    transactional_event_listener,
)
from snakeboot.events.event_publication_registry import EventPublication, EventPublicationRegistry
from snakeboot.events.task_executor import SyncTaskExecutor, TaskExecutor, ThreadPoolTaskExecutor

__all__ = [
    "ApplicationEventListener",
    "ApplicationEventPublisher",
    "Delivery",
    "EventPublication",
    "EventPublicationRegistry",
    "InvalidApplicationEventListenerError",
    "ListenerMapping",
    "SyncTaskExecutor",
    "TaskExecutor",
    "ThreadPoolTaskExecutor",
    "application_event_listener",
    "application_module_listener",
    "event_listener",
    "transactional_event_listener",
]
