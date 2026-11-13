"""The lifecycle starts its components by phase, announces that the application is ready, and stops them in reverse."""

import logging
import threading

import pytest
import wireup
from wireup import injectable

from snakeboot.application.run_lifecycle_command import run_until
from snakeboot.events import ApplicationEventPublisher, application_event_listener, event_listener
from snakeboot.events.application_event_publisher_injectable import (
    application_event_publisher,
    event_listener_method_processor,
)
from snakeboot.events.event_listener_method_processor import EventListenerMethodProcessor
from snakeboot.lifecycle import ApplicationLifecycle, ApplicationReadyEvent
from snakeboot.lifecycle.application_lifecycle_injectable import application_lifecycle
from tests.lifecycle.sample_components import Early, Journal, Recording, StillAbstract, Wired


def lifecycle_of(journal: Journal, *components: Recording) -> ApplicationLifecycle:
    return ApplicationLifecycle(components, on_ready=lambda: journal.entries.append("ready"))


def test_starts_by_phase_then_announces_ready_and_stops_in_reverse() -> None:
    journal = Journal()
    lifecycle = lifecycle_of(journal, Recording(journal, "late"), Early(journal, "early"))

    lifecycle.start()
    lifecycle.stop()

    assert journal.entries == ["start early", "start late", "ready", "stop late", "stop early"]


def test_a_component_that_cannot_start_stops_the_ones_already_started_and_the_start_up() -> None:
    journal = Journal()
    lifecycle = lifecycle_of(journal, Early(journal, "early"), Recording(journal, "broken", failing="start"))

    with pytest.raises(RuntimeError, match="broken cannot start"):
        lifecycle.start()

    assert journal.entries == ["start early", "stop early"]


def test_a_failing_ready_listener_stops_the_start_up_too() -> None:
    journal = Journal()

    def refuse() -> None:
        raise RuntimeError("the platform is unreachable")

    lifecycle = ApplicationLifecycle([Recording(journal, "only")], on_ready=refuse)

    with pytest.raises(RuntimeError, match="unreachable"):
        lifecycle.start()

    assert journal.entries == ["start only", "stop only"]


def test_a_component_that_cannot_stop_is_logged_and_the_others_still_stop(caplog: pytest.LogCaptureFixture) -> None:
    journal = Journal()
    lifecycle = lifecycle_of(journal, Early(journal, "early"), Recording(journal, "stuck", failing="stop"))
    lifecycle.start()

    with caplog.at_level(logging.ERROR):
        lifecycle.stop()

    assert journal.entries[-1] == "stop early"
    assert "Recording did not stop cleanly" in caplog.text


def test_stopping_twice_stops_once() -> None:
    journal = Journal()
    lifecycle = lifecycle_of(journal, Recording(journal, "once"))
    lifecycle.start()

    lifecycle.stop()
    lifecycle.stop()

    assert journal.entries.count("stop once") == 1


def test_an_application_without_components_starts_and_is_ready() -> None:
    journal = Journal()

    lifecycle_of(journal).start()

    assert journal.entries == ["ready"]


def test_a_concrete_subclass_is_a_component_and_an_abstract_one_or_a_base_is_not() -> None:
    assert "__wireup_registration__" in vars(Wired)
    assert "__wireup_registration__" not in vars(StillAbstract)
    assert "__wireup_registration__" not in vars(Recording)


def test_wireup_hands_every_component_to_the_lifecycle_and_ready_goes_to_the_listeners() -> None:
    journal = Journal()

    @injectable
    def shared_journal() -> Journal:
        return journal

    @application_event_listener
    class ReadyListener:
        @event_listener(ApplicationReadyEvent)
        def on_ready(self, event: ApplicationReadyEvent) -> None:
            journal.entries.append("ready")

    container = wireup.create_sync_container(
        injectables=[
            shared_journal,
            application_event_publisher,
            event_listener_method_processor,
            application_lifecycle,
            Wired,
            ReadyListener,
        ]
    )
    container.get(EventListenerMethodProcessor).register_listeners()
    container.get(ApplicationLifecycle).start()

    assert journal.entries == ["start wired", "ready"]


def test_the_library_ships_the_lifecycle_so_an_application_without_components_registers_nothing() -> None:
    container = wireup.create_sync_container(injectables=[application_event_publisher, application_lifecycle])

    container.get(ApplicationLifecycle).start()

    assert isinstance(container.get(ApplicationEventPublisher), ApplicationEventPublisher)


def test_run_lifecycle_runs_until_it_is_told_to_stop() -> None:
    journal = Journal()
    stopping = threading.Event()
    lifecycle = ApplicationLifecycle([Recording(journal, "worker")], on_ready=stopping.set)

    run_until(stopping, lifecycle)

    assert journal.entries == ["start worker", "stop worker"]
