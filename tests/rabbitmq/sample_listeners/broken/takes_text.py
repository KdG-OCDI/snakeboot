"""A listener that takes a type no body becomes."""

from snakeboot.rabbitmq import rabbit_listener


class TakesText:
    """Stands in for a mistake: a body becomes a pydantic model, a dict or bytes, not text."""

    @rabbit_listener(queue="broken", exchange="games", routing_key="broken")
    def on_message(self, message: str) -> None:
        """Cannot listen."""
