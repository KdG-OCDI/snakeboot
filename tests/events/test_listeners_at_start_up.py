"""The start-up builds every listener once the container exists and registers it with the publisher: a listener may
depend on a use case that publishes events, and one that cannot be built stops the start, not the first event. A spy
is in place before the listeners are built, so it records what they call."""

from collections.abc import Iterator
from datetime import date

import pytest

from snakeboot.application import ApplicationContext
from snakeboot.boot import CONDITIONAL_MODULES
from snakeboot.boot.testing import SPY, TestApplication
from snakeboot.events import ApplicationEventPublisher
from snakeboot.testing import Autowired, ModuleSlice, PublishedEvents, SpyComponent, application_test, verify
from tests.command_line.sample_commands.applications import ApplicationWithoutCommands
from tests.events.sample_contexts.contexts_application import ContextsApplication
from tests.events.sample_contexts.funding.deadlines import ConfirmDeadlineUseCase, DeadlineConfirmed
from tests.events.sample_contexts.proposals.proposals import (
    FollowDeadlineUseCase,
    ProposalDeadlineMoved,
    ProposalDeadlines,
)
from tests.events.sample_unbuildable_listener.unbuildable_listener_application import (
    SignedUp,
    UnbuildableListenerApplication,
)

DEADLINE = date(2027, 3, 1)


@pytest.fixture
def contexts() -> Iterator[ApplicationContext]:
    context = ApplicationContext.start(ContextsApplication, CONDITIONAL_MODULES)
    yield context
    context.close()


def test_a_listener_may_inject_a_use_case_of_another_context_that_publishes_events(
    contexts: ApplicationContext,
) -> None:
    """Regression (#13): listener -> use case -> publisher -> every listener was a cycle, and the start failed."""
    contexts.get(ConfirmDeadlineUseCase).execute("horizon", DEADLINE)

    assert contexts.get(ProposalDeadlines).by_proposal == {"ann's proposal": DEADLINE, "bob's proposal": DEADLINE}


def test_the_events_of_the_use_case_a_listener_calls_reach_every_listener_too() -> None:
    with TestApplication.start(ContextsApplication) as application:
        application.get(ConfirmDeadlineUseCase).execute("horizon", DEADLINE)

        assert list(application.published_events) == [
            DeadlineConfirmed("horizon", DEADLINE),
            ProposalDeadlineMoved("ann's proposal", DEADLINE),
            ProposalDeadlineMoved("bob's proposal", DEADLINE),
        ]


def test_the_listeners_are_built_with_the_test_components() -> None:
    deadlines = ProposalDeadlines()

    with TestApplication.start(ContextsApplication, test_components={ProposalDeadlines: deadlines}) as application:
        application.get(ConfirmDeadlineUseCase).execute("horizon", DEADLINE)

    assert set(deadlines.by_proposal.values()) == {DEADLINE}


def test_a_spy_records_what_a_listener_calls() -> None:
    with TestApplication.start(ContextsApplication, {FollowDeadlineUseCase: SPY}) as application:
        application.get(ConfirmDeadlineUseCase).execute("horizon", DEADLINE)

        verify(application.get(FollowDeadlineUseCase).execute).called_once_with(DEADLINE)
        assert set(application.get(ProposalDeadlines).by_proposal.values()) == {DEADLINE}, "and does what it wraps"


def test_a_spy_in_a_slice_wraps_the_component_the_slice_holds() -> None:
    proposals = ModuleSlice(("tests.events.sample_contexts.proposals",))

    with TestApplication.start(ContextsApplication, {FollowDeadlineUseCase: SPY}, only=proposals) as application:
        application.get(FollowDeadlineUseCase).execute(DEADLINE)

        verify(application.get(FollowDeadlineUseCase).execute).called_once_with(DEADLINE)


@application_test(application=ContextsApplication)
def test_a_spy_component_records_what_a_listener_calls(
    confirm_deadline: Autowired[ConfirmDeadlineUseCase], follow_deadline: SpyComponent[FollowDeadlineUseCase]
) -> None:
    confirm_deadline.execute("horizon", DEADLINE)

    verify(follow_deadline.execute).called_once_with(DEADLINE)


@application_test(application=ContextsApplication)
class TestASpyComponentOfWhatAListenerCalls:
    confirm_deadline: Autowired[ConfirmDeadlineUseCase]
    follow_deadline: SpyComponent[FollowDeadlineUseCase]
    published: Autowired[PublishedEvents]

    def test_the_spy_records_the_call_and_the_use_case_still_publishes(self) -> None:
        self.confirm_deadline.execute("horizon", DEADLINE)

        verify(self.follow_deadline.execute).called_once_with(DEADLINE)
        assert len(self.published.of_type(ProposalDeadlineMoved)) == 2


def test_a_listener_whose_dependency_cannot_be_built_stops_the_start() -> None:
    with pytest.raises(ConnectionError, match="The mail server is unreachable") as raised:
        ApplicationContext.start(UnbuildableListenerApplication, CONDITIONAL_MODULES)

    assert raised.value.__notes__ == ["Raised while the application started and built its event listeners."]


def test_a_test_application_with_that_listener_does_not_start_either() -> None:
    with pytest.raises(ConnectionError, match="The mail server is unreachable"):
        TestApplication.start(UnbuildableListenerApplication)


def test_a_start_that_failed_leaves_nothing_behind() -> None:
    context = ApplicationContext.of(UnbuildableListenerApplication, CONDITIONAL_MODULES)

    with pytest.raises(ConnectionError):
        context.refresh()

    assert not context.started


def test_an_application_without_listeners_starts_and_publishing_tells_nobody() -> None:
    context = ApplicationContext.start(ApplicationWithoutCommands, CONDITIONAL_MODULES)
    publisher = context.get(ApplicationEventPublisher)

    publisher.publish(SignedUp("ann"))

    assert not publisher.has_application_module_listeners
    context.close()
