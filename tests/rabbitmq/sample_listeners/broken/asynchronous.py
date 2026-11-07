"""An async listener, which a listener thread cannot await."""

from snakeboot.rabbitmq import rabbit_listener


class Asynchronous:
    """Stands in for a mistake: listeners are synchronous."""

    @rabbit_listener(queue="broken", exchange="games", routing_key="broken")
    async def on_message(self, message: bytes) -> None:
        """Cannot listen."""
