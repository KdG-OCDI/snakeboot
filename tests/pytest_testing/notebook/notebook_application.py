"""A notebook: writers sign in and write notes, anybody reads the last one; `@application_test` starts it."""

from snakeboot.component_scan import application_root


@application_root
class NotebookApplication:
    """Its section `[notes]`, a clock, a notice board, a cache and tokens of its own: what a test replaces."""
