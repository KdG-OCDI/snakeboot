"""Technical library: RabbitMQ through pika, like Spring AMQP's `@RabbitListener` and `RabbitTemplate`.

Extra `rabbitmq`.

    @injectable                                                    # a component, like @Component
    class GameStartedListener:
        def __init__(self, start_game: StartGameUseCase) -> None: ...

        @rabbit_listener(queue="tictactoe.game-started", exchange="games", routing_key="game.tictactoe.started")
        def on_game_started(self, message: GameStartedMessage) -> None: ...   # a pydantic model, a dict or bytes

    @injectable(as_type=PlatformEventPublisherPort)                # an adapter that sends
    class RabbitMqPlatformEventPublisherAdapter(PlatformEventPublisherPort):
        def __init__(self, rabbit: RabbitTemplate) -> None: ...

The broker comes from `[rabbitmq]`; without that section the application has neither listeners nor a template. The
listeners are a `Lifecycle` component: they consume while an ASGI server serves the application or while
`run_lifecycle` runs it, and `[rabbitmq.listener] auto_startup = false` keeps a process from consuming.
"""

from snakeboot.rabbitmq.in_process_rabbit_template import InProcessRabbitTemplate, RefusedMessage, SentMessage
from snakeboot.rabbitmq.message_conversion import MessageConversionError
from snakeboot.rabbitmq.rabbit_connection_factory import RabbitConnectionFactory
from snakeboot.rabbitmq.rabbit_listener import (
    InvalidRabbitListenerError,
    RabbitListenerMapping,
    RejectAndDontRequeueError,
    rabbit_listener,
)
from snakeboot.rabbitmq.rabbit_listener_containers import ListenerTiming, RabbitListenerContainers
from snakeboot.rabbitmq.rabbit_template import AmqpPublishError, RabbitTemplate

__all__ = [
    "AmqpPublishError",
    "InProcessRabbitTemplate",
    "InvalidRabbitListenerError",
    "ListenerTiming",
    "MessageConversionError",
    "RabbitConnectionFactory",
    "RabbitListenerContainers",
    "RabbitListenerMapping",
    "RabbitTemplate",
    "RefusedMessage",
    "RejectAndDontRequeueError",
    "SentMessage",
    "rabbit_listener",
]
