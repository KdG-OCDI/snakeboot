import logging
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from enum import Enum
from functools import partial
from typing import Any, Final, override

from pika.exceptions import AMQPError

from snakeboot.events.stream_offsets import STREAM_CONSUMER_ATTRIBUTE, InMemoryStreamOffsets, StreamOffsets
from snakeboot.lifecycle.application_components import ApplicationComponents
from snakeboot.lifecycle.lifecycle import Lifecycle
from snakeboot.lifecycle.task_decorator import TaskDecorator
from snakeboot.rabbitmq.listener_declaration import AmqpDeclarationError, declare_listener_stream
from snakeboot.rabbitmq.message_conversion import MessageConversionError
from snakeboot.rabbitmq.rabbit_connection_factory import RabbitConnectionFactory
from snakeboot.rabbitmq.rabbit_listener import RejectAndDontRequeueError
from snakeboot.rabbitmq.rabbit_listener_containers import (
    BoundListener,
    ListenerTiming,
    bound_listener,
    close_quietly,
    paused_until_stopping,
)
from snakeboot.rabbitmq.rabbit_stream_listener import RabbitStreamListenerMapping
from snakeboot.tracing import TRACEPARENT, TraceContext
from snakeboot.transaction import TransactionManagerRegistry

logger = logging.getLogger(__name__)

STREAM_OFFSET: Final = "x-stream-offset"
"""Where a stream consumer starts (its argument), and the offset of a message it receives (a header)."""

FIRST: Final = "first"
"""The start of a stream: its oldest message."""

_PREFETCH: Final = 100
"""How many messages RabbitMQ hands a stream consumer before it acknowledged them; a stream requires a limit."""


class RabbitStreamListenerEndpoint:
    """One `@rabbit_stream_listener` method, bound to its component, and the offsets it reads from and saves."""

    def __init__(
        self,
        name: str,
        mapping: RabbitStreamListenerMapping,
        listener: BoundListener,
        *,
        task_decorator: TaskDecorator,
        offsets: StreamOffsets,
    ) -> None:
        self.name = name
        self.mapping = mapping
        self._listener = listener
        self._task_decorator = task_decorator
        self._offsets = offsets

    def start_offset(self) -> int | str:
        """Where the method reads on: after the last message it handled, or from the start of the stream."""
        found: list[int | None] = []
        self._task_decorator.decorate(lambda: found.append(self._offsets.last_handled(self.name)))()
        last = found[0]
        return FIRST if last is None else last + 1

    def receive(self, body: bytes, offset: int) -> None:
        """Handles the message at `offset` and saves the offset, in one transaction.

        Raises MessageConversionError for a body the method cannot take, and whatever the method raises.
        """
        message = self._listener.read(body)
        self._task_decorator.decorate(partial(self._handle, message, offset))()

    def skip(self, offset: int) -> None:
        """Saves `offset` without handling its message: one refused for good."""
        self._task_decorator.decorate(partial(self._remember, offset))()

    def _handle(self, message: object, offset: int) -> None:
        with _transaction():
            self._listener.handle(message)
            self._offsets.handled(self.name, offset)

    def _remember(self, offset: int) -> None:
        with _transaction():
            self._offsets.handled(self.name, offset)


def rabbit_stream_listener_endpoints(
    components: ApplicationComponents, task_decorator: TaskDecorator, offsets: StreamOffsets
) -> list[RabbitStreamListenerEndpoint]:
    """Returns every `@rabbit_stream_listener` method of the application, bound to its component and the offsets.

    A method that cannot receive as declared stops here, as a `@rabbit_listener` method does.
    """
    return [
        RabbitStreamListenerEndpoint(
            marked.name,
            marked.mapping,
            bound_listener(marked, components),
            task_decorator=task_decorator,
            offsets=offsets,
        )
        for marked in components.methods_marked(STREAM_CONSUMER_ATTRIBUTE, RabbitStreamListenerMapping)
    ]


