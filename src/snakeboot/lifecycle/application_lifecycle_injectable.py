"""Registers the one ApplicationLifecycle with wireup, so no application has to.

Part of snakeboot's auto-configuration (`SNAKEBOOT_AUTO_CONFIGURATION`): every application has a lifecycle, with or
without components, and announces `ApplicationReadyEvent` once it has started.
"""

from collections.abc import Sequence
from functools import partial

from wireup import injectable

from snakeboot.events import ApplicationEventPublisher
from snakeboot.lifecycle.application_lifecycle import ApplicationLifecycle
from snakeboot.lifecycle.application_ready_event import ApplicationReadyEvent
from snakeboot.lifecycle.lifecycle import Lifecycle


@injectable
def application_lifecycle(
    events: ApplicationEventPublisher, components: Sequence[Lifecycle] = ()
) -> ApplicationLifecycle:
    """Provides the lifecycle of every `Lifecycle` component wireup knows, or of none.

    As with the listeners of the publisher, the default keeps an application without components starting.
    """
    return ApplicationLifecycle(components, on_ready=partial(events.publish, ApplicationReadyEvent()))
