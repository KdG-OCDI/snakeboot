import logging
import threading
from datetime import timedelta
from typing import Final, override

from snakeboot.actuator import MeterRegistry
from snakeboot.event_publication.publication_timing import RESUBMIT_EVERY
from snakeboot.events import ApplicationEventPublisher, EventPublicationRegistry
from snakeboot.lifecycle import Lifecycle
from snakeboot.tracing import TraceContext

logger = logging.getLogger(__name__)

SHUTDOWN_SECONDS: Final = 5.0
"""How long `stop` waits for a resubmission in hand to finish."""

INCOMPLETE_METRIC: Final = "snakeboot_event_publications_incomplete"
"""The gauge of the publications not delivered yet: a number that keeps growing means a listener keeps failing."""


class EventPublicationResubmitter(Lifecycle, component=False):
    """Delivers the publications that failed or were lost again, like Spring Modulith's
    `republish-outstanding-events-on-restart` together with a scheduled `resubmitIncompletePublications`.

    It starts with the application, resubmits at once (what a stopped process left), then every `every` (`[events]
    resubmit_every`), on a thread of its own; the deliveries themselves run on the publisher's executor. It
    registers the gauge `snakeboot_event_publications_incomplete`. An application without
    `@application_module_listener` methods starts no thread and asks the database nothing.
    """

    def __init__(
        self,
        publisher: ApplicationEventPublisher,
        registry: EventPublicationRegistry,
        meters: MeterRegistry,
        *,
        every: timedelta = RESUBMIT_EVERY,
    ) -> None:
        self._publisher = publisher
        self._every = every
        self._registry = registry
        self._meters = meters
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        """Whether its thread runs."""
        return self._thread is not None and self._thread.is_alive()

    @override
    def start(self) -> None:
        if not self._publisher.has_application_module_listeners:
            return
        self._meters.gauge(INCOMPLETE_METRIC, "Event publications not delivered yet", self._registry.count_incomplete)
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name="snakeboot-event-publications", daemon=True)
        self._thread.start()

    @override
    def stop(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=SHUTDOWN_SECONDS)
            self._thread = None

    def _run(self) -> None:
        while True:
            self._resubmit()
            if self._stopping.wait(self._every.total_seconds()):
                return

    def _resubmit(self) -> None:
        with TraceContext.started():
            try:
                if resubmitted := self._publisher.resubmit_incomplete():
                    logger.info("Resubmitted %d event publications", resubmitted)
            except Exception:
                logger.exception("The incomplete event publications could not be resubmitted; trying again later")
