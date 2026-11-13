"""A depot of two bounded contexts, each with its own migrations: a slice of one runs the migrations of both."""

from snakeboot.component_scan import application_root


@application_root
class DepotApplication:
    """The shelves hold the goods; the deliveries bring them. snakeboot's own tables come with the shelves' V1."""
