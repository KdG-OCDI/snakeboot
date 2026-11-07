"""The scheduler runs every `@scheduled` method of the application on one thread, and refuses broken ones at start."""

import logging
from collections.abc import Iterator

import pytest
import wireup
from wireup import injectable

from snakeboot.configuration import CONFIGURATION_KEY, SchedulingProperties, begin_configuration
from snakeboot.lifecycle import ApplicationComponents, Lifecycle, TaskDecorator
from snakeboot.scheduling import InvalidScheduledTaskError, TaskScheduler
from snakeboot.scheduling.task_scheduler_injectable import auto_startup_of, task_scheduler
from tests.scheduling.sample_jobs.working.jobs import Failing, Ticker
from tests.scheduling.stand_ins import CountingTaskDecorator, ScannedComponents

WORKING = "tests.scheduling.sample_jobs.working"
WAIT_SECONDS = 5


@pytest.fixture
def ticker() -> Ticker:
    return Ticker()


@pytest.fixture
def failing() -> Failing:
    return Failing()


@pytest.fixture
def scheduler(ticker: Ticker, failing: Failing) -> Iterator[TaskScheduler]:
    scheduler = TaskScheduler(ScannedComponents(WORKING, ticker, failing), CountingTaskDecorator(), auto_startup=True)
    yield scheduler
    scheduler.stop()


def test_runs_every_scheduled_method_again_and_again(scheduler: TaskScheduler, ticker: Ticker) -> None:
    scheduler.start()

    assert ticker.ticked_three_times.wait(WAIT_SECONDS)


def test_a_method_that_raises_is_logged_and_runs_again(
    scheduler: TaskScheduler, failing: Failing, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        scheduler.start()
        assert failing.tried_twice.wait(WAIT_SECONDS)

    assert "Failing.fail failed; it runs again at its next turn" in caplog.text


def test_every_run_goes_through_the_task_decorator(ticker: Ticker, failing: Failing) -> None:
    decorator = CountingTaskDecorator()
    scheduler = TaskScheduler(ScannedComponents(WORKING, ticker, failing), decorator, auto_startup=True)

    scheduler.start()
    ticker.ticked_three_times.wait(WAIT_SECONDS)
    scheduler.stop()

    assert decorator.runs >= ticker.ticks


def test_after_stop_no_method_runs_anymore(scheduler: TaskScheduler, ticker: Ticker) -> None:
    scheduler.start()
    ticker.ticked_three_times.wait(WAIT_SECONDS)

    scheduler.stop()
    ticks = ticker.ticks

    assert not scheduler.running
    assert ticker.ticks == ticks


def test_with_auto_startup_off_no_thread_starts(ticker: Ticker, failing: Failing) -> None:
    scheduler = TaskScheduler(ScannedComponents(WORKING, ticker, failing), CountingTaskDecorator(), auto_startup=False)

    scheduler.start()

    assert not scheduler.running
    assert ticker.ticks == 0


def test_an_application_without_scheduled_methods_starts_no_thread() -> None:
    scheduler = TaskScheduler(
        ScannedComponents("tests.component_scan.sample_project"), CountingTaskDecorator(), auto_startup=True
    )

    scheduler.start()

    assert not scheduler.running


def test_a_scheduled_method_of_a_class_that_is_no_component_stops_the_start_up(ticker: Ticker) -> None:
    scheduler = TaskScheduler(ScannedComponents(WORKING, ticker), CountingTaskDecorator(), auto_startup=False)

    with pytest.raises(InvalidScheduledTaskError, match="Failing is no component: add @injectable"):
        scheduler.start()


@pytest.mark.parametrize(
    ("package", "message"),
    [
        ("tests.scheduling.sample_jobs.broken", "must take nothing but self"),
        ("tests.scheduling.sample_jobs.asynchronous", "is async"),
    ],
)
def test_a_scheduled_method_that_cannot_run_stops_the_start_up(package: str, message: str) -> None:
    scheduler = TaskScheduler(ScannedComponents(package), CountingTaskDecorator(), auto_startup=True)

    with pytest.raises(InvalidScheduledTaskError, match=message):
        scheduler.start()


def test_the_scheduled_methods_run_unless_the_section_turns_them_off(monkeypatch: pytest.MonkeyPatch) -> None:
    def configuration() -> object:
        return begin_configuration(optional=(SchedulingProperties,), package="tests.configuration.empty_service")

    monkeypatch.delenv("SCHEDULING__AUTO_STARTUP", raising=False)
    assert auto_startup_of(configuration()) is True  # type: ignore[arg-type]

    monkeypatch.setenv("SCHEDULING__AUTO_STARTUP", "false")
    assert auto_startup_of(configuration()) is False  # type: ignore[arg-type]


def test_wireup_provides_the_scheduler_as_a_lifecycle_component(ticker: Ticker, failing: Failing) -> None:
    @injectable(as_type=ApplicationComponents)
    def components() -> ApplicationComponents:
        return ScannedComponents(WORKING, ticker, failing)

    @injectable(as_type=TaskDecorator)
    def decorator() -> TaskDecorator:
        return CountingTaskDecorator()

    configuration = begin_configuration(optional=(SchedulingProperties,), package="tests.configuration.empty_service")
    container = wireup.create_sync_container(
        injectables=[components, decorator, task_scheduler], config={CONFIGURATION_KEY: configuration}
    )

    assert isinstance(container.get(Lifecycle, qualifier="snakeboot.scheduling.TaskScheduler"), TaskScheduler)
