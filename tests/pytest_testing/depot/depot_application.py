"""A depot of two bounded contexts, each with its own migrations: a module slice of one runs those of both."""

from snakeboot.component_scan import application_root


@application_root
class DepotApplication:
    """The shelves hold the goods; the deliveries bring them. snakeboot's own tables come with the shelves' V1."""
