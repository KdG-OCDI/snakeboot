import contextlib
import inspect
import logging
import math
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import Enum
from functools import partial
from typing import Any, Final, get_type_hints, override

from pika.exceptions import AMQPError

from snakeboot.component_scan import MarkedMethod
from snakeboot.lifecycle.application_components import ApplicationComponents
from snakeboot.lifecycle.lifecycle import Lifecycle
from snakeboot.lifecycle.task_decorator import TaskDecorator
from snakeboot.rabbitmq.listener_declaration import AmqpDeclarationError, declare_listener_queue
from snakeboot.rabbitmq.message_conversion import MessageConversionError, body_reader
from snakeboot.rabbitmq.rabbit_connection_factory import RabbitConnectionFactory
from snakeboot.rabbitmq.rabbit_listener import (
    RABBIT_LISTENER_MAPPING_ATTRIBUTE,
    InvalidRabbitListenerError,
    RabbitListenerMapping,
    RejectAndDontRequeueError,
)
from snakeboot.tracing import TRACEPARENT, TraceContext

logger = logging.getLogger(__name__)

_SELF_AND_MESSAGE: Final = 2


@dataclass(frozen=True, slots=True)
class ListenerTiming:
    """How patiently a listener waits, like Spring AMQP's `recoveryInterval`, `shutdownTimeout` and Spring Boot's
    `spring.rabbitmq.listener.simple.retry.*`, whose defaults the retry takes."""

    reconnect_seconds: float = 5.0
    """Between attempts to reach a broker that is down."""
    attempts: int = 3
    """How often a message whose handling fails is tried before it is refused for good (`max-attempts`)."""
    retry_pause_seconds: float = 1.0
    """The pause after the first failed attempt, so a database that is down is not asked again at once
    (`initial-interval`)."""
    retry_multiplier: float = 1.0
    """How much longer each next pause is than the one before (`multiplier`): exponential back-off."""
    max_retry_pause_seconds: float = math.inf
    """The longest pause between two attempts (`max-interval`); no limit unless given, so a timing that only sets
    `retry_pause_seconds` keeps that pause, however long."""
    poll_seconds: float = 1.0
    """How long a listener waits for messages before it checks whether it must stop."""
    shutdown_seconds: float = 5.0
    """How long `stop` waits for a listener to finish the message in hand."""

    def retry_pauses(self) -> Iterator[float]:
        """Yields the pause after each failed attempt, in seconds: the first, then each `retry_multiplier` times
        longer, none longer than `max_retry_pause_seconds`."""
        pause = self.retry_pause_seconds
        while True:
            yield min(pause, self.max_retry_pause_seconds)
            pause = min(pause * self.retry_multiplier, self.max_retry_pause_seconds)


@dataclass(frozen=True, slots=True)
class RabbitListenerEndpoint:
    """One `@rabbit_listener` method, bound to its component: where it receives from and how it takes a body."""

    name: str
    mapping: RabbitListenerMapping
    receive: Callable[[bytes], None]