def stream_offsets_of(components: ApplicationComponents) -> StreamOffsets:
    """Returns the offsets in the application's database, or offsets in memory for an application without one."""
    try:
        return components.get(StreamOffsets)
    except LookupError:
        return InMemoryStreamOffsets()


class RabbitStreamListenerContainers(Lifecycle, component=False):
    """Runs every `@rabbit_stream_listener` method of the application, each on a thread and connection of its own.

    `start` builds the methods, so one that cannot receive as declared stops the start-up, even with `auto_startup`
    off. With it on, it declares every exchange, stream and binding before any method reads, and a declaration
    RabbitMQ refuses stops the start-up too (`AmqpDeclarationError`). Each method then reads its stream from the
    offset after the last message it handled, or from the start, and reconnects when the broker goes away. A message
    whose handling keeps failing is not skipped: the method stops reading, waits, and reads on from that message, so
    a projection built from the stream never misses one. `stop` lets each finish the message in hand.

    `snakeboot.rabbitmq.rabbitmq_injectable` registers it with wireup; tests build it with a stand-in for the broker.
    """

    def __init__(
        self,
        endpoints: Callable[[], list[RabbitStreamListenerEndpoint]],
        connection_factory: RabbitConnectionFactory,
        *,
        auto_startup: bool,
        timing: ListenerTiming = ListenerTiming(),  # noqa: B008  # reason: a frozen dataclass, shared safely
    ) -> None:
        self._endpoints = endpoints
        self._connection_factory = connection_factory
        self._auto_startup = auto_startup
        self._timing = timing
        self._stopping = threading.Event()
        self._threads: list[threading.Thread] = []

    @property
    def running(self) -> int:
        """How many stream listener threads run."""
        return sum(thread.is_alive() for thread in self._threads)

    @override
    def start(self) -> None:
        endpoints = self._endpoints()
        if not self._auto_startup or not endpoints:
            return
        self._declare_before_reading(endpoints)
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

    def _declare_before_reading(self, endpoints: list[RabbitStreamListenerEndpoint]) -> None:
        try:
            self._declare(endpoints)
        except AMQPError as error:  # an AmqpDeclarationError is no AMQPError: it stops the start-up
            logger.warning(
                "RabbitMQ cannot be reached (%r); each stream listener declares its stream once it can", error
            )

    def _declare(self, endpoints: list[RabbitStreamListenerEndpoint]) -> None:
        connection = self._connection_factory.open()
        try:
            channel = connection.channel()
            for endpoint in endpoints:
                declare_listener_stream(channel, endpoint.name, endpoint.mapping)
        finally:
            close_quietly(connection)

    def _thread_for(self, endpoint: RabbitStreamListenerEndpoint) -> threading.Thread:
        reader = _StreamReader(endpoint, self._connection_factory, timing=self._timing, stopping=self._stopping)
        return threading.Thread(target=reader.run, name=f"snakeboot-stream-{endpoint.mapping.stream}", daemon=True)


class _Outcome(Enum):
    DONE = "acknowledge"
    STALLED = "read on from this message later"


