import json
import logging
import threading
from dataclasses import dataclass
from functools import partial
from typing import Any, override

from snakeboot.events import InMemoryStreamOffsets, StreamEvent, StreamOffsets
from snakeboot.lifecycle.application_components import ApplicationComponents
from snakeboot.lifecycle.task_decorator import TaskDecorator
from snakeboot.rabbitmq.message_conversion import MessageConversionError, body_of
from snakeboot.rabbitmq.rabbit_listener import RejectAndDontRequeueError
from snakeboot.rabbitmq.rabbit_listener_containers import RabbitListenerEndpoint, rabbit_listener_endpoints
from snakeboot.rabbitmq.rabbit_stream_listener_containers import (
    RabbitStreamListenerEndpoint,
    rabbit_stream_listener_endpoints,
    stream_offsets_of,
)
from snakeboot.rabbitmq.rabbit_template import RabbitTemplate
from snakeboot.transaction import TransactionManagerRegistry, after_commit

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SentMessage:
    """A message the application sent: to which exchange, with which routing key, and its JSON body."""

    exchange: str
    routing_key: str
    body: bytes
    message_id: str | None

    def json(self) -> Any:
        """Returns the body, read as JSON."""
        return json.loads(self.body)


@dataclass(frozen=True, slots=True)
class RefusedMessage:
    """A message a `@rabbit_listener` method did not take: which method, what it raised, and where it went.

    `dead_letter_queue` is the listener's dead-letter queue, which RabbitMQ would move the message to, or None when
    the listener has none and RabbitMQ would drop it.
    """

    message: SentMessage
    listener: str
    error: Exception
    dead_letter_queue: str | None


