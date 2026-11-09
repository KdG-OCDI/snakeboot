"""The optional table `[events]` sets when the event publication registry delivers again."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from snakeboot.boot.testing import TestApplication
from snakeboot.configuration import PROFILE_VARIABLE, EventsProperties
from snakeboot.event_publication import (
    IN_FLIGHT,
    MAX_ATTEMPTS,
    RESUBMIT_EVERY,
    RETRY_AFTER,
    EventPublicationRecords,
    PublicationTiming,
)
from snakeboot.events import ApplicationEventPublisher
from tests.event_publication.sample_outbox.orders import InvoicingService, PlaceOrderUseCase
from tests.event_publication.sample_outbox.outbox_application import OutboxApplication


@pytest.fixture
def timed(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestApplication]:
    monkeypatch.setenv(PROFILE_VARIABLE, "timed")
    with TestApplication.start(OutboxApplication) as started:
        yield started


def test_without_the_table_snakeboot_s_own_timing_holds() -> None:
    assert PublicationTiming.of(None) == PublicationTiming(RESUBMIT_EVERY, IN_FLIGHT, RETRY_AFTER, MAX_ATTEMPTS)


def test_a_time_is_seconds_or_an_iso_duration() -> None:
    properties = EventsProperties.model_validate(
        {"resubmit_every": 5, "in_flight": "PT2M", "retry_after": 60, "max_attempts": 2}
    )

    assert PublicationTiming.of(properties) == PublicationTiming(
        timedelta(seconds=5), timedelta(minutes=2), timedelta(minutes=1), 2
    )


@pytest.mark.parametrize(
    "wrong",
    [
        pytest.param({"resubmit_every": 0}, id="no time between looks"),
        pytest.param({"retry_after": -1}, id="a negative wait"),
        pytest.param({"max_attempts": 0}, id="no attempt"),
    ],
)
def test_times_that_are_not_positive_stop_the_start(wrong: dict[str, int]) -> None:
    values = {"resubmit_every": 5, "in_flight": 120, "retry_after": 60, "max_attempts": 2, **wrong}

    with pytest.raises(ValidationError, match="positive times and one attempt at least"):
        EventsProperties.model_validate(values)


def test_the_registry_of_an_application_waits_and_tries_as_its_table_says(timed: TestApplication) -> None:
    timed.get(InvoicingService).down = True
    before = datetime.now(UTC)

    timed.get(PlaceOrderUseCase).execute("o1", 42, before)

    records = timed.get(EventPublicationRecords)
    [record] = records.find_all()
    assert before + timedelta(seconds=55) < record.due_at < before + timedelta(seconds=65)
    for _ in range(3):
        record.due_at = datetime.now(UTC) - timedelta(seconds=1)
        records.save(record)
        timed.get(ApplicationEventPublisher).resubmit_incomplete()
        [record] = records.find_all()
    assert record.attempts == 2
