"""Registers the one ApplicationEventPublisher with wireup, so no application has to.

Spring always provides an `ApplicationEventPublisher`, with or without listeners; this
module is the library's equivalent. A component scan that covers the library finds it;
otherwise an application lists this module among wireup's injectables.
"""

from collections.abc import Sequence

from wireup import injectable

from snakeboot.events.application_event_listener import ApplicationEventListener
from snakeboot.events.application_event_publisher import ApplicationEventPublisher


@injectable
def application_event_publisher(listeners: Sequence[ApplicationEventListener] = ()) -> ApplicationEventPublisher:
    """Provides the publisher, connected to every `@application_event_listener` wireup knows.

    Wireup only creates `Sequence[ApplicationEventListener]` when at least one listener
    exists. Without the default, an application without listeners would not even start;
    with it, wireup leaves the parameter out and the publisher simply has nobody to tell.
    """
    return ApplicationEventPublisher(listeners)
