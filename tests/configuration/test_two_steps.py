"""The configuration is read in two steps: what is known before the container is built, then everything."""

import pytest
from pydantic import ValidationError

from snakeboot.configuration import (
    CacheProperties,
    DatabaseProperties,
    InvalidConfigurationPropertiesError,
    ServerProperties,
    begin_configuration,
    sections_with_a_table,
)
from tests.configuration.sample_service.greeting_properties import GreetingProperties

SAMPLE = "tests.configuration.sample_service"
INFRASTRUCTURE_SERVICE = "tests.configuration.infrastructure_service"
INFRASTRUCTURE_SECTIONS = (DatabaseProperties, CacheProperties)


def test_the_first_step_leaves_the_tables_of_the_container_for_later() -> None:
    configuration = begin_configuration(ServerProperties, package=SAMPLE)  # application.toml also has [greeting]

    assert set(configuration.sections) == {ServerProperties}


def test_the_second_step_reads_the_sections_of_the_container() -> None:
    configuration = begin_configuration(ServerProperties, package=SAMPLE)

    configuration.complete(GreetingProperties)

    assert configuration.get(GreetingProperties).text == "Hello"
    assert configuration.get(ServerProperties).debug is False


def test_the_second_step_refuses_a_table_no_section_claims() -> None:
    configuration = begin_configuration(ServerProperties, package=SAMPLE)

    with pytest.raises(ValidationError, match="greeting"):
        configuration.complete()


def test_the_second_step_is_taken_once() -> None:
    configuration = begin_configuration(ServerProperties, package=SAMPLE)
    configuration.complete(GreetingProperties)

    with pytest.raises(InvalidConfigurationPropertiesError, match="complete already"):
        configuration.complete(GreetingProperties)


def test_a_section_known_from_the_first_step_may_be_named_again() -> None:
    configuration = begin_configuration(ServerProperties, package=SAMPLE)

    configuration.complete(ServerProperties, GreetingProperties)

    assert set(configuration.sections) == {ServerProperties, GreetingProperties}


def test_an_optional_section_is_read_when_its_table_is_there() -> None:
    configuration = begin_configuration(
        ServerProperties, optional=INFRASTRUCTURE_SECTIONS, package=INFRASTRUCTURE_SERVICE
    )
    configuration.complete()

    assert configuration.get(DatabaseProperties).host == "db"
    assert configuration.get(CacheProperties).redis_url == "redis://redis:6379/1"


def test_an_optional_section_without_a_table_is_absent() -> None:
    configuration = begin_configuration(ServerProperties, optional=INFRASTRUCTURE_SECTIONS, package=SAMPLE)
    configuration.complete(GreetingProperties)

    assert DatabaseProperties not in configuration.sections
    with pytest.raises(LookupError, match="DatabaseProperties has no table"):
        configuration.get(DatabaseProperties)


def test_an_optional_table_that_is_only_partly_there_stops_the_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE__PASSWORD", "set-by-compose")  # the other keys of [database] are missing

    with pytest.raises(ValidationError, match=r"database\.host"):
        begin_configuration(ServerProperties, optional=INFRASTRUCTURE_SECTIONS, package=SAMPLE)


def test_which_tables_there_are_is_known_without_reading_a_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVER__PORT", "eighty")  # invalid, but [server] is in application.toml
    monkeypatch.setenv("CACHE__REDIS_URL", "redis://cache:6379/0")  # a table of the environment alone
    monkeypatch.setenv("DATABASE", "postgres")  # no key of a table: names no table

    present = sections_with_a_table(
        ServerProperties, GreetingProperties, DatabaseProperties, CacheProperties, package=SAMPLE
    )

    assert present == {ServerProperties, GreetingProperties, CacheProperties}


def test_without_a_table_no_section_is_there() -> None:
    present = sections_with_a_table(ServerProperties, DatabaseProperties, package="tests.configuration.empty_service")

    assert present == frozenset()
