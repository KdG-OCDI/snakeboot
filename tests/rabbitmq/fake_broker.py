"""A stand-in for RabbitMQ and pika's BlockingConnection: enough to declare, consume, acknowledge and publish."""

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from pika.exceptions import AMQPConnectionError, ChannelClosedByBroker, StreamLostError

type Consumer = Callable[[Any, Any, Any, bytes], None]


@dataclass
class Published:
    """One message the broker took."""

    exchange: str
    routing_key: str
    body: bytes
    properties: Any


@dataclass
class FakeBroker:
    """Stands in for RabbitMQ: remembers what was declared, delivers what a test hands it, records the outcome.

    Like RabbitMQ, it refuses to declare a queue that exists with other arguments (PRECONDITION_FAILED).
    """

    unreachable_attempts: int = 0
    lost_publishes: int = 0
    exchanges: dict[str, tuple[str, bool]] = field(default_factory=dict)
    queues: dict[str, dict[str, str]] = field(default_factory=dict)
    bindings: set[tuple[str, str, str]] = field(default_factory=set)
    acked: list[int] = field(default_factory=list)
    rejected: list[tuple[int, bool]] = field(default_factory=list)
    published: list[Published] = field(default_factory=list)
    slept: list[float] = field(default_factory=list)
    connections: list["FakeConnection"] = field(default_factory=list)
    settled: threading.Event = field(default_factory=threading.Event)
    _pending: "queue.Queue[tuple[str, bytes, dict[str, str] | None]]" = field(default_factory=queue.Queue)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def connect(self, _parameters: Any) -> "FakeConnection":
        """What `pika.BlockingConnection(parameters)` does: a connection, or AMQPConnectionError when down."""
        with self._lock:
            if self.unreachable_attempts > 0:
                self.unreachable_attempts -= 1
                raise AMQPConnectionError("the broker is down")
            connection = FakeConnection(self)
            self.connections.append(connection)
            return connection

    def deliver(self, queue_name: str, body: bytes, headers: dict[str, str] | None = None) -> None:
        """Puts a message, with its headers, on a queue, for the listener of that queue."""
        self._pending.put((queue_name, body, headers))

    def next_delivery(self, timeout: float) -> tuple[str, bytes, dict[str, str] | None] | None:
        """The next message for a consumer, or None after `timeout`."""
        try:
            return self._pending.get(timeout=timeout)
        except queue.Empty:
            return None

    def settle(self, outcome: Callable[[], None]) -> None:
        """Records an acknowledgement or a rejection and says one happened."""
        with self._lock:
            outcome()
        self.settled.set()


class FakeChannel:
    """Stands in for a pika channel."""

    def __init__(self, broker: FakeBroker, connection: "FakeConnection") -> None:
        self._broker = broker
        self.connection = connection
        self.is_open = True
        self.confirms = False
        self.prefetch = 0
        self.consumers: dict[str, Consumer] = {}

    def exchange_declare(self, exchange: str, exchange_type: str, durable: bool) -> None:
        self._broker.exchanges[exchange] = (exchange_type, durable)

    def queue_declare(self, queue: str, durable: bool, arguments: dict[str, str] | None = None) -> None:
        assert durable
        declared = self._broker.queues.setdefault(queue, arguments or {})
        if declared != (arguments or {}):
            self.is_open = False
            raise ChannelClosedByBroker(
                406, f"PRECONDITION_FAILED - inequivalent arg 'x-dead-letter-exchange' for queue '{queue}' in vhost '/'"
            )

    def queue_bind(self, queue: str, exchange: str, routing_key: str) -> None:
        self._broker.bindings.add((queue, exchange, routing_key))

    def basic_qos(self, prefetch_count: int) -> None:
        self.prefetch = prefetch_count

    def basic_consume(self, queue: str, on_message_callback: Consumer) -> None:
        self.consumers[queue] = on_message_callback

    def basic_ack(self, delivery_tag: int) -> None:
        self._broker.settle(lambda: self._broker.acked.append(delivery_tag))

    def basic_reject(self, delivery_tag: int, requeue: bool) -> None:
        self._broker.settle(lambda: self._broker.rejected.append((delivery_tag, requeue)))

    def confirm_delivery(self) -> None:
        self.confirms = True

    def basic_publish(self, exchange: str, routing_key: str, body: bytes, properties: Any) -> None:
        if self._broker.lost_publishes > 0:
            self._broker.lost_publishes -= 1
            self.is_open = False
            raise StreamLostError("the connection was lost")
        self._broker.published.append(Published(exchange, routing_key, body, properties))


class FakeConnection:
    """Stands in for pika's BlockingConnection: delivers pending messages to the consumers of its channel."""

    def __init__(self, broker: FakeBroker) -> None:
        self._broker = broker
        self.is_open = True
        self.channels: list[FakeChannel] = []
        self._tags = 0

    def channel(self) -> FakeChannel:
        channel = FakeChannel(self._broker, self)
        self.channels.append(channel)
        return channel

    def process_data_events(self, time_limit: float) -> None:
        delivery = self._broker.next_delivery(timeout=time_limit)
        if delivery is None:
            return
        queue_name, body, headers = delivery
        for channel in self.channels:
            if queue_name in channel.consumers:
                self._tags += 1
                properties = SimpleNamespace(headers=headers)
                channel.consumers[queue_name](channel, SimpleNamespace(delivery_tag=self._tags), properties, body)
                return
        self._broker.deliver(queue_name, body, headers)
        time.sleep(time_limit)

    def sleep(self, duration: float) -> None:
        """What `BlockingConnection.sleep` does: waits while it keeps the connection alive."""
        self._broker.slept.append(duration)
        time.sleep(duration)

    def close(self) -> None:
        self.is_open = False
