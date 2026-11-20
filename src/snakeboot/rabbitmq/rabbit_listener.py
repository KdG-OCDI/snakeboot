from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from snakeboot.rabbitmq.topic_routing import routes

RABBIT_LISTENER_MAPPING_ATTRIBUTE: Final = "__rabbit_listener_mapping__"
DEAD_LETTER_SUFFIX: Final = ".dead-letter"
"""What the name of a listener's queue gets to name its dead-letter queue: `tictactoe.game-started.dead-letter`."""

type MethodMarker = Callable[[Callable[..., Any]], Callable[..., Any]]


class InvalidRabbitListenerError(TypeError):
    """Raised while the application starts when a `@rabbit_listener` method cannot receive messages as declared.

    Like a broken controller, a broken listener must stop the start-up, not fail silently at the first message.
    """


class RejectAndDontRequeueError(Exception):
    """Raised by a listener to refuse a message for good, like Spring AMQP's `AmqpRejectAndDontRequeueException`.

    For a message that can never succeed, such as one that breaks the rules of the domain: it is not tried again, and
    RabbitMQ drops it (or moves it to the dead-letter queue, when the listener has one) instead of delivering it again
    and again.
    """


@dataclass(frozen=True, slots=True)
class RabbitListenerMapping:
    """Where a `@rabbit_listener` method receives from: its queue, bound to a topic exchange with one routing key or
    more.

    `dead_letter_queue` is where RabbitMQ moves a message the method refuses for good, or None: RabbitMQ drops it.
    """

    queue: str
    exchange: str
    routing_keys: tuple[str, ...]
    dead_letter_queue: str | None

    def matches(self, routing_key: str) -> bool:
        """Tells whether the exchange routes a message sent with `routing_key` to the queue: a binding matches it."""
        return any(routes(binding_key, routing_key) for binding_key in self.routing_keys)


def binding_keys(routing_key: str | Sequence[str], listener: str) -> tuple[str, ...]:
    """Returns the routing keys a listener binds its queue or stream with: the one given, or each of several.

    Raises InvalidRabbitListenerError, naming `listener`, for an empty sequence: a queue nothing would route to.
    """
    keys = (routing_key,) if isinstance(routing_key, str) else tuple(routing_key)
    if not keys:
        raise InvalidRabbitListenerError(f"{listener} names no routing key; give one, or a tuple of several.")
    return keys


def rabbit_listener(
    *, queue: str, exchange: str, routing_key: str | Sequence[str], dead_letter: bool = False
) -> MethodMarker:
    """Makes a method of a component receive the messages of a queue, like Spring AMQP's `@RabbitListener`.

        @component
        class GameStartedListener:
            def __init__(self, start_game: StartGameUseCase) -> None: ...

            @rabbit_listener(
                queue="tictactoe.game-started",
                exchange="games",
                routing_key="game.tictactoe.started",
                dead_letter=True,
            )
            def on_game_started(self, message: GameStartedMessage) -> None: ...

    When the application starts, the durable topic exchange, the durable queue and the binding are declared, as
    `@QueueBinding` does. `routing_key` may also be a tuple, as `@QueueBinding(key = {...})` takes several keys: the
    queue is bound once for each, so it receives what any of them matches, and the one method takes it all, telling
    the messages apart by their body. A key left out later stays bound, as with Spring's `RabbitAdmin`, which only
    adds: unbind it on the broker (`rabbitmqctl` or the management UI).

    The method takes one message: a pydantic model, a `dict` or `bytes`; the JSON body is converted to it. It may
    take minutes, as one that waits for a language model does: meanwhile the connection keeps answering the
    broker's heartbeats, so RabbitMQ hands the message to no other consumer. Returning acknowledges the message.
    `RejectAndDontRequeueError`, or a body that cannot be converted, refuses it for good at once. Any other exception
    is a failure that may pass, such as a database that is down: the message is tried again as
    `[rabbitmq.listener.retry]` says (without it three times in all, a second apart), and then refused for good.

    RabbitMQ drops a message refused for good, unless the listener has a dead-letter queue: `dead_letter=True`
    declares the durable queue `<queue>.dead-letter` and gives the queue the arguments `x-dead-letter-exchange` and
    `x-dead-letter-routing-key` that move such a message there, as Spring's `RejectAndDontRequeueRecoverer` does with
    `@Queue(arguments = ...)`. RabbitMQ does not change the arguments of a queue that exists: turning `dead_letter`
    on or off for one stops the start-up, with how to migrate it.
    """
    dead_letter_queue = f"{queue}{DEAD_LETTER_SUFFIX}" if dead_letter else None
    mapping = RabbitListenerMapping(
        queue=queue,
        exchange=exchange,
        routing_keys=binding_keys(routing_key, f"@rabbit_listener(queue={queue!r})"),
        dead_letter_queue=dead_letter_queue,
    )

    def mark(method: Callable[..., Any]) -> Callable[..., Any]:
        setattr(method, RABBIT_LISTENER_MAPPING_ATTRIBUTE, mapping)
        return method

    return mark
