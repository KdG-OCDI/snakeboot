"""What a `@rabbit_listener` declares on the broker, like Spring AMQP's `RabbitAdmin`: exchange, queues and binding."""

import json
import re
from typing import Any, Final

from pika.exceptions import ChannelClosedByBroker

from snakeboot.rabbitmq.rabbit_listener import RabbitListenerMapping

_PRECONDITION_FAILED: Final = 406
_DEAD_LETTER_ARGUMENT: Final = "x-dead-letter"


class AmqpDeclarationError(RuntimeError):
    """RabbitMQ refused to declare the exchange, a queue or the binding of a `@rabbit_listener` method.

    Raised while the application starts, so a listener that could never consume stops the start-up instead of
    trying again and again. Most often a queue that exists with other arguments: RabbitMQ does not change those of a
    queue, so a queue that gets a dead-letter queue, or loses one, must be migrated; the message says how.
    """


def declare_listener_queue(channel: Any, listener: str, mapping: RabbitListenerMapping) -> None:
    """Declares the durable topic exchange, the dead-letter queue (if any), the durable queue and its binding.

    Raises AmqpDeclarationError, naming `listener`, when RabbitMQ refuses one; RabbitMQ then closed the channel.
    """
    try:
        _declare(channel, mapping)
    except ChannelClosedByBroker as error:
        raise AmqpDeclarationError(_refusal(listener, mapping, error)) from error


def _declare(channel: Any, mapping: RabbitListenerMapping) -> None:
    channel.exchange_declare(exchange=mapping.exchange, exchange_type="topic", durable=True)
    dead_lettering = None
    if mapping.dead_letter_queue is not None:
        # The dead-letter queue first, so no message refused for good finds it missing.
        channel.queue_declare(queue=mapping.dead_letter_queue, durable=True)
        dead_lettering = {"x-dead-letter-exchange": "", "x-dead-letter-routing-key": mapping.dead_letter_queue}
    channel.queue_declare(queue=mapping.queue, durable=True, arguments=dead_lettering)
    channel.queue_bind(queue=mapping.queue, exchange=mapping.exchange, routing_key=mapping.routing_key)


def _refusal(listener: str, mapping: RabbitListenerMapping, error: ChannelClosedByBroker) -> str:
    refusal = f"RabbitMQ refused what {listener} declares: {error.reply_text}."
    if error.reply_code != _PRECONDITION_FAILED:
        return refusal
    if _DEAD_LETTER_ARGUMENT not in error.reply_text:
        return (
            f"{refusal} An exchange or a queue that exists keeps the type, durability and arguments it was declared "
            "with: delete it and start again, or declare it as it is."
        )
    return f"{refusal} {_dead_letter_migration(mapping)}"


def _dead_letter_migration(mapping: RabbitListenerMapping) -> str:
    queue = mapping.queue
    migration = (
        "A queue that exists keeps the arguments it was declared with, so it cannot get a dead-letter queue or lose "
        f"one. Either delete the queue while it is empty and start again, so the start-up declares it anew: "
        f"rabbitmqctl delete_queue {queue} --if-empty."
    )
    if mapping.dead_letter_queue is None:
        return f"{migration} Or give the listener dead_letter=True again."
    policy = json.dumps({"dead-letter-exchange": "", "dead-letter-routing-key": mapping.dead_letter_queue})
    return (
        f"{migration} Or keep the queue, leave out dead_letter=True and give the queue its dead-letter queue through "
        f"a policy: rabbitmqctl set_policy {mapping.dead_letter_queue} '^{re.escape(queue)}$' '{policy}' "
        f"--apply-to queues (this start declared the queue {mapping.dead_letter_queue} already)."
    )
