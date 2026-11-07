"""What threads outside a request need from Django: the components of the container and usable database connections.

Part of snakeboot's auto-configuration (`SNAKEBOOT_AUTO_CONFIGURATION`), for the scheduler and the message listeners.
"""

from collections.abc import Callable
from typing import override

from django.conf import settings
from django.db import close_old_connections
from wireup import injectable
from wireup.errors import WireupError
from wireup.integration.django import get_app_container

from snakeboot.component_scan import ComponentScan, MarkedMethod
from snakeboot.django_application.django_settings import APPLICATION_SETTING
from snakeboot.lifecycle.application_components import ApplicationComponents
from snakeboot.lifecycle.task_decorator import TaskDecorator


@injectable(as_type=ApplicationComponents)
class DjangoApplicationComponents(ApplicationComponents):
    """The component scan of the application class and wireup's container of the running Django application."""

    @override
    def methods_marked[M](self, marker: str, mapping_type: type[M]) -> list[MarkedMethod[M]]:
        return ComponentScan.of(getattr(settings, APPLICATION_SETTING)).methods_marked(marker, mapping_type)

    @override
    def get[T](self, component_type: type[T]) -> T:
        try:
            # reason: a thread outside a request needs a synchronous singleton; wireup's container is async.
            component: T = get_app_container()._synchronous_get(component_type)
        except WireupError as error:
            raise LookupError(f"The container has no {component_type.__qualname__}: {error}") from error
        return component


@injectable(as_type=TaskDecorator)
class DjangoConnectionsTaskDecorator(TaskDecorator):
    """Closes database connections that broke or outlived `CONN_MAX_AGE` before and after each piece of work.

    Django does so around every request; a thread that runs for days needs it around every task and message,
    or one dropped connection to PostgreSQL would fail every task after it.
    """

    @override
    def decorate(self, task: Callable[[], None]) -> Callable[[], None]:
        def with_fresh_connections() -> None:
            close_old_connections()
            try:
                task()
            finally:
                close_old_connections()

        return with_fresh_connections
