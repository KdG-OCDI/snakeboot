"""The application context reads the configuration, builds the container and installs the transactions."""

from collections.abc import Iterator

import pytest

from snakeboot.application import ApplicationContext
from snakeboot.boot import CONDITIONAL_MODULES
from snakeboot.configuration import DatabaseProperties, ServerProperties
from snakeboot.lifecycle import ApplicationComponents
from snakeboot.rest.rest_controller_mappings import CONTROLLER_MAPPING_ATTRIBUTE
from snakeboot.sqlalchemy_data import Database, SqlAlchemyTransactionManager
from snakeboot.sqlalchemy_data.testing import in_memory_database
from snakeboot.transaction import TransactionManagerNotInstalledError, TransactionManagerRegistry, transactional
from tests.application.sample_service.games.game_record import GameRecords
from tests.application.sample_service.games.game_rest_controller import GameRestController
from tests.application.sample_service.sample_service_application import SampleServiceApplication
from tests.command_line.sample_commands.applications import ApplicationWithoutCommands


@pytest.fixture
def started() -> Iterator[ApplicationContext]:
    context = ApplicationContext.of(SampleServiceApplication, CONDITIONAL_MODULES)
    context.refresh({Database: in_memory_database()})
    yield context
    context.close()


def test_of_reads_the_configuration_and_builds_nothing() -> None:
    context = ApplicationContext.of(SampleServiceApplication, CONDITIONAL_MODULES)

    assert context.configuration.get(ServerProperties).log_level == "WARNING"
    assert not context.started


def test_a_table_brings_its_binding_into_the_container() -> None:
    with_database = ApplicationContext.of(SampleServiceApplication, CONDITIONAL_MODULES).scan.module_names()
    without = ApplicationContext.of(ApplicationWithoutCommands, CONDITIONAL_MODULES).scan.module_names()

    assert "snakeboot.sqlalchemy_data.sqlalchemy_data_injectable" in with_database
    assert "snakeboot.sqlalchemy_data.sqlalchemy_data_injectable" not in without


def test_refresh_builds_the_container_of_the_component_scan(started: ApplicationContext) -> None:
    assert isinstance(started.get(GameRestController), GameRestController)
    assert started.get(GameRestController) is started.get(GameRestController)


def test_a_repository_interface_is_a_component(started: ApplicationContext) -> None:
    assert GameRecords in type(started.get(GameRecords)).__mro__


def test_the_context_is_the_application_s_components(started: ApplicationContext) -> None:
    assert started.get(ApplicationComponents) is started
    assert started.classes_marked(CONTROLLER_MAPPING_ATTRIBUTE) == [GameRestController]


def test_with_a_database_transactional_runs_on_it(started: ApplicationContext) -> None:
    assert isinstance(TransactionManagerRegistry.current(), SqlAlchemyTransactionManager)
    assert DatabaseProperties in started.configuration.sections


def test_without_a_database_transactional_has_nothing_to_run_on() -> None:
    context = ApplicationContext.start(ApplicationWithoutCommands, CONDITIONAL_MODULES)

    with pytest.raises(TransactionManagerNotInstalledError):
        transactional(lambda: None)()
    context.close()


def test_close_uninstalls_the_transactions(started: ApplicationContext) -> None:
    started.close()

    with pytest.raises(TransactionManagerNotInstalledError):
        TransactionManagerRegistry.current()


def test_a_component_the_container_lacks_is_a_lookup_error(started: ApplicationContext) -> None:
    with pytest.raises(LookupError, match="The container has no ApplicationWithoutCommands"):
        started.get(ApplicationWithoutCommands)


def test_nothing_is_handed_out_before_the_container_is_built() -> None:
    with pytest.raises(LookupError, match="not started yet"):
        ApplicationContext.of(SampleServiceApplication, CONDITIONAL_MODULES).get(GameRecords)
