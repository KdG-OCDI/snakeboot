"""The publisher delivers each event to the listener methods for its type, at once or after the commit."""

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
import wireup
from wireup import injectable

from snakeboot.events import (
    ApplicationEventPublisher,
    InvalidApplicationEventListenerError,
    application_event_listener,
    application_event_publisher_injectable,
    event_listener,
    transactional_event_listener,
)
from snakeboot.events.application_event_publisher_injectable import application_event_publisher
from snakeboot.testing import RecordingTransactionManager
from snakeboot.transaction import TransactionManagerRegistry, transactional


@dataclass(frozen=True)
class SomethingHappened:
    what: str


@dataclass(frozen=True)
class SomethingSpecialHappened(SomethingHappened):
    pass


@dataclass(frozen=True)
class SomethingElseHappened:
    what: str


class Diary:
    """Records what the listeners received, in order."""

    def __init__(self) -> None:
        self.entries: list[str] = []


@application_event_listener
class ImmediateListener:
    def __init__(self, diary: Diary) -> None:
        self._diary = diary

    @event_listener(SomethingHappened)
    def write_down(self, event: SomethingHappened) -> None:
        self._diary.entries.append(f"at once: {event.what}")


@application_event_listener
class AfterCommitListener:
    def __init__(self, diary: Diary) -> None:
        self._diary = diary

    @transactional_event_listener(SomethingHappened)
    def write_down(self, event: SomethingHappened) -> None:
        self._diary.entries.append(f"after commit: {event.what}")


@pytest.fixture
def transaction_manager() -> Iterator[RecordingTransactionManager]:
    manager = RecordingTransactionManager()
    TransactionManagerRegistry.install(manager)
    yield manager
    TransactionManagerRegistry.uninstall()


def test_an_event_listener_receives_the_event_at_once_inside_the_transaction(
    transaction_manager: RecordingTransactionManager,
) -> None:
    diary = Diary()
    publisher = ApplicationEventPublisher([ImmediateListener(diary)])
    seen_inside: list[list[str]] = []

    @transactional
    def change() -> None:
        publisher.publish(SomethingHappened("seat freed"))
        seen_inside.append(list(diary.entries))

    change()

    assert seen_inside == [["at once: seat freed"]]


def test_a_transactional_listener_receives_the_event_only_after_the_commit(
    transaction_manager: RecordingTransactionManager,
) -> None:
    diary = Diary()
    publisher = ApplicationEventPublisher([AfterCommitListener(diary)])
    seen_inside: list[list[str]] = []

    @transactional
    def change() -> None:
        publisher.publish(SomethingHappened("seat freed"))
        seen_inside.append(list(diary.entries))

    change()

    assert seen_inside == [[]]
    assert diary.entries == ["after commit: seat freed"]


def test_a_rolled_back_change_reaches_no_transactional_listener(
    transaction_manager: RecordingTransactionManager,
) -> None:
    diary = Diary()
    publisher = ApplicationEventPublisher([AfterCommitListener(diary)])

    @transactional
    def failing_change() -> None:
        publisher.publish(SomethingHappened("seat freed"))
        raise ConnectionError("database gone")

    with pytest.raises(ConnectionError):
        failing_change()

    assert diary.entries == []


def test_a_listener_for_a_base_class_receives_its_subclasses_and_nothing_else(
    transaction_manager: RecordingTransactionManager,
) -> None:
    diary = Diary()
    publisher = ApplicationEventPublisher([ImmediateListener(diary)])

    publisher.publish_all([SomethingSpecialHappened("special"), SomethingElseHappened("unrelated")])

    assert diary.entries == ["at once: special"]


def test_listeners_receive_events_in_a_stable_order_by_name(
    transaction_manager: RecordingTransactionManager,
) -> None:
    diary = Diary()
    publisher = ApplicationEventPublisher([ImmediateListener(diary), AfterCommitListener(diary)])

    publisher.publish_all([SomethingHappened("first"), SomethingHappened("second")])

    assert diary.entries == [
        "after commit: first",
        "at once: first",
        "after commit: second",
        "at once: second",
    ], "outside a transaction an after-commit listener runs at once; AfterCommitListener sorts first"


class WithoutListenerMethods:
    pass


class AsyncListener:
    @event_listener(SomethingHappened)
    async def write_down(self, event: SomethingHappened) -> None: ...


class GreedyListener:
    @event_listener(SomethingHappened)
    def write_down(self, event: SomethingHappened, extra: str) -> None: ...


@pytest.mark.parametrize(
    ("listener", "message"),
    [
        (WithoutListenerMethods(), "has no listener methods"),
        (AsyncListener(), "is async"),
        (GreedyListener(), "exactly one argument"),
    ],
    ids=["no methods", "async", "two arguments"],
)
def test_a_broken_listener_stops_the_start_up(listener: object, message: str) -> None:
    with pytest.raises(InvalidApplicationEventListenerError, match=message):
        ApplicationEventPublisher([listener])


def test_wireup_hands_every_listener_to_the_publisher(transaction_manager: RecordingTransactionManager) -> None:
    diary = Diary()

    @injectable
    def shared_diary() -> Diary:
        return diary

    container = wireup.create_sync_container(
        injectables=[shared_diary, application_event_publisher, ImmediateListener, AfterCommitListener]
    )
    container.get(ApplicationEventPublisher).publish(SomethingHappened("wired"))

    assert sorted(diary.entries) == ["after commit: wired", "at once: wired"]


def test_an_application_without_listeners_starts_and_publishing_tells_nobody() -> None:
    """Regression: wireup creates `Sequence[ApplicationEventListener]` only when a listener exists.

    An application with at least one listener never shows it; one without listeners could not
    start. Like Spring, a publisher without listeners is valid.
    """
    container = wireup.create_sync_container(injectables=[application_event_publisher])

    container.get(ApplicationEventPublisher).publish(SomethingHappened("nobody listens"))


def test_the_library_ships_the_publisher_so_applications_register_nothing() -> None:
    container = wireup.create_sync_container(injectables=[application_event_publisher_injectable])

    assert isinstance(container.get(ApplicationEventPublisher), ApplicationEventPublisher)
