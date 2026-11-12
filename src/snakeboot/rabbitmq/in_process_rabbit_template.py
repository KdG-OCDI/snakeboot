import json
import logging
import threading
from dataclasses import dataclass
from functools import partial
from typing import Any, override

from snakeboot.lifecycle.application_components import ApplicationComponents
from snakeboot.lifecycle.task_decorator import TaskDecorator
from snakeboot.rabbitmq.message_conversion import body_of
from snakeboot.rabbitmq.rabbit_listener_containers import RabbitListenerEndpoint, rabbit_listener_endpoints
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
    """A message a `@rabbit_listener` method did not take: which method, and what it raised."""

    message: SentMessage
    listener: str
    error: Exception


class InProcessRabbitTemplate(RabbitTemplate):
    """A `RabbitTemplate` without a broker, like Spring AMQP's `TestRabbitTemplate`: a test's application sends with it.

    `convert_and_send` writes the payload as the same JSON, keeps the message in `sent`, and hands it to every
    `@rabbit_listener` method whose queue the exchange routes it to (`*` one word of the routing key, `#` any number),
    through the method's own conversion and task decorator: one method per queue, as a queue's consumers share it. It
    hands the message over once the sender's transaction committed, or at once outside one, so the listener works in
    a transaction of its own, as it would on a thread of its own. As with a broker, a listener that fails does not
    fail the sender: the message lands in `refused`, with the error, after one attempt.
    """

    def __init__(self, components: ApplicationComponents) -> None:  # the broker's connection factory is left out
        self._components = components
        self._endpoints: list[RabbitListenerEndpoint] | None = None
        self._lock = threading.Lock()
        self.sent: list[SentMessage] = []
        self.refused: list[RefusedMessage] = []

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
            if bound and _routes(endpoint.mapping.routing_key, message.routing_key):
                by_queue.setdefault(endpoint.mapping.queue, endpoint)
        for endpoint in by_queue.values():
            try:
                endpoint.receive(message.body)
            except Exception as error:  # as with a broker, a failing listener never fails the sender
                logger.warning("%s refused a message to %s", endpoint.name, message.routing_key, exc_info=True)
                with self._lock:
                    self.refused.append(RefusedMessage(message, endpoint.name, error))

    def _listeners(self) -> list[RabbitListenerEndpoint]:
        # Found at the first message, not when the application starts: their components then get the test's doubles.
        with self._lock:
            if self._endpoints is None:
                self._endpoints = rabbit_listener_endpoints(self._components, self._components.get(TaskDecorator))
            return self._endpoints


def _routes(binding_key: str, routing_key: str) -> bool:
    """Tells whether a topic exchange routes `routing_key` to a queue bound with `binding_key`."""
    return _words_match(binding_key.split("."), routing_key.split("."))


def _words_match(pattern: list[str], words: list[str]) -> bool:
    if not pattern:
        return not words
    head, rest = pattern[0], pattern[1:]
    if head == "#":
        return any(_words_match(rest, words[skipped:]) for skipped in range(len(words) + 1))
    return bool(words) and head in {"*", words[0]} and _words_match(rest, words[1:])
