from snakeboot.component_scan import application_root


@application_root
class OutboxApplication:
    """A service that places orders and invoices them in a module of its own."""