class RabbitListenerContainers(Lifecycle, component=False):
    """Runs every `@rabbit_listener` method of the application, each on a thread and connection of its own.

    Like Spring AMQP's listener containers: `start` finds the methods and their components, and a method that cannot
    receive as declared stops the start-up, even with `auto_startup` off. With it on, `start` declares every
    exchange, queue and binding before any listener consumes, as Spring AMQP's `RabbitAdmin` does: a declaration
    RabbitMQ refuses, such as a queue that exists without the dead-letter queue its listener now asks for, stops the
    start-up too (`AmqpDeclarationError`). A broker that cannot be reached does not: each listener waits for it.

    Each listener declares its exchange, queue and binding again on its own connection, takes one message at a time
    (prefetch 1) and reconnects when the broker goes away. `stop` lets each finish the message in hand. Every
    message is handled through the `TaskDecorator`, between fresh connections to the database.

    A message whose handling fails is tried again, `attempts` times in all, with a pause that grows by
    `retry_multiplier` after each failure, then refused for good, as Spring Boot does with `retry.enabled`: handed
    back to the queue instead, it would come back first, again and again, and hold up every message behind it.
    RabbitMQ then moves it to the listener's dead-letter queue, or drops it when there is none. During a pause the
    connection keeps answering the broker's heartbeats, so a long back-off does not lose it.

    `snakeboot.rabbitmq.rabbitmq_injectable` registers it with wireup; tests build it with a stand-in for the broker.
    """

    def __init__(
        self,
        components: ApplicationComponents,
        task_decorator: TaskDecorator,
        connection_factory: RabbitConnectionFactory,
        *,
        auto_startup: bool,
        timing: ListenerTiming = ListenerTiming(),  # noqa: B008  # reason: a frozen dataclass, shared safely
    ) -> None:
        self._components = components
        self._task_decorator = task_decorator
        self._connection_factory = connection_factory
        self._auto_startup = auto_startup
        self._timing = timing
        self._stopping = threading.Event()
        self._threads: list[threading.Thread] = []

    @property
    def running(self) -> int:
        """How many listener threads run."""
        return sum(thread.is_alive() for thread in self._threads)

    @override
    def start(self) -> None:
        endpoints = rabbit_listener_endpoints(self._components, self._task_decorator)
        if not self._auto_startup or not endpoints:
            return
        self._declare_before_consuming(endpoints)
        self._stopping.clear()
        self._threads = [self._thread_for(endpoint) for endpoint in endpoints]
        for thread in self._threads:
            thread.start()

    @override
    def stop(self) -> None:
        self._stopping.set()
        for thread in self._threads:
            thread.join(timeout=self._timing.shutdown_seconds)
        self._threads = []

    def _declare_before_consuming(self, endpoints: list[RabbitListenerEndpoint]) -> None:
        try:
            self._declare(endpoints)
        except AMQPError as error:  # an AmqpDeclarationError is no AMQPError: it stops the start-up
            logger.warning("RabbitMQ cannot be reached (%r); each listener declares its queue once it can", error)

    def _declare(self, endpoints: list[RabbitListenerEndpoint]) -> None:
        connection = self._connection_factory.open()
        try:
            channel = connection.channel()
            for endpoint in endpoints:
                declare_listener_queue(channel, endpoint.name, endpoint.mapping)
        finally:
            _close_quietly(connection)

    def _thread_for(self, endpoint: RabbitListenerEndpoint) -> threading.Thread:
        consumer = _Consumer(endpoint, self._connection_factory, timing=self._timing, stopping=self._stopping)
        return threading.Thread(target=consumer.run, name=f"snakeboot-rabbit-{endpoint.mapping.queue}", daemon=True)


def rabbit_listener_endpoints(
    components: ApplicationComponents, task_decorator: TaskDecorator
) -> list[RabbitListenerEndpoint]:
    """Returns every `@rabbit_listener` method of the application, bound to its component and its body reader.

    A method that cannot receive as declared stops here: async, or not taking exactly one message, or of a class that
    is no component. Each message is handled through `task_decorator`, between fresh connections to the database.
    """
    return [
        _endpoint_of(marked, components, task_decorator)
        for marked in components.methods_marked(RABBIT_LISTENER_MAPPING_ATTRIBUTE, RabbitListenerMapping)
    ]


def _endpoint_of(
    marked: MarkedMethod[RabbitListenerMapping], components: ApplicationComponents, task_decorator: TaskDecorator
) -> RabbitListenerEndpoint:
    method = marked.method
    if inspect.iscoroutinefunction(method):
        raise InvalidRabbitListenerError(f"{marked.name} is async; listeners are synchronous.")
    parameters = list(inspect.signature(method).parameters)
    if len(parameters) != _SELF_AND_MESSAGE:
        raise InvalidRabbitListenerError(f"{marked.name} must take exactly one argument: the message.")
    read = body_reader(get_type_hints(method).get(parameters[1], Any), marked.name)
    try:
        component: object = components.get(marked.owner)
    except LookupError as error:
        raise InvalidRabbitListenerError(
            f"{marked.name} listens, but {marked.owner.__qualname__} is no component: add @component."
        ) from error
    handle: Callable[[object], None] = getattr(component, method.__name__)

    def receive(body: bytes) -> None:
        task_decorator.decorate(partial(handle, read(body)))()

    return RabbitListenerEndpoint(marked.name, marked.mapping, receive)


