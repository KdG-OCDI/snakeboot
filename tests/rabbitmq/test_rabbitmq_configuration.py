"""`[rabbitmq]` names the broker, and only an application with that section gets listeners and a template."""

import pytest
import wireup
from pydantic import ValidationError

from snakeboot.application import ApplicationContext
from snakeboot.boot import CONDITIONAL_MODULES
from snakeboot.configuration import RabbitListenerRetryProperties, RabbitProperties
from snakeboot.lifecycle import ApplicationComponents, Lifecycle, TaskDecorator
from snakeboot.rabbitmq import ListenerTiming, RabbitConnectionFactory, RabbitListenerContainers, RabbitTemplate
from snakeboot.rabbitmq.rabbitmq_injectable import (
    listener_timing,
    rabbit_connection_factory,
    rabbit_listener_containers,
    rabbit_template,
)
from snakeboot.stereotype import bean
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


def rabbit_properties_of(monkeypatch: pytest.MonkeyPatch, properties: dict[str, object]) -> RabbitProperties:
    for name, value in BROKER.items():
        monkeypatch.setenv(name, value)
    context = ApplicationContext.of(ApplicationWithoutCommands, CONDITIONAL_MODULES, properties=properties)
    return context.configuration.get(RabbitProperties)


def test_without_the_retry_table_a_failing_message_is_tried_three_times_a_second_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    properties = rabbit_properties_of(monkeypatch, {})

    assert properties.listener.retry is None
    assert listener_timing(properties.listener.retry) == ListenerTiming()  # three attempts, a second apart


def test_the_retry_table_sets_the_attempts_and_the_exponential_back_off(monkeypatch: pytest.MonkeyPatch) -> None:
    retry = {"max_attempts": 6, "initial_interval": 2, "multiplier": 2, "max_interval": "PT30S"}

    properties = rabbit_properties_of(
        monkeypatch, {f"rabbitmq.listener.retry.{key}": value for key, value in retry.items()}
    )

    assert listener_timing(properties.listener.retry) == ListenerTiming(
        attempts=6, retry_pause_seconds=2, retry_multiplier=2, max_retry_pause_seconds=30
    )


@pytest.mark.parametrize(
    "retry",
    [
        {"max_attempts": 0, "initial_interval": 1, "multiplier": 1, "max_interval": 10},
        {"max_attempts": 3, "initial_interval": -1, "multiplier": 1, "max_interval": 10},
        {"max_attempts": 3, "initial_interval": 1, "multiplier": 0.5, "max_interval": 10},
        {"max_attempts": 3, "initial_interval": 20, "multiplier": 2, "max_interval": 10},
    ],
    ids=["no attempt", "a negative interval", "a shrinking pause", "a longest pause shorter than the first"],
)
def test_a_retry_table_that_cannot_work_stops_the_start(retry: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match=r"\[rabbitmq\.listener\.retry\] needs"):
        RabbitListenerRetryProperties.model_validate(retry)


def test_wireup_provides_the_template_and_the_listener_containers() -> None:
    @bean
    def properties() -> RabbitProperties:
        return rabbit_properties(auto_startup=False)

    @bean(as_type=ApplicationComponents)
    def components() -> ApplicationComponents:
        return ScannedComponents("tests.component_scan.sample_project")

    @bean(as_type=TaskDecorator)
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
