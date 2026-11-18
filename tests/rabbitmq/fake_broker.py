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
type Delivery = tuple[str, bytes, dict[str, object] | None, str]


@dataclass
class Published:
    """One message the broker took."""

    exchange: str
    routing_key: str
    body: bytes
    properties: Any


@dataclass(frozen=True)
class StreamMessage:
    """One message a stream keeps, at its offset."""

    offset: int
    body: bytes
    routing_key: str
    message_id: str | None


@dataclass
class FakeBroker:
    """Stands in for RabbitMQ: remembers what was declared, delivers what a test hands it, records the outcome.

    Like RabbitMQ, it refuses to declare a queue that exists with other arguments (PRECONDITION_FAILED). A stream a
    test appends to (`append`) is read as RabbitMQ 4 has it read: a consumer gets the messages from the offset it
    asked for and none before it, so nothing at all while that offset is beyond the end; `last` is the last message;
    a stream that is deleted cancels its consumers and counts from 0 once it is declared anew.
    """

    unreachable_attempts: int = 0
    lost_publishes: int = 0
    exchanges: dict[str, tuple[str, bool]] = field(default_factory=dict)
    queues: dict[str, dict[str, object]] = field(default_factory=dict)
    """Every queue and stream declared, with its arguments."""
    bindings: set[tuple[str, str, str]] = field(default_factory=set)
    acked: list[int] = field(default_factory=list)
    rejected: list[tuple[int, bool]] = field(default_factory=list)
    published: list[Published] = field(default_factory=list)
    slept: list[float] = field(default_factory=list)
    connections: list["FakeConnection"] = field(default_factory=list)
    streams: dict[str, list[StreamMessage]] = field(default_factory=dict)
    """What every stream a test appended to holds, oldest first."""
    behind: dict[str, int] = field(default_factory=dict)
    """Per stream, the last offset a replica that is behind holds yet: what is after it, no consumer sees."""
    caught_up_after_looks: int = 1
    """After how many looks at where a stream ends (a passive declaration) its replica is behind no more."""
    looks: list[str] = field(default_factory=list)
    """Every stream a listener asked the size of, to find where it ends."""
    _next_offsets: dict[str, int] = field(default_factory=dict)
    settled: threading.Event = field(default_factory=threading.Event)
    _pending: "queue.Queue[Delivery]" = field(default_factory=queue.Queue)
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

    def deliver(
        self, queue_name: str, body: bytes, headers: dict[str, object] | None = None, routing_key: str = ""
    ) -> None:
        """Puts a message, with its headers and the routing key it was sent with, on a queue, for its listener."""
        self._pending.put((queue_name, body, headers, routing_key))

    def cancel_consumers(self, queue_name: str) -> None:
        """What RabbitMQ does when a queue or stream is deleted: it cancels every consumer of it."""
        for connection in list(self.connections):
            for channel in connection.channels:
                channel.consumers.pop(queue_name, None)
                channel.cursors.pop(queue_name, None)

    def append(
        self, stream: str, body: bytes, *, routing_key: str = "auction.bid", message_id: str | None = None
    ) -> int:
        """Writes a message to a stream, as its exchange would route it there, and returns its offset."""
        with self._lock:
            offset = self._next_offsets.get(stream, 0)
            self._next_offsets[stream] = offset + 1
            self.streams.setdefault(stream, []).append(StreamMessage(offset, body, routing_key, message_id))
            return offset

    def delete_stream(self, stream: str) -> None:
        """Deletes a stream: its messages are gone, its consumers cancelled, and declared anew it counts from 0."""
        with self._lock:
            self.streams.pop(stream, None)
            self._next_offsets.pop(stream, None)
            self.behind.pop(stream, None)
            self.queues.pop(stream, None)
        self.cancel_consumers(stream)

    def retain_from(self, stream: str, first: int) -> None:
        """What a retention does: removes the messages of a stream before the offset `first`."""
        with self._lock:
            self.streams[stream] = [message for message in self.streams.get(stream, []) if message.offset >= first]

    def held(self, stream: str) -> list[StreamMessage]:
        """The messages of a stream a consumer can see: all of them, unless its replica is behind."""
        with self._lock:
            messages = list(self.streams.get(stream, []))
            limit = self.behind.get(stream)
        return messages if limit is None else [message for message in messages if message.offset <= limit]

    def size_of(self, stream: str) -> int:
        """How many messages a consumer can see, as a passive declaration tells; a replica catches up after it."""
        size = len(self.held(stream))
        with self._lock:
            self.looks.append(stream)
            if len(self.looks) >= self.caught_up_after_looks:
                self.behind.pop(stream, None)
        return size

    def start_of(self, stream: str, asked: object) -> int:
        """The first offset a consumer that asked for `asked` gets: `first`, `last`, `next` or an offset."""
        held = self.held(stream)
        end = held[-1].offset + 1 if held else 0
        if asked == "last":
            return max(end - 1, 0)
        if asked == "next":
            return end
        return asked if isinstance(asked, int) else 0

    def next_delivery(self, timeout: float) -> "Delivery | None":
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
        self.consumer_arguments: dict[str, dict[str, object]] = {}
        self.cursors: dict[str, int] = {}
        """Per stream this channel reads, the lowest offset it still gets."""

    def exchange_declare(self, exchange: str, exchange_type: str, durable: bool) -> None:
        self._broker.exchanges[exchange] = (exchange_type, durable)

    @property
    def consumer_tags(self) -> list[str]:
        """The consumers RabbitMQ did not cancel."""
        return list(self.consumers)

    def queue_declare(
        self, queue: str, durable: bool = False, arguments: dict[str, object] | None = None, *, passive: bool = False
    ) -> Any:
        if passive:
            if queue not in self._broker.queues:
                self.is_open = False
                raise ChannelClosedByBroker(404, f"NOT_FOUND - no queue '{queue}' in vhost '/'")
            return SimpleNamespace(method=SimpleNamespace(message_count=self._broker.size_of(queue)))
        assert durable
        wanted = arguments or {}
        declared = self._broker.queues.setdefault(queue, wanted)
        if differing := sorted(key for key in {*declared, *wanted} if declared.get(key) != wanted.get(key)):
            self.is_open = False
            raise ChannelClosedByBroker(
                406, f"PRECONDITION_FAILED - inequivalent arg '{differing[0]}' for queue '{queue}' in vhost '/'"
            )
        return None

    def queue_bind(self, queue: str, exchange: str, routing_key: str) -> None:
        self._broker.bindings.add((queue, exchange, routing_key))

    def basic_qos(self, prefetch_count: int) -> None:
        self.prefetch = prefetch_count

    def basic_consume(
        self, queue: str, on_message_callback: Consumer, arguments: dict[str, object] | None = None
    ) -> None:
        self.consumers[queue] = on_message_callback
        self.consumer_arguments[queue] = arguments or {}
        self.cursors[queue] = self._broker.start_of(queue, (arguments or {}).get("x-stream-offset"))

    def close(self) -> None:
        self.is_open = False
        self.consumers.clear()
        self.cursors.clear()

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
        if self._read_streams():
            return
        delivery = self._broker.next_delivery(timeout=time_limit)
        if delivery is None:
            return
        queue_name, body, headers, routing_key = delivery
        for channel in self.channels:
            if queue_name in channel.consumers:
                self._tags += 1
                method = SimpleNamespace(delivery_tag=self._tags, routing_key=routing_key)
                channel.consumers[queue_name](channel, method, SimpleNamespace(headers=headers), body)
                return
        self._broker.deliver(queue_name, body, headers, routing_key)
        time.sleep(time_limit)

    def _read_streams(self) -> bool:
        """Hands every consumer of a stream the messages from its offset on; tells whether there were any."""
        read = False
        for channel in list(self.channels):
            for stream in list(channel.cursors):
                for message in self._broker.held(stream):
                    if stream in channel.consumers and message.offset >= channel.cursors.get(stream, 0):
                        channel.cursors[stream] = message.offset + 1
                        self._hand(channel, stream, message)
                        read = True
        return read

    def _hand(self, channel: FakeChannel, stream: str, message: StreamMessage) -> None:
        self._tags += 1
        method = SimpleNamespace(delivery_tag=self._tags, routing_key=message.routing_key)
        properties = SimpleNamespace(headers={"x-stream-offset": message.offset}, message_id=message.message_id)
        channel.consumers[stream](channel, method, properties, message.body)

    def sleep(self, duration: float) -> None:
        """What `BlockingConnection.sleep` does: waits while it keeps the connection alive."""
        self._broker.slept.append(duration)
        time.sleep(duration)

    def close(self) -> None:
        self.is_open = False