class _StreamReader:
    """The loop of one stream listener: read from its offset, handle, and start over from it after a failure."""

    def __init__(
        self,
        endpoint: RabbitStreamListenerEndpoint,
        connection_factory: RabbitConnectionFactory,
        *,
        timing: ListenerTiming,
        stopping: threading.Event,
    ) -> None:
        self._endpoint = endpoint
        self._connection_factory = connection_factory
        self._timing = timing
        self._stopping = stopping
        self._stalled = False

    def run(self) -> None:
        while not self._stopping.is_set():
            try:
                self._read()
            except AMQPError as error:  # an AmqpDeclarationError is none, and is logged below
                logger.warning("%s cannot reach RabbitMQ (%r)", self._endpoint.name, error)
            except AmqpDeclarationError as error:
                logger.error("%s", error)
            except Exception:
                logger.exception("%s cannot find where it reads on", self._endpoint.name)
            else:
                if not self._stalled:
                    continue
            self._stopping.wait(self._timing.reconnect_seconds)

    def _read(self) -> None:
        self._stalled = False
        mapping = self._endpoint.mapping
        start = self._endpoint.start_offset()
        connection = self._connection_factory.open()
        try:
            channel = connection.channel()
            declare_listener_stream(channel, self._endpoint.name, mapping)
            channel.basic_qos(prefetch_count=_PREFETCH)
            channel.basic_consume(
                queue=mapping.stream, on_message_callback=self._on_message, arguments={STREAM_OFFSET: start}
            )
            logger.info("%s reads %s from %s", self._endpoint.name, mapping.stream, start)
            while not self._stopping.is_set() and not self._stalled:
                connection.process_data_events(time_limit=self._timing.poll_seconds)
        finally:
            close_quietly(connection)  # what it received and did not acknowledge, it reads again from the offset

    def _on_message(self, channel: Any, delivery: Any, properties: Any, body: bytes) -> None:  # noqa: PLR0917  # reason: pika calls it with four positional arguments
        if self._stalled:
            return  # received before the failure was known: read again from the offset
        headers = getattr(properties, "headers", None) or {}
        offset, traceparent = headers.get(STREAM_OFFSET), headers.get(TRACEPARENT)
        if not isinstance(offset, int):
            logger.warning("%s received a message without an offset from %s", self._endpoint.name, self._stream)
            channel.basic_ack(delivery_tag=delivery.delivery_tag)
            return
        with TraceContext.started(traceparent if isinstance(traceparent, str) else None):
            outcome = self._handled(body, offset, channel.connection)
        if outcome is _Outcome.DONE:
            channel.basic_ack(delivery_tag=delivery.delivery_tag)
        else:
            self._stalled = True

    @property
    def _stream(self) -> str:
        return self._endpoint.mapping.stream

    def _handled(self, body: bytes, offset: int, connection: Any) -> _Outcome:
        pauses = self._timing.retry_pauses()
        for attempt in range(1, self._timing.attempts + 1):
            pause = next(pauses)
            if (outcome := self._attempt(body, offset, attempt)) is not None:
                return outcome
            stopping = paused_until_stopping(
                connection, pause, stopping=self._stopping, poll_seconds=self._timing.poll_seconds
            )
            if stopping:
                break
        return _Outcome.STALLED

    def _attempt(self, body: bytes, offset: int, attempt: int) -> _Outcome | None:
        name, attempts = self._endpoint.name, self._timing.attempts
        try:
            self._endpoint.receive(body, offset)
        except (MessageConversionError, RejectAndDontRequeueError) as error:
            logger.warning("%s skips the message at offset %s of %s for good: %r", name, offset, self._stream, error)
            return self._skipped(offset)
        except Exception:
            if attempt == attempts:
                logger.exception(
                    "%s failed on the message at offset %s of %s %s times; it reads on from it in %s s",
                    name,
                    offset,
                    self._stream,
                    attempts,
                    self._timing.reconnect_seconds,
                )
                return _Outcome.STALLED
            logger.warning(
                "%s failed on the message at offset %s (attempt %s of %s)",
                name,
                offset,
                attempt,
                attempts,
                exc_info=True,
            )
            return None
        return _Outcome.DONE

    def _skipped(self, offset: int) -> _Outcome:
        try:
            self._endpoint.skip(offset)
        except Exception:
            logger.exception("%s could not save offset %s of %s", self._endpoint.name, offset, self._stream)
            return _Outcome.STALLED
        return _Outcome.DONE


def _transaction() -> AbstractContextManager[object]:
    if TransactionManagerRegistry.is_installed():
        return TransactionManagerRegistry.current().atomic()
    return nullcontext()
