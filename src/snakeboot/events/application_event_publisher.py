import logging
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from functools import partial

from snakeboot.events.application_event_listener_registry import ApplicationEventListenerRegistry, ListenerMethod
from snakeboot.events.event_listener_markers import Delivery
from snakeboot.events.event_publication_registry import EventPublication, EventPublicationRegistry
from snakeboot.events.task_executor import SyncTaskExecutor, TaskExecutor
from snakeboot.tracing import TraceContext
from snakeboot.transaction import TransactionManagerRegistry, after_commit

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Delivery:
    """One event for one `@application_module_listener`: its publication in the registry, the publisher's trace."""

    method: ListenerMethod
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

    It keeps its listeners in an `ApplicationEventListenerRegistry`, which `register` fills. The library registers
    the publisher with wireup (`application_event_publisher_injectable`) without a single listener, so a listener may
    depend on a use case that publishes; the start-up then registers every listener wireup found, or none
    (`EventListenerMethodProcessor`). Tests build it with the listeners they need.
    """

    def __init__(
        self,
        listeners: Iterable[object] = (),
        *,
        executor: TaskExecutor | None = None,
        registry: EventPublicationRegistry | None = None,
    ) -> None:
        self._listeners = ApplicationEventListenerRegistry()
        self._executor = executor or SyncTaskExecutor()
        self._registry = registry
        self.register(listeners)

    @property
    def has_application_module_listeners(self) -> bool:
        """Whether a listener receives events on a thread of its own, so the registry may owe it some."""
        return any(m.mapping.delivery is Delivery.ASYNC_AFTER_COMMIT for m in self._listeners.methods)

    def register(self, listeners: Iterable[object]) -> None:
        """Adds the listener methods of `listeners`, like Spring's `addApplicationListener`.

        The start-up registers every `@application_event_listener` here once the container is built. A listener that
        cannot listen raises `InvalidApplicationEventListenerError`, and so does an `@application_module_listener`
        for events the registry cannot keep.
        """
        added = self._listeners.register(listeners)
        asynchronous = [m for m in added if m.mapping.delivery is Delivery.ASYNC_AFTER_COMMIT]
        if self._registry is not None and asynchronous:
            self._registry.verify({event_type for m in asynchronous for event_type in m.mapping.event_types})

    def publish(self, event: object) -> None:
        """Delivers `event` to every listener method for its type: at once, after the commit, or on its own."""
        methods = self._listeners.receiving(event)
        publications = self._stored(event, methods)
        for method in methods:
            match method.mapping.delivery:
                case Delivery.IN_TRANSACTION:
                    method.receive(event)
                case Delivery.AFTER_COMMIT:
                    after_commit(partial(method.receive, event))
                case Delivery.ASYNC_AFTER_COMMIT:
                    publication, trace = publications.get(method.name), TraceContext.current()
                    _after_commit_or_now(partial(self._hand_over, _Delivery(method, event, publication, trace)))

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
        by_name = {method.name: method for method in self._listeners.methods}
        for publication in publications:
            method = by_name.get(publication.listener_id)
            if method is None:
                self._failed(publication, LookupError(f"No listener method is named {publication.listener_id}."))
            else:
                self._hand_over(_Delivery(method, publication.event, publication, None))
        return len(publications)

    def _stored(self, event: object, methods: Sequence[ListenerMethod]) -> dict[str, EventPublication]:
        owed = [m.name for m in methods if m.mapping.delivery is Delivery.ASYNC_AFTER_COMMIT]
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
                    delivery.method.receive(delivery.event)
                    if publication is not None and self._registry is not None:
                        self._registry.complete(publication)
            except Exception as error:
                name, event = delivery.method.name, type(delivery.event).__qualname__
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
