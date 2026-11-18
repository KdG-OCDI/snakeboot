"""Technical library: RabbitMQ through pika, like Spring AMQP's `@RabbitListener` and `RabbitTemplate`.

Extra `rabbitmq`.

    @component                                                     # a component, like @Component
    class GameStartedListener:
        def __init__(self, start_game: StartGameUseCase) -> None: ...

        @rabbit_listener(queue="tictactoe.game-started", exchange="games", routing_key="game.tictactoe.started")
        def on_game_started(self, message: GameStartedMessage) -> None: ...   # a pydantic model, a dict or bytes

    @component(as_type=PlatformEventPublisherPort)                 # an adapter that sends
    class RabbitMqPlatformEventPublisherAdapter(PlatformEventPublisherPort):
        def __init__(self, rabbit: RabbitTemplate) -> None: ...

The broker comes from `[rabbitmq]`; without that section the application has neither listeners nor a template. The
listeners are a `Lifecycle` component: they consume while an ASGI server serves the application or while
`run_lifecycle` runs it, and `[rabbitmq.listener] auto_startup = false` keeps a process from consuming. A failing
message is tried again as `[rabbitmq.listener.retry]` says, then refused: dropped, or kept in `<queue>.dead-letter`
for a listener with `@rabbit_listener(..., dead_letter=True)`.

    @rabbit_stream_listener(stream="auctions.history", exchange="auctions", routing_key="auction.#")
    def on_auction_event(self, message: AuctionEvent) -> None: ...    # every message ever, from the first one

A stream listener reads a RabbitMQ stream, which keeps every message: from the start, to build a projection from the
history, then on from the last message it handled, whose offset it saves in the transaction that handled it. With
`[rabbitmq]`, every event of an `@externalized` class goes to its exchange as well, through the event publication
registry (`EventExternalizer`), like Spring Modulith's event externalization.
"""

from snakeboot.rabbitmq.event_externalizer import EventExternalizer
from snakeboot.rabbitmq.in_process_rabbit_template import InProcessRabbitTemplate, RefusedMessage, SentMessage
from snakeboot.rabbitmq.listener_declaration import AmqpDeclarationError
from snakeboot.rabbitmq.listener_timing import ListenerTiming
from snakeboot.rabbitmq.message_conversion import MessageConversionError
from snakeboot.rabbitmq.rabbit_connection_factory import RabbitConnectionFactory
from snakeboot.rabbitmq.rabbit_listener import (
    InvalidRabbitListenerError,
    RabbitListenerMapping,
    RejectAndDontRequeueError,
    rabbit_listener,
)
from snakeboot.rabbitmq.rabbit_listener_containers import RabbitListenerContainers
from snakeboot.rabbitmq.rabbit_stream_listener import RabbitStreamListenerMapping, rabbit_stream_listener
from snakeboot.rabbitmq.rabbit_stream_listener_containers import RabbitStreamListenerContainers
from snakeboot.rabbitmq.rabbit_template import AmqpPublishError, RabbitTemplate

__all__ = [
    "AmqpDeclarationError",
    "AmqpPublishError",
    "EventExternalizer",
    "InProcessRabbitTemplate",
    "InvalidRabbitListenerError",
    "ListenerTiming",
    "MessageConversionError",
    "RabbitConnectionFactory",
    "RabbitListenerContainers",
    "RabbitListenerMapping",
    "RabbitStreamListenerContainers",
    "RabbitStreamListenerMapping",
    "RabbitTemplate",
    "RefusedMessage",
    "RejectAndDontRequeueError",
    "SentMessage",
    "rabbit_listener",
    "rabbit_stream_listener",
]
