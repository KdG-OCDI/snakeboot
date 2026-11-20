from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from snakeboot.events.stream_offsets import STREAM_CONSUMER_ATTRIBUTE
from snakeboot.rabbitmq.rabbit_listener import binding_keys
from snakeboot.rabbitmq.topic_routing import routes

type MethodMarker = Callable[[Callable[..., Any]], Callable[..., Any]]


@dataclass(frozen=True, slots=True)
class RabbitStreamListenerMapping:
    """Where a `@rabbit_stream_listener` method reads from: a RabbitMQ stream, bound to a topic exchange with one
    routing key or more."""

    stream: str
    exchange: str
    routing_keys: tuple[str, ...]

    def matches(self, routing_key: str) -> bool:
        """Tells whether the method handles a message sent with `routing_key`: one of its routing keys matches it."""
        return any(routes(binding_key, routing_key) for binding_key in self.routing_keys)


def rabbit_stream_listener(*, stream: str, exchange: str, routing_key: str | Sequence[str]) -> MethodMarker:
    """Makes a method of a component read a RabbitMQ stream: every message in it, from the first one on.

    A queue forgets a message once a listener took it; a stream keeps every message, like a Kafka topic, and each
    consumer reads it at its own pace. So a new service builds its projection of another's events from their whole
    history, instead of from a shared database or an export of one, and keeps it up to date in real time:

        @component
        class BidProjection:
            def __init__(self, bids: BidStatistics) -> None: ...

            @rabbit_stream_listener(stream="auctions.history", exchange="auctions", routing_key="auction.#")
            def on_auction_event(self, message: dict[str, Any]) -> None: ...

    When the application starts, the durable topic exchange, the stream (a durable queue of type `stream`) and the
    binding are declared; a stream declared already with arguments of its own, such as `x-max-age`, is taken as it
    is. The method takes one message, as a `@rabbit_listener` does: a pydantic model, a `dict` or `bytes`. It claims
    the message's offset and handles the message in one transaction: with `[database]` the offset is a row of
    `snakeboot_stream_offset`, so after a restart the method reads on from the next message, without a gap and without
    handling one twice, and of the processes of the service that all read the stream, one handles each message.
    Without a database the offset lives in memory, and the method reads the stream from the start again at every
    start, building its projection in memory anew. The offset belongs to the method, by its name
    `module.Class.method`: renaming it reads the stream from the start again. `routing_key` may be a tuple, as for a
    `@rabbit_listener`: the stream is bound once for each key, and the method handles what any of them matches.

    A stream only keeps what reached it: what the exchange routed before the stream was declared is lost. So start
    the consumer once before the events it needs, or declare the stream with RabbitMQ's definitions. RabbitMQ keeps a
    stream for ever unless a policy limits it (`max-age`, `max-length-bytes`). The stream holds what the bindings of
    all its listeners route to it; the method handles what its own `routing_key` matches.

    A stream deleted and declared anew counts from 0 again, so the offset the method saved is one of a stream that is
    gone. The method finds that out and reads the new stream from its start, like Kafka's
    `auto.offset.reset=earliest`, with a warning: with its offset it saves a fingerprint of the message, and when it
    reads on it asks for that message again. Another message at that offset, or a stream that ends before it, is
    another stream. What the method built from the old stream stays in its projection. A new stream that holds the
    very same message, without a message id, at the very same offset goes unnoticed. A retention that removed
    messages the method had not handled yet is a warning, and the method reads on from the oldest one left.

    `RejectAndDontRequeueError`, or a body that cannot be converted, skips the message for good. Another failure,
    such as a database that is down, is tried again as `[rabbitmq.listener.retry]` says; then the method stops reading
    and reads on from the same message after a while, so its projection never misses one.
    """
    mapping = RabbitStreamListenerMapping(
        stream=stream,
        exchange=exchange,
        routing_keys=binding_keys(routing_key, f"@rabbit_stream_listener(stream={stream!r})"),
    )

    def mark(method: Callable[..., Any]) -> Callable[..., Any]:
        setattr(method, STREAM_CONSUMER_ATTRIBUTE, mapping)
        return method

    return mark
