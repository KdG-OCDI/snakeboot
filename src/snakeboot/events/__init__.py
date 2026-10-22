"""Technical library: in-process application events, like Spring's `ApplicationEventPublisher`.

    @application_event_listener                                    # a @Component with listener methods
    class ParticipantNotificationListener:
        def __init__(self, notifications: NotificationPort) -> None:   # constructor injection
            self._notifications = notifications

        @transactional_event_listener(WaitlistedParticipantPromoted)    # @TransactionalEventListener
        def notify_promoted(self, event: WaitlistedParticipantPromoted) -> None: ...

    # in a @transactional use case, after saving the aggregate:
    self._events.publish_all(workshop.pull_events())

Events are facts, never requests: a caller that needs an outcome calls a facade instead.
The library knows wireup and `snakeboot.transaction`, but no framework and no bounded context.
"""

from snakeboot.events.application_event_listener import (
    ApplicationEventListener,
    InvalidApplicationEventListenerError,
    application_event_listener,
)
from snakeboot.events.application_event_publisher import ApplicationEventPublisher
from snakeboot.events.event_listener_markers import event_listener, transactional_event_listener

__all__ = [
    "ApplicationEventListener",
    "ApplicationEventPublisher",
    "InvalidApplicationEventListenerError",
    "application_event_listener",
    "event_listener",
    "transactional_event_listener",
]