class _Consumer:
    """The loop of one listener: connect, declare, consume until told to stop, and reconnect after a failure."""

    def __init__(
        self,
        endpoint: RabbitListenerEndpoint,
        connection_factory: RabbitConnectionFactory,
        *,
        timing: ListenerTiming,
        stopping: threading.Event,
    ) -> None:
        self._endpoint = endpoint
        self._connection_factory = connection_factory
        self._timing = timing
        self._stopping = stopping

    def run(self) -> None:
        while not self._stopping.is_set():
            try:
                self._consume()
            except AmqpDeclarationError as error:
                # Reached once the start-up is over: the broker was down then. Migrating the queue lets it consume.
                logger.error("%s It tries again in %s s.", error, self._timing.reconnect_seconds)
                self._stopping.wait(self._timing.reconnect_seconds)
            except AMQPError as error:
                logger.warning(
                    "%s cannot reach RabbitMQ (%r); it tries again in %s s",
                    self._endpoint.name,
                    error,
                    self._timing.reconnect_seconds,
                )
                self._stopping.wait(self._timing.reconnect_seconds)

    def _consume(self) -> None:
        mapping = self._endpoint.mapping
        connection = self._connection_factory.open()
        try:
            channel = connection.channel()
            declare_listener_queue(channel, self._endpoint.name, mapping)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=mapping.queue, on_message_callback=self._on_message)
            logger.info("%s listens to %s", self._endpoint.name, mapping.queue)
            while not self._stopping.is_set():
                connection.process_data_events(time_limit=self._timing.poll_seconds)
        finally:
            _close_quietly(connection)

    def _on_message(self, channel: Any, delivery: Any, properties: Any, body: bytes) -> None:  # noqa: PLR0917  # reason: pika calls it with four positional arguments
        # The message continues the trace of whoever sent it, like Spring AMQP's observation.
        headers = getattr(properties, "headers", None) or {}
        traceparent = headers.get(TRACEPARENT)
        with TraceContext.started(traceparent if isinstance(traceparent, str) else None):
            outcome = self._handled(body, channel.connection)
        if outcome is _Outcome.DONE:
            channel.basic_ack(delivery_tag=delivery.delivery_tag)
        else:
            channel.basic_reject(delivery_tag=delivery.delivery_tag, requeue=outcome is _Outcome.HAND_BACK)

    def _handled(self, body: bytes, connection: Any) -> "_Outcome":
        pauses = self._timing.retry_pauses()
        for attempt in range(1, self._timing.attempts + 1):
            pause = next(pauses)
            if (outcome := self._attempt(body, attempt, pause=pause)) is not None:
                return outcome
            if self._paused_until_stopping(connection, pause):
                return _Outcome.HAND_BACK  # stopping: the next start, or another process, tries it again
        return _Outcome.REFUSE

    def _attempt(self, body: bytes, attempt: int, *, pause: float) -> "_Outcome | None":
        name, attempts = self._endpoint.name, self._timing.attempts
        try:
            self._endpoint.receive(body)
        except (MessageConversionError, RejectAndDontRequeueError) as error:
            logger.warning("%s refused a message for good: %r", name, error)
            return _Outcome.REFUSE
        except Exception:
            if attempt == attempts:
                logger.exception("%s failed on a message %s times; it is refused for good", name, attempts)
                return _Outcome.REFUSE
            logger.warning(
                "%s failed on a message (attempt %s of %s); it tries again in %s s",
                name,
                attempt,
                attempts,
                pause,
                exc_info=True,
            )
            return None
        return _Outcome.DONE

    def _paused_until_stopping(self, connection: Any, seconds: float) -> bool:
        """Waits `seconds` before the next attempt, or until told to stop, and tells whether it must stop.

        The connection sleeps instead of the thread, in slices, so it keeps answering the broker's heartbeats: the
        broker closes a connection that stays silent longer than the heartbeat timeout and puts the message back on
        the queue, where its attempts start over.
        """
        deadline = time.monotonic() + seconds
        while not self._stopping.is_set() and (left := deadline - time.monotonic()) > 0:
            connection.sleep(min(left, self._timing.poll_seconds))
        return self._stopping.is_set()


class _Outcome(Enum):
    DONE = "acknowledge"
    REFUSE = "reject for good"
    HAND_BACK = "reject back to the queue"


def _close_quietly(connection: Any) -> None:
    if connection.is_open:
        with contextlib.suppress(AMQPError):  # the broker went away; nothing is left to close
            connection.close()
