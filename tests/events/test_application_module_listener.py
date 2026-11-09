"""An `@application_module_listener` receives its event after the commit, on the executor, in a transaction of its own,
and with a registry its publication is kept until it was delivered."""

import uuid
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import override

import pytest

from snakeboot.events import (
    ApplicationEventPublisher,
    EventPublication,
    EventPublicationRegistry,
    TaskExecutor,
    application_module_listener,
)
from snakeboot.testing import RecordingTransactionManager
from snakeboot.tracing import TraceContext
from snakeboot.transaction import TransactionManagerRegistry, transactional


@dataclass(frozen=True)
class OrderPlaced:
    order_id: str


class LaterExecutor(TaskExecutor):
    """Keeps the work until the test runs it, as a pool of threads would run it later."""

    def __init__(self) -> None:
        self.waiting: list[Callable[[], None]] = []

    @override
    def execute(self, task: Callable[[], None]) -> None:
        self.waiting.append(task)

    def run_all(self) -> None:
        waiting, self.waiting = self.waiting, []
        for task in waiting:
            task()


@dataclass
class InMemoryRegistry(EventPublicationRegistry):
    """Keeps the publications in a dictionary, and says what happened to them."""

    owed: dict[uuid.UUID, EventPublication] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    due: list[EventPublication] = field(default_factory=list)
    stored_in_transaction: list[bool] = field(default_factory=list)

    @override
    def verify(self, event_types: Iterable[type]) -> None:
        pass

    @override
    def store(self, event: object, listener_ids: Sequence[str]) -> list[EventPublication]:
        self.stored_in_transaction.append(TransactionManagerRegistry.current().in_transaction)  # type: ignore[attr-defined]
        publications = [EventPublication(uuid.uuid4(), listener_id, event) for listener_id in listener_ids]
        self.owed.update({publication.identifier: publication for publication in publications})
        return publications

    @override
    def complete(self, publication: EventPublication) -> None:
        del self.owed[publication.identifier]

    @override
    def fail(self, publication: EventPublication, error: Exception) -> None:
        self.failures.append(str(error))

    @override
    def claim_due(self) -> list[EventPublication]:
        due, self.due = self.due, []
        return due

    @override
    def count_incomplete(self) -> int:
        return len(self.owed)


class Invoicing:
    """Invoices every order placed, and fails while told to."""

    def __init__(self) -> None:
        self.invoiced: list[str] = []
        self.in_transaction: list[bool] = []
        self.traces: list[str | None] = []
        self.failing = False

    @application_module_listener(OrderPlaced)
    def invoice(self, event: OrderPlaced) -> None:
        installed = TransactionManagerRegistry.is_installed()
        self.in_transaction.append(installed and TransactionManagerRegistry.current().in_transaction)  # type: ignore[attr-defined]
        span = TraceContext.current()
        self.traces.append(span.trace_id if span is not None else None)
        if self.failing:
            raise RuntimeError("the invoicing service is down")
        self.invoiced.append(event.order_id)


@pytest.fixture
def transactions() -> Iterator[RecordingTransactionManager]:
    manager = RecordingTransactionManager()
    TransactionManagerRegistry.install(manager)
    yield manager
    TransactionManagerRegistry.uninstall()


@pytest.fixture
def executor() -> LaterExecutor:
    return LaterExecutor()


@pytest.fixture
def registry() -> InMemoryRegistry:
    return InMemoryRegistry()


@pytest.fixture
def invoicing() -> Invoicing:
    return Invoicing()


@pytest.fixture
def publisher(executor: LaterExecutor, registry: InMemoryRegistry, invoicing: Invoicing) -> ApplicationEventPublisher:
    return ApplicationEventPublisher([invoicing], executor=executor, registry=registry)


def placed_in_a_transaction(publisher: ApplicationEventPublisher, order_id: str) -> None:
    transactional(lambda: publisher.publish(OrderPlaced(order_id)))()


def test_the_listener_receives_the_event_on_the_executor_after_the_commit(
    transactions: RecordingTransactionManager,
    publisher: ApplicationEventPublisher,
    executor: LaterExecutor,
    invoicing: Invoicing,
) -> None:
    placed_in_a_transaction(publisher, "o1")
    assert invoicing.invoiced == []

    executor.run_all()

    assert invoicing.invoiced == ["o1"]


