import inspect
import logging
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from functools import partial
from typing import Any, Final

from snakeboot.events.application_event_listener import InvalidApplicationEventListenerError
from snakeboot.events.event_listener_markers import LISTENER_MAPPING_ATTRIBUTE, Delivery, ListenerMapping
from snakeboot.events.event_publication_registry import EventPublication, EventPublicationRegistry
from snakeboot.events.task_executor import SyncTaskExecutor, TaskExecutor
from snakeboot.tracing import TraceContext
from snakeboot.transaction import TransactionManagerRegistry, after_commit

logger = logging.getLogger(__name__)

_SELF_AND_EVENT: Final = 2


@dataclass(frozen=True, slots=True)
class _Subscription:
    """One listener method and the events it receives."""

    name: str
    receive: Callable[[object], None]
    mapping: ListenerMapping


@dataclass(frozen=True, slots=True)
class _Delivery:
    """One event for one `@application_module_listener`: its publication in the registry, the publisher's trace."""

    subscription: _Subscription
    event: object
    publication: EventPublication | None
    trace: TraceContext | None


class ApplicationEventPublisher:
    """Hands each event to the listener methods that asked for its type (Spring's `ApplicationEventPublisher`).

    It is the Observer pattern for facts: the use case that publishes does not know who
    reacts, and a new reaction is a new listener, not a change to the use case. Delivery is
    in-process, in a stable order (by listener name). A listener for a base class (`WorkshopEvent`)
    receives every subclass.

    An `@event_listener` receives the event at once, a `@transactional_event_listener` after the commit.
    An `@application_module_listener` receives it after the commit on the `executor`, in a transaction of its
    own and in the trace of the publisher; with a `registry`, the publisher's transaction stores the publication,
    the listener's transaction completes it, and `resubmit_incomplete` delivers the ones that failed or were lost.

    The library registers it with wireup (`application_event_publisher_injectable`), connected
    to every listener wireup found, or to none; tests build it with the listeners they need.
    """

    def __init__(
        self,
        listeners: Iterable[object],
        *,
        executor: TaskExecutor | None = None,
        registry: EventPublicationRegistry | None = None,
    ) -> None:
        self._subscriptions = sorted(
            (subscription for listener in listeners for subscription in self._subscriptions_of(listener)),
            key=lambda subscription: subscription.name,
        )
        self._executor = executor or SyncTaskExecutor()
        self._registry = registry
        asynchronous = [s for s in self._subscriptions if s.mapping.delivery is Delivery.ASYNC_AFTER_COMMIT]
        if registry is not None and asynchronous:
            registry.verify({event_type for s in asynchronous for event_type in s.mapping.event_types})

    @property
    def has_application_module_listeners(self) -> bool:
        """Whether a listener receives events on a thread of its own, so the registry may owe it some."""
        return any(s.mapping.delivery is Delivery.ASYNC_AFTER_COMMIT for s in self._subscriptions)

    def publish(self, event: object) -> None:
        """Delivers `event` to every listener method for its type: at once, after the commit, or on its own."""
        subscriptions = [s for s in self._subscriptions if isinstance(event, s.mapping.event_types)]
        publications = self._stored(event, subscriptions)
        for subscription in subscriptions:
            match subscription.mapping.delivery:
                case Delivery.IN_TRANSACTION:
                    subscription.receive(event)
                case Delivery.AFTER_COMMIT:
                    after_commit(partial(subscription.receive, event))
                case Delivery.ASYNC_AFTER_COMMIT:
                    publication, trace = publications.get(subscription.name), TraceContext.current()
                    _after_commit_or_now(partial(self._hand_over, _Delivery(subscription, event, publication, trace)))

    def publish_all(self, events: Iterable[object]) -> None:
        """Publishes `events` in the order they happened."""
        for event in events:
            self.publish(event)

    def resubmit_incomplete(self) -> int:
        """Delivers again every publication of the registry whose turn has come, and returns how many.

        Like Spring Modulith's `IncompleteEventPublications.resubmitIncompletePublications`: a failed delivery, or one
        a stopped process lost. `snakeboot.event_publication` calls it periodically.
        """
        if self._registry is None:
            return 0
        publications = self._registry.claim_due()
        by_name = {subscription.name: subscription for subscription in self._subscriptions}
        for publication in publications:
            subscription = by_name.get(publication.listener_id)
            if subscription is None:
                self._failed(publication, LookupError(f"No listener method is named {publication.listener_id}."))
            else:
                self._hand_over(_Delivery(subscription, publication.event, publication, None))
        return len(publications)

    def _stored(self, event: object, subscriptions: Sequence[_Subscription]) -> dict[str, EventPublication]:
        owed = [s.name for s in subscriptions if s.mapping.delivery is Delivery.ASYNC_AFTER_COMMIT]
        if self._registry is None or not owed:
            return {}
        return {publication.listener_id: publication for publication in self._registry.store(event, owed)}

    def _hand_over(self, delivery: _Delivery) -> None:
        self._executor.execute(partial(self._deliver, delivery))

    def _deliver(self, delivery: _Delivery) -> None:
        # Like @Async with @Transactional(REQUIRES_NEW): the listener's work and the completion commit together.
        publication = delivery.publication
        with TraceContext.started(delivery.trace.traceparent if delivery.trace is not None else None):
            try:
                with _own_transaction():
                    delivery.subscription.receive(delivery.event)
                    if publication is not None and self._registry is not None:
                        self._registry.complete(publication)
            except Exception as error:
                name, event = delivery.subscription.name, type(delivery.event).__qualname__
                logger.exception("The listener %s failed on %s", name, event)
                if publication is not None:
                    self._failed(publication, error)

    def _failed(self, publication: EventPublication, error: Exception) -> None:
        if self._registry is None:
            return
        try:
            self._registry.fail(publication, error)
        except Exception:
            logger.exception("The failure of publication %s could not be recorded", publication.identifier)

    def _subscriptions_of(self, listener: object) -> list[_Subscription]:
        listener_class = type(listener)
        subscriptions = [
            _Subscription(
                name=f"{listener_class.__module__}.{listener_class.__qualname__}.{name}",
                receive=self._receiver(listener, name, method),
                mapping=mapping,
            )
            for name, method in inspect.getmembers(listener_class, inspect.isfunction)
            if (mapping := getattr(method, LISTENER_MAPPING_ATTRIBUTE, None)) is not None
        ]
        if not subscriptions:
            raise InvalidApplicationEventListenerError(f"{listener_class.__name__} has no listener methods.")
        return subscriptions

    def _receiver(self, listener: object, name: str, method: Callable[..., Any]) -> Callable[[object], None]:
        owner = f"{type(listener).__name__}.{name}"
        if inspect.iscoroutinefunction(method):
            raise InvalidApplicationEventListenerError(f"{owner} is async; listeners are synchronous.")
        if len(inspect.signature(method).parameters) != _SELF_AND_EVENT:
            raise InvalidApplicationEventListenerError(f"{owner} must take exactly one argument: the event.")
        receive: Callable[[object], None] = getattr(listener, name)
        return receive


def _after_commit_or_now(callback: Callable[[], None]) -> None:
    # An application without a database has no transaction to wait for.
    if TransactionManagerRegistry.is_installed():
        after_commit(callback)
    else:
        callback()


def _own_transaction() -> AbstractContextManager[object]:
    if TransactionManagerRegistry.is_installed():
        return TransactionManagerRegistry.current().atomic()
    return nullcontext()
