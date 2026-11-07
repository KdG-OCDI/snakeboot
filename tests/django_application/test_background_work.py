"""Threads outside a request get the components of the container and fresh database connections from Django."""

import pytest
from django.test import override_settings
from wireup.errors import WireupError

from snakeboot.django_application import background_work
from snakeboot.django_application.background_work import DjangoApplicationComponents, DjangoConnectionsTaskDecorator
from snakeboot.scheduling.scheduled import SCHEDULED_MAPPING_ATTRIBUTE, ScheduledMapping
from tests.scheduling.sample_jobs.applications import WorkingJobsApplication
from tests.scheduling.sample_jobs.working.jobs import Ticker


def test_each_piece_of_work_runs_between_fresh_database_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    journal: list[str] = []
    monkeypatch.setattr(background_work, "close_old_connections", lambda: journal.append("close old connections"))

    DjangoConnectionsTaskDecorator().decorate(lambda: journal.append("work"))()

    assert journal == ["close old connections", "work", "close old connections"]


def test_connections_are_tidied_up_after_work_that_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    journal: list[str] = []
    monkeypatch.setattr(background_work, "close_old_connections", lambda: journal.append("close old connections"))

    def fail() -> None:
        raise RuntimeError("broken")

    with pytest.raises(RuntimeError):
        DjangoConnectionsTaskDecorator().decorate(fail)()

    assert journal == ["close old connections", "close old connections"]


def test_the_marked_methods_come_from_the_scan_of_the_application() -> None:
    with override_settings(APPLICATION=WorkingJobsApplication):
        found = DjangoApplicationComponents().methods_marked(SCHEDULED_MAPPING_ATTRIBUTE, ScheduledMapping)

    assert Ticker in {marked.owner for marked in found}


def test_a_type_the_container_does_not_know_is_a_lookup_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class EmptyContainer:
        def _synchronous_get(self, component_type: type) -> object:
            raise WireupError(f"unknown {component_type.__name__}")

    monkeypatch.setattr(background_work, "get_app_container", EmptyContainer)

    with pytest.raises(LookupError, match="The container has no Ticker"):
        DjangoApplicationComponents().get(Ticker)
