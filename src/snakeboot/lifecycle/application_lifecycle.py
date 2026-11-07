import logging
from collections.abc import Callable, Iterable

from snakeboot.lifecycle.lifecycle import Lifecycle

logger = logging.getLogger(__name__)


class ApplicationLifecycle:
    """Starts and stops every `Lifecycle` component of the application, like Spring's `DefaultLifecycleProcessor`.

    `start` starts them in ascending phase, then announces that the application is ready; when one fails, the ones
    already started are stopped again and the error stops the start-up. `stop` stops the started ones in the reverse
    order; a component that fails to stop is logged and the others still stop.

    The library registers it with wireup (`application_lifecycle_injectable`), with every component wireup found and
    the publication of `ApplicationReadyEvent` as `on_ready`; tests build it with what they need.
    """

    def __init__(self, components: Iterable[Lifecycle], on_ready: Callable[[], None]) -> None:
        self._components = sorted(components, key=lambda component: component.phase)
        self._on_ready = on_ready
        self._started: list[Lifecycle] = []

    def start(self) -> None:
        """Starts every component, then calls `on_ready`; raises what stopped the start-up."""
        try:
            for component in self._components:
                component.start()
                self._started.append(component)
            self._on_ready()
        except BaseException:
            self.stop()
            raise

    def stop(self) -> None:
        """Stops the started components, last started first."""
        while self._started:
            component = self._started.pop()
            try:
                component.stop()
            except Exception:
                logger.exception("%s did not stop cleanly", type(component).__qualname__)
