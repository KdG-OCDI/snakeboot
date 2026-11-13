"""A listener between modules: it needs the event publication registry's table."""

from snakeboot.events import application_event_listener, application_module_listener


@application_event_listener
class InvoiceListener:
    @application_module_listener(dict)
    def on_order(self, event: dict[str, object]) -> None:
        """Hears an order from another module, through the outbox."""
