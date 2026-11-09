"""Registers the event publication registry and its resubmitter with wireup.

`snakeboot.boot` adds this module, and the one of its table, to the container when the application has `[database]`,
like Spring Modulith's JDBC starter: the `@application_module_listener` methods then receive their events at least once.
"""

from typing import Annotated

from wireup import Inject, injectable

from snakeboot.actuator import MeterRegistry
from snakeboot.configuration import CONFIGURATION_KEY, Configuration, EventsProperties
from snakeboot.event_publication.event_publication_record import EventPublicationRecords
from snakeboot.event_publication.event_publication_resubmitter import EventPublicationResubmitter
from snakeboot.event_publication.persistent_event_publication_registry import PersistentEventPublicationRegistry
from snakeboot.event_publication.publication_timing import PublicationTiming
from snakeboot.events import ApplicationEventPublisher, EventPublicationRegistry
from snakeboot.lifecycle import Lifecycle


@injectable
def publication_timing(configuration: Annotated[Configuration, Inject(config=CONFIGURATION_KEY)]) -> PublicationTiming:
    """Provides when the registry delivers again: `[events]`, or snakeboot's own timing without the table."""
    present = EventsProperties in configuration.sections
    return PublicationTiming.of(configuration.get(EventsProperties) if present else None)


@injectable(as_type=EventPublicationRegistry)
def event_publication_registry(records: EventPublicationRecords, timing: PublicationTiming) -> EventPublicationRegistry:
    """Provides the registry in the application's database."""
    return PersistentEventPublicationRegistry(records, timing=timing)


@injectable(as_type=Lifecycle, qualifier="snakeboot.event_publication.EventPublicationResubmitter")
def event_publication_resubmitter(
    publisher: ApplicationEventPublisher,
    registry: EventPublicationRegistry,
    meters: MeterRegistry,
    *,
    timing: PublicationTiming,
) -> Lifecycle:
    """Provides what delivers the failed and the lost publications again while the application runs."""
    return EventPublicationResubmitter(publisher, registry, meters, every=timing.resubmit_every)
