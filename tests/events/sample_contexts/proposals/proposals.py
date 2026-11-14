"""Proposals: each follows the deadline of its call, and says so with an event."""

from dataclasses import dataclass
from datetime import date

from snakeboot.events import ApplicationEventPublisher
from snakeboot.stereotype import component, service


@dataclass(frozen=True)
class ProposalDeadlineMoved:
    proposal: str
    deadline: date


@component
class ProposalDeadlines:
    """The proposals of every call and their deadlines, in memory."""

    def __init__(self) -> None:
        self.by_proposal: dict[str, date | None] = {"ann's proposal": None, "bob's proposal": None}


@service
class FollowDeadlineUseCase:
    """Proposals' use case: every proposal of a call takes its deadline, and the context publishes that it moved."""

    def __init__(self, deadlines: ProposalDeadlines, events: ApplicationEventPublisher) -> None:
        self._deadlines = deadlines
        self._events = events

    def execute(self, deadline: date) -> None:
        for proposal in self._deadlines.by_proposal:
            self._deadlines.by_proposal[proposal] = deadline
            self._events.publish(ProposalDeadlineMoved(proposal, deadline))