def test_the_listener_runs_in_a_transaction_of_its_own(
    transactions: RecordingTransactionManager,
    publisher: ApplicationEventPublisher,
    executor: LaterExecutor,
    invoicing: Invoicing,
) -> None:
    placed_in_a_transaction(publisher, "o1")
    executor.run_all()

    assert invoicing.in_transaction == [True]
    assert transactions.committed == 2


def test_a_rolled_back_change_hands_nothing_over(
    transactions: RecordingTransactionManager, publisher: ApplicationEventPublisher, executor: LaterExecutor
) -> None:
    @transactional
    def place_and_fail() -> None:
        publisher.publish(OrderPlaced("o1"))
        raise RuntimeError("no stock")

    with pytest.raises(RuntimeError):
        place_and_fail()

    assert executor.waiting == []


def test_the_publication_is_stored_in_the_publisher_s_transaction_and_completed_by_the_listener(
    transactions: RecordingTransactionManager,
    publisher: ApplicationEventPublisher,
    executor: LaterExecutor,
    registry: InMemoryRegistry,
) -> None:
    placed_in_a_transaction(publisher, "o1")
    assert registry.stored_in_transaction == [True]
    assert len(registry.owed) == 1

    executor.run_all()

    assert registry.owed == {}


def test_a_failing_listener_keeps_its_publication_and_records_why(
    transactions: RecordingTransactionManager,
    publisher: ApplicationEventPublisher,
    executor: LaterExecutor,
    registry: InMemoryRegistry,
    invoicing: Invoicing,
) -> None:
    invoicing.failing = True
    placed_in_a_transaction(publisher, "o1")

    executor.run_all()

    assert len(registry.owed) == 1
    assert registry.failures == ["the invoicing service is down"]
    assert transactions.rolled_back == 1


def test_resubmission_delivers_what_the_registry_says_is_due(
    transactions: RecordingTransactionManager,
    publisher: ApplicationEventPublisher,
    executor: LaterExecutor,
    registry: InMemoryRegistry,
    invoicing: Invoicing,
) -> None:
    invoicing.failing = True
    placed_in_a_transaction(publisher, "o1")
    executor.run_all()
    invoicing.failing = False
    registry.due = list(registry.owed.values())

    assert publisher.resubmit_incomplete() == 1
    executor.run_all()

    assert (invoicing.invoiced, registry.owed) == (["o1"], {})


def test_a_publication_for_a_listener_that_is_gone_fails(
    transactions: RecordingTransactionManager, publisher: ApplicationEventPublisher, registry: InMemoryRegistry
) -> None:
    registry.due = [EventPublication(uuid.uuid4(), "myapp.Gone.listen", OrderPlaced("o1"))]

    publisher.resubmit_incomplete()

    assert registry.failures == ["No listener method is named myapp.Gone.listen."]


def test_the_listener_continues_the_trace_of_the_publisher(
    transactions: RecordingTransactionManager,
    publisher: ApplicationEventPublisher,
    executor: LaterExecutor,
    invoicing: Invoicing,
) -> None:
    with TraceContext.started() as span:
        placed_in_a_transaction(publisher, "o1")

    executor.run_all()

    assert invoicing.traces == [span.trace_id]


def test_without_a_database_the_event_is_handed_over_at_once_and_kept_nowhere(executor: LaterExecutor) -> None:
    invoicing = Invoicing()
    publisher = ApplicationEventPublisher([invoicing], executor=executor)

    publisher.publish(OrderPlaced("o1"))
    executor.run_all()

    assert (invoicing.invoiced, invoicing.in_transaction) == (["o1"], [False])
    assert publisher.resubmit_incomplete() == 0


def test_without_an_executor_the_listener_runs_on_the_publisher_s_thread(
    transactions: RecordingTransactionManager,
) -> None:
    invoicing = Invoicing()

    placed_in_a_transaction(ApplicationEventPublisher([invoicing]), "o1")

    assert invoicing.invoiced == ["o1"]
