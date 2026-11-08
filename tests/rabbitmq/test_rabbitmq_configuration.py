"""`[rabbitmq]` names the broker, and only an application with that section gets listeners and a template."""

import pytest
import wireup
from wireup import injectable

from snakeboot.application import ApplicationContext
from snakeboot.boot import CONDITIONAL_MODULES
from snakeboot.configuration import RabbitProperties
from snakeboot.lifecycle import ApplicationComponents, Lifecycle, TaskDecorator
from snakeboot.rabbitmq import RabbitConnectionFactory, RabbitListenerContainers, RabbitTemplate
from snakeboot.rabbitmq.rabbitmq_injectable import (
    rabbit_connection_factory,
    rabbit_listener_containers,
    rabbit_template,
)
from tests.command_line.sample_commands.applications import ApplicationWithoutCommands
from tests.rabbitmq.stand_ins import rabbit_properties
from tests.scheduling.stand_ins import CountingTaskDecorator, ScannedComponents

BROKER = {
    "RABBITMQ__HOST": "rabbitmq",
    "RABBITMQ__PORT": "5672",
    "RABBITMQ__USERNAME": "guest",
    "RABBITMQ__PASSWORD": "guest",
    "RABBITMQ__VIRTUAL_HOST": "/",
    "RABBITMQ__LISTENER__AUTO_STARTUP": "true",
}


@pytest.fixture(autouse=True)
def no_broker_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in BROKER:
        monkeypatch.delenv(name, raising=False)


def test_the_connections_log_in_where_and_as_whom_the_section_says() -> None:
    parameters = RabbitConnectionFactory(rabbit_properties()).parameters

    assert (parameters.host, parameters.port, parameters.virtual_host) == ("rabbitmq", 5672, "/")
    assert (parameters.credentials.username, parameters.credentials.password) == ("guest", "guest")


def test_an_application_with_the_section_has_rabbitmq_in_its_container(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in BROKER.items():
        monkeypatch.setenv(name, value)

    assert RABBITMQ_AUTO_CONFIGURATION in modules_of(ApplicationWithoutCommands)


def test_an_application_without_the_section_has_no_rabbitmq_in_its_container() -> None:
    assert RABBITMQ_AUTO_CONFIGURATION not in modules_of(ApplicationWithoutCommands)


RABBITMQ_AUTO_CONFIGURATION = "snakeboot.rabbitmq.rabbitmq_injectable"


def modules_of(application: type) -> list[str]:
    return ApplicationContext.of(application, CONDITIONAL_MODULES).scan.module_names()


def test_wireup_provides_the_template_and_the_listener_containers() -> None:
    @injectable
    def properties() -> RabbitProperties:
        return rabbit_properties(auto_startup=False)

    @injectable(as_type=ApplicationComponents)
    def components() -> ApplicationComponents:
        return ScannedComponents("tests.component_scan.sample_project")

    @injectable(as_type=TaskDecorator)
    def decorator() -> TaskDecorator:
        return CountingTaskDecorator()

    container = wireup.create_sync_container(
        injectables=[
            properties,
            components,
            decorator,
            rabbit_connection_factory,
            rabbit_template,
            rabbit_listener_containers,
        ]
    )

    assert isinstance(container.get(RabbitTemplate), RabbitTemplate)
    listeners = container.get(Lifecycle, qualifier="snakeboot.rabbitmq.RabbitListenerContainers")
    assert isinstance(listeners, RabbitListenerContainers)