class InProcessRabbitTemplate(RabbitTemplate):
    """A `RabbitTemplate` without a broker, like Spring AMQP's `TestRabbitTemplate`: a test's application sends with it.

    `convert_and_send` writes the payload as the same JSON, keeps the message in `sent`, and hands it to every
    `@rabbit_listener` method whose queue the exchange routes it to (`*` one word of the routing key, `#` any number),
    through the method's own conversion and task decorator: one method per queue, as a queue's consumers share it. It
    hands the message over once the sender's transaction committed, or at once outside one, so the listener works in
    a transaction of its own, as it would on a thread of its own. As with a broker, a listener that fails does not
    fail the sender: the message lands in `refused`, with the error, after one attempt (the retries of
    `[rabbitmq.listener.retry]` are left out, so a test does not wait for them). What a listener with
    `dead_letter=True` refuses is also in `dead_lettered`, as its dead-letter queue would keep it.

    A stream holds what the bindings of all its `@rabbit_stream_listener` methods route to it, each message with the
    stream's next offset, and every method of the stream reads it, as on RabbitMQ: a method handles the messages its
    own routing key matches and claims their offsets. What a method refuses for good lands in `refused`, and the
    method skips it. Another failure lands there too, after one attempt, and the method then stalls, as it would on
    RabbitMQ: it handles nothing more of its stream until the next test. A test does not replay a stream: each starts
    with empty streams, and a method whose offset an earlier test left in the database starts over, as it does on
    RabbitMQ when its stream is deleted and declared anew.
    """

    def __init__(self, components: ApplicationComponents) -> None:  # the broker's connection factory is left out
        self._components = components
        self._endpoints: list[RabbitListenerEndpoint] | None = None
        self._stream_endpoints: list[RabbitStreamListenerEndpoint] | None = None
        self._offsets: StreamOffsets | None = None
        self._stream_lengths: dict[str, int] = {}
        self._stalled: set[str] = set()
        self._lock = threading.Lock()
        self.sent: list[SentMessage] = []
        self.refused: list[RefusedMessage] = []

    def clear(self) -> None:
        """Forgets every sent and refused message, as a test that keeps its application does before the next test."""
        with self._lock:
            self.sent.clear()
            self.refused.clear()
            self._stream_lengths.clear()
            self._stalled.clear()
            if isinstance(self._offsets, InMemoryStreamOffsets):
                self._offsets.clear()

    @property
    def dead_lettered(self) -> list[RefusedMessage]:
        """Every refused message that a dead-letter queue would keep, in the order they were refused."""
        with self._lock:
            return [refused for refused in self.refused if refused.dead_letter_queue is not None]

    @override
    def convert_and_send(
        self, exchange: str, routing_key: str, payload: object, *, message_id: str | None = None
    ) -> None:
        message = SentMessage(exchange, routing_key, body_of(payload), message_id)
        with self._lock:
            self.sent.append(message)
        if TransactionManagerRegistry.is_installed():
            after_commit(partial(self._deliver, message))
        else:
            self._deliver(message)

    def _deliver(self, message: SentMessage) -> None:
        by_queue: dict[str, RabbitListenerEndpoint] = {}
        for endpoint in self._listeners():
            bound = endpoint.mapping.exchange == message.exchange
            if bound and endpoint.mapping.matches(message.routing_key):
                by_queue.setdefault(endpoint.mapping.queue, endpoint)
        for endpoint in by_queue.values():
            try:
                endpoint.receive(message.body)
            except Exception as error:  # as with a broker, a failing listener never fails the sender
                logger.warning("%s refused a message to %s", endpoint.name, message.routing_key, exc_info=True)
                self._keep(RefusedMessage(message, endpoint.name, error, endpoint.mapping.dead_letter_queue))
        self._append_to_streams(message)

    def _append_to_streams(self, message: SentMessage) -> None:
        by_stream: dict[str, list[RabbitStreamListenerEndpoint]] = {}
        for endpoint in self._stream_listeners():
            if endpoint.mapping.exchange == message.exchange:
                by_stream.setdefault(endpoint.mapping.stream, []).append(endpoint)
        for stream, endpoints in by_stream.items():
            if any(endpoint.mapping.matches(message.routing_key) for endpoint in endpoints):
                with self._lock:
                    offset = self._stream_lengths.get(stream, 0)
                    self._stream_lengths[stream] = offset + 1
                for endpoint in endpoints:
                    self._read_from_stream(endpoint, message, offset)

    def _read_from_stream(self, endpoint: RabbitStreamListenerEndpoint, message: SentMessage, offset: int) -> None:
        if endpoint.name in self._stalled or not endpoint.mapping.matches(message.routing_key):
            return
        event = StreamEvent.of(offset, message.body, message.message_id)
        generation = self._generation_to_read_in(endpoint, event)
        try:
            endpoint.receive(message.body, event, generation=generation)
        except (MessageConversionError, RejectAndDontRequeueError) as error:  # skipped for good, as on RabbitMQ
            logger.warning("%s refused a message to %s", endpoint.name, message.routing_key, exc_info=True)
            self._keep(RefusedMessage(message, endpoint.name, error, None))
            endpoint.skip(event, generation=generation)
        except Exception as error:  # the method stalls on it, as on RabbitMQ, and the sender never fails
            logger.warning("%s failed on a message to %s", endpoint.name, message.routing_key, exc_info=True)
            self._keep(RefusedMessage(message, endpoint.name, error, None))
            with self._lock:
                self._stalled.add(endpoint.name)

    @staticmethod
    def _generation_to_read_in(endpoint: RabbitStreamListenerEndpoint, event: StreamEvent) -> int:
        # A stream gives every message a higher offset, so a method that handled this offset or a later one read
        # another stream: one of an earlier test, whose offsets the database kept. It starts over, as on RabbitMQ.
        position = endpoint.position()
        if position.last is None or position.last.offset < event.offset:
            return position.generation
        if endpoint.start_over(position):
            logger.warning(
                "%s handled its stream up to offset %s, but the stream is a new one: it reads it from the start",
                endpoint.name,
                position.last.offset,
            )
        return endpoint.position().generation

    def _keep(self, refused: RefusedMessage) -> None:
        with self._lock:
            self.refused.append(refused)

    def _listeners(self) -> list[RabbitListenerEndpoint]:
        # Found at the first message, not when the application starts: their components then get the test's doubles.
        with self._lock:
            if self._endpoints is None:
                self._endpoints = rabbit_listener_endpoints(self._components, self._components.get(TaskDecorator))
            return self._endpoints

    def _stream_listeners(self) -> list[RabbitStreamListenerEndpoint]:
        # Found at the first message, as the other listeners are: their components then get the test's doubles.
        with self._lock:
            if self._stream_endpoints is None:
                self._offsets = stream_offsets_of(self._components)
                decorator = self._components.get(TaskDecorator)
                self._stream_endpoints = rabbit_stream_listener_endpoints(self._components, decorator, self._offsets)
            return self._stream_endpoints
