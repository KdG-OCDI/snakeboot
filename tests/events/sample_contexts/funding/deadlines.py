"""Funding: it confirms the deadline of a call and lets the proposals follow it."""

from dataclasses import dataclass
from datetime import date

from wireup import injectable

from snakeboot.events import ApplicationEventPublisher, application_event_listener, event_listener
from tests.events.sample_contexts.proposals.proposals import FollowDeadlineUseCase


@dataclass(frozen=True)
class DeadlineConfirmed:
    call: str
    deadline: date


@injectable
class ConfirmDeadlineUseCase:
    """Funding's use case: a call's deadline is confirmed, which every context may hear."""

    def __init__(self, events: ApplicationEventPublisher) -> None:
        self._events = events

    def execute(self, call: str, deadline: date) -> None:
        self._events.publish(DeadlineConfirmed(call, deadline))


@application_event_listener
class ProposalsFollowConfirmedDeadlines:
    """A listener of funding that calls a use case of proposals, which publishes events of its own (#13).

    listener -> use case -> ApplicationEventPublisher: a cycle while the publisher took every listener.
    """

    def __init__(self, follow_deadline: FollowDeadlineUseCase) -> None:
        self._follow_deadline = follow_deadline

    @event_listener(DeadlineConfirmed)
    def on_deadline_confirmed(self, event: DeadlineConfirmed) -> None:
        self._follow_deadline.execute(event.deadline)
