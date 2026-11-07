from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

RABBIT_LISTENER_MAPPING_ATTRIBUTE: Final = "__rabbit_listener_mapping__"

type MethodMarker = Callable[[Callable[..., Any]], Callable[..., Any]]


class InvalidRabbitListenerError(TypeError):
    """Raised while the application starts when a `@rabbit_listener` method cannot receive messages as declared.

    Like a broken controller, a broken listener must stop the start-up, not fail silently at the first message.
    """


class RejectAndDontRequeueError(Exception):
    """Raised by a listener to refuse a message for good, like Spring AMQP's `AmqpRejectAndDontRequeueException`.

    For a message that can never succeed, such as one that breaks the rules of the domain: RabbitMQ drops it (or
    moves it to a dead-letter queue, when the queue has one) instead of delivering it again and again.
    """


@dataclass(frozen=True, slots=True)
class RabbitListenerMapping:
    """Where a `@rabbit_listener` method receives from: its queue, bound to a topic exchange with a routing key."""

    queue: str
    exchange: str
    routing_key: str


def rabbit_listener(*, queue: str, exchange: str, routing_key: str) -> MethodMarker:
    """Makes a method of a component receive the messages of a queue, like Spring AMQP's `@RabbitListener`.

        @injectable
        class GameStartedListener:
            def __init__(self, start_game: StartGameUseCase) -> None: ...

            @rabbit_listener(queue="tictactoe.game-started", exchange="games", routing_key="game.tictactoe.started")
            def on_game_started(self, message: GameStartedMessage) -> None: ...

    When the application starts, the durable topic exchange, the durable queue and the binding are declared, as
    `@QueueBinding` does. The method takes one message: a pydantic model, a `dict` or `bytes`; the JSON body is
    converted to it. Returning acknowledges the message. `RejectAndDontRequeueError`, or a body that cannot be
    converted, refuses it for good. Any other exception is a failure that may pass, such as a database that is
    down: the message is tried again, three times in all, a second apart, and then refused for good.
    """
    mapping = RabbitListenerMapping(queue=queue, exchange=exchange, routing_key=routing_key)

    def mark(method: Callable[..., Any]) -> Callable[..., Any]:
        setattr(method, RABBIT_LISTENER_MAPPING_ATTRIBUTE, mapping)
        return method

    return mark
