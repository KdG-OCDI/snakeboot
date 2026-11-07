"""A listener that wants more than the message."""

from snakeboot.rabbitmq import rabbit_listener


class TwoArguments:
    """Stands in for a mistake: a listener takes exactly one message."""

    @rabbit_listener(queue="broken", exchange="games", routing_key="broken")
    def on_message(self, message: bytes, extra: bytes) -> None:
        """Cannot listen."""
