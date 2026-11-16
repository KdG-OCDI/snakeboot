"""The publisher delivers each event to the listener methods for its type, at once or after the commit."""

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
import wireup

from snakeboot.events import (
    ApplicationEventPublisher,
    InvalidApplicationEventListenerError,
    application_event_listener,
    application_event_publisher_injectable,
    event_listener,
    transactional_event_listener,
)
from snakeboot.events.application_event_publisher_injectable import (
    application_event_publisher,
    event_listener_method_processor,
)
from snakeboot.events.event_listener_method_processor import EventListenerMethodProcessor
from snakeboot.stereotype import bean, service
from snakeboot.testing import RecordingTransactionManager
from snakeboot.transaction import TransactionManagerRegistry, TransactionPhase, transactional


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


@application_event_listener
class FallbackListener:
    def __init__(self, diary: Diary) -> None:
        self._diary = diary

    @transactional_event_listener(SomethingHappened, fallback_execution=True)
    def write_down(self, event: SomethingHappened) -> None:
        self._diary.entries.append(f"fallback: {event.what}")


@application_event_listener
class PhasesListener:
    def __init__(self, diary: Diary) -> None:
        self._diary = diary

    @transactional_event_listener(SomethingHappened, phase=TransactionPhase.BEFORE_COMMIT)
    def before_commit(self, event: SomethingHappened) -> None:
        self._diary.entries.append(f"before commit: {event.what}")

    @transactional_event_listener(SomethingHappened, phase=TransactionPhase.AFTER_ROLLBACK)
    def after_rollback(self, event: SomethingHappened) -> None:
        self._diary.entries.append(f"after rollback: {event.what}")

    @transactional_event_listener(SomethingHappened, phase=TransactionPhase.AFTER_COMPLETION)
    def after_completion(self, event: SomethingHappened) -> None:
        self._diary.entries.append(f"after completion: {event.what}")


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
    publisher = ApplicationEventPublisher([ImmediateListener(diary), FallbackListener(diary)])

    publisher.publish_all([SomethingHappened("first"), SomethingHappened("second")])

    assert diary.entries == [
        "fallback: first",
        "at once: first",
        "fallback: second",
        "at once: second",
    ], "outside a transaction a fallback listener runs at once; FallbackListener sorts first"


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


def test_the_start_up_hands_every_listener_wireup_knows_to_the_publisher(
    transaction_manager: RecordingTransactionManager,
) -> None:
    diary = Diary()

    @bean
    def shared_diary() -> Diary:
        return diary

    container = wireup.create_sync_container(
        injectables=[
            shared_diary,
            application_event_publisher,
            event_listener_method_processor,
            ImmediateListener,
            AfterCommitListener,
        ]
    )
    container.get(EventListenerMethodProcessor).register_listeners()
    with transaction_manager.atomic():
        container.get(ApplicationEventPublisher).publish(SomethingHappened("wired"))

    assert sorted(diary.entries) == ["after commit: wired", "at once: wired"]


@dataclass(frozen=True)
class SomethingFollowedUp:
    what: str


@service
class FollowUpUseCase:
    """Publishes an event of its own: what a listener between two bounded contexts calls."""

    def __init__(self, events: ApplicationEventPublisher) -> None:
        self._events = events

    def execute(self, what: str) -> None:
        self._events.publish(SomethingFollowedUp(what))


@application_event_listener
class FollowingUpListener:
    """Depends on a use case that depends on the publisher: a cycle while the publisher took every listener."""

    def __init__(self, follow_up: FollowUpUseCase) -> None:
        self._follow_up = follow_up

    @event_listener(SomethingHappened)
    def follow_up(self, event: SomethingHappened) -> None:
        self._follow_up.execute(event.what)


@application_event_listener
class FollowUpListener:
    def __init__(self, diary: Diary) -> None:
        self._diary = diary

    @event_listener(SomethingFollowedUp)
    def write_down(self, event: SomethingFollowedUp) -> None:
        self._diary.entries.append(f"followed up: {event.what}")


def test_a_listener_may_depend_on_a_use_case_that_publishes_events() -> None:
    """Regression (#13): wireup refused to build listener -> use case -> publisher -> every listener."""
    diary = Diary()

    @bean
    def shared_diary() -> Diary:
        return diary

    container = wireup.create_sync_container(
        injectables=[
            shared_diary,
            application_event_publisher_injectable,
            FollowUpUseCase,
            FollowingUpListener,
            FollowUpListener,
        ]
    )
    container.get(EventListenerMethodProcessor).register_listeners()
    container.get(ApplicationEventPublisher).publish(SomethingHappened("deadline confirmed"))

    assert diary.entries == ["followed up: deadline confirmed"]
    container.close()


def test_the_publisher_knows_no_listener_until_the_start_up_registers_them_and_registers_them_once() -> None:
    diary = Diary()
    publisher = ApplicationEventPublisher()
    processor = EventListenerMethodProcessor(publisher, [ImmediateListener(diary)])

    publisher.publish(SomethingHappened("before the start-up"))
    processor.register_listeners()
    processor.register_listeners()
    publisher.publish(SomethingHappened("after it"))

    assert diary.entries == ["at once: after it"]


def test_an_application_without_listeners_starts_and_publishing_tells_nobody() -> None:
    """Regression: wireup creates `Sequence[ApplicationEventListener]` only when a listener exists.

    An application with at least one listener never shows it; one without listeners could not
    start. Like Spring, a publisher without listeners is valid.
    """
    container = wireup.create_sync_container(injectables=[application_event_publisher, event_listener_method_processor])

    container.get(EventListenerMethodProcessor).register_listeners()
    container.get(ApplicationEventPublisher).publish(SomethingHappened("nobody listens"))

    assert not container.get(ApplicationEventPublisher).has_application_module_listeners


def test_the_library_ships_the_publisher_so_applications_register_nothing() -> None:
    container = wireup.create_sync_container(injectables=[application_event_publisher_injectable])

    assert isinstance(container.get(ApplicationEventPublisher), ApplicationEventPublisher)
    assert isinstance(container.get(EventListenerMethodProcessor), EventListenerMethodProcessor)


def test_outside_a_transaction_a_transactional_listener_is_skipped_and_the_others_still_hear(
    transaction_manager: RecordingTransactionManager,
) -> None:
    diary = Diary()
    publisher = ApplicationEventPublisher([AfterCommitListener(diary), ImmediateListener(diary)])

    publisher.publish(SomethingHappened("no transaction"))

    assert diary.entries == ["at once: no transaction"]


def test_without_a_transaction_manager_a_transactional_listener_is_skipped_and_a_fallback_one_hears() -> None:
    TransactionManagerRegistry.uninstall()
    diary = Diary()
    publisher = ApplicationEventPublisher([AfterCommitListener(diary), FallbackListener(diary)])

    publisher.publish(SomethingHappened("no database"))

    assert diary.entries == ["fallback: no database"]


def test_a_fallback_listener_still_waits_for_a_running_transaction_and_never_hears_a_rollback(
    transaction_manager: RecordingTransactionManager,
) -> None:
    diary = Diary()
    publisher = ApplicationEventPublisher([FallbackListener(diary)])
    seen_inside: list[list[str]] = []

    @transactional
    def change(fail: bool) -> None:
        publisher.publish(SomethingHappened("fail" if fail else "commit"))
        seen_inside.append(list(diary.entries))
        if fail:
            raise ConnectionError("database gone")

    change(False)
    with pytest.raises(ConnectionError):
        change(True)

    assert seen_inside == [[], ["fallback: commit"]]
    assert diary.entries == ["fallback: commit"]


def test_an_event_published_after_its_transaction_ended_is_published_outside_one(
    transaction_manager: RecordingTransactionManager,
) -> None:
    diary = Diary()
    publisher = ApplicationEventPublisher([AfterCommitListener(diary)])

    @transactional
    def save() -> None:
        pass

    save()
    publisher.publish(SomethingHappened("too late"))

    assert diary.entries == []


def test_listeners_hear_the_phases_of_a_committed_transaction(
    transaction_manager: RecordingTransactionManager,
) -> None:
    diary = Diary()
    publisher = ApplicationEventPublisher([PhasesListener(diary), AfterCommitListener(diary)])
    seen_inside: list[list[str]] = []

    @transactional
    def change() -> None:
        publisher.publish(SomethingHappened("x"))
        seen_inside.append(list(diary.entries))

    change()

    assert seen_inside == [[]]
    assert diary.entries == ["before commit: x", "after commit: x", "after completion: x"]


def test_listeners_hear_the_phases_of_a_rolled_back_transaction(
    transaction_manager: RecordingTransactionManager,
) -> None:
    diary = Diary()
    publisher = ApplicationEventPublisher([PhasesListener(diary), AfterCommitListener(diary)])

    @transactional
    def change() -> None:
        publisher.publish(SomethingHappened("x"))
        raise ConnectionError("database gone")

    with pytest.raises(ConnectionError):
        change()

    assert diary.entries == ["after rollback: x", "after completion: x"]


def test_a_failing_before_commit_listener_rolls_the_transaction_back(
    transaction_manager: RecordingTransactionManager,
) -> None:
    @application_event_listener
    class Refusing:
        @transactional_event_listener(SomethingHappened, phase=TransactionPhase.BEFORE_COMMIT)
        def refuse(self, event: SomethingHappened) -> None:
            raise PermissionError(event.what)

    publisher = ApplicationEventPublisher([Refusing()])

    @transactional
    def change() -> None:
        publisher.publish(SomethingHappened("refused"))

    with pytest.raises(PermissionError, match="refused"):
        change()

    assert (transaction_manager.committed, transaction_manager.rolled_back) == (0, 1)


@application_event_listener
class ReturningListener:
    @event_listener(SomethingHappened)
    def follow_up(self, event: SomethingHappened) -> SomethingElseHappened:
        return SomethingElseHappened(event.what)


def test_a_listener_that_returns_a_follow_up_event_is_refused_since_nobody_publishes_it() -> None:
    with pytest.raises(InvalidApplicationEventListenerError, match=r"ReturningListener\.follow_up returns"):
        ApplicationEventPublisher([ReturningListener()])


@application_event_listener
class PublishingFollowUpListener:
    def __init__(self, diary: Diary, events: ApplicationEventPublisher) -> None:
        self._diary = diary
        self._events = events

    @event_listener(SomethingHappened)
    def follow_up(self, event: SomethingHappened) -> None:
        self._events.publish(SomethingElseHappened(event.what))

    @event_listener(SomethingElseHappened)
    def write_down(self, event: SomethingElseHappened) -> None:
        self._diary.entries.append(f"followed up: {event.what}")


def test_a_listener_publishes_a_follow_up_event_through_the_publisher(
    transaction_manager: RecordingTransactionManager,
) -> None:
    diary = Diary()
    publisher = ApplicationEventPublisher()
    publisher.register([PublishingFollowUpListener(diary, publisher)])

    publisher.publish(SomethingHappened("signed up"))

    assert diary.entries == ["followed up: signed up"]
