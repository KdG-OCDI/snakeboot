"""What is wrong with the configuration, one sentence per problem, naming the key and the variable that sets it."""

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from snakeboot.configuration import (
    PROFILE_VARIABLE,
    Configuration,
    ConfigurationFileNotFoundError,
    DatabaseProperties,
    ServerProperties,
    begin_configuration,
    configuration_problems,
    load_configuration,
)
from tests.configuration.sample_service.greeting_properties import FarewellProperties, GreetingProperties

SAMPLE = "tests.configuration.sample_service"


def problems_of(read: Callable[[], Configuration]) -> tuple[str, ...]:
    with pytest.raises(ValidationError) as stopped:
        read()
    return configuration_problems(stopped.value)


def test_a_missing_value_names_its_key_and_its_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE__PASSWORD", "set-by-the-deployment")  # the other keys of [database] are missing

    problems = problems_of(
        lambda: begin_configuration(ServerProperties, optional=(DatabaseProperties,), package=SAMPLE)
    )

    assert problems == (
        "database.host is missing: set it in application.toml or DATABASE__HOST",
        "database.port is missing: set it in application.toml or DATABASE__PORT",
        "database.name is missing: set it in application.toml or DATABASE__NAME",
        "database.user is missing: set it in application.toml or DATABASE__USER",
    )


def test_a_missing_table_names_the_variables_of_its_keys() -> None:
    problems = problems_of(
        lambda: load_configuration(ServerProperties, GreetingProperties, FarewellProperties, package=SAMPLE)
    )

    assert problems == ("[farewell] is missing: add the table to application.toml, or set its keys as FAREWELL__<KEY>",)


def test_an_invalid_value_says_why_and_never_shows_the_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GREETING__REPEAT", "often")

    problems = problems_of(lambda: load_configuration(ServerProperties, GreetingProperties, package=SAMPLE))

    assert problems == (
        "greeting.repeat is invalid (Input should be a valid integer, unable to parse string as an integer): "
        "correct it in application.toml or GREETING__REPEAT",
    )


def test_an_unknown_key_names_the_variable_that_may_have_set_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GREETING__SENDER__NAEM", "a typo of name")

    problems = problems_of(lambda: load_configuration(ServerProperties, GreetingProperties, package=SAMPLE))

    assert problems == ("greeting.sender.naem is unknown: remove it from application.toml or GREETING__SENDER__NAEM",)


def test_a_table_no_section_claims_says_how_to_claim_it() -> None:
    problems = problems_of(lambda: load_configuration(GreetingProperties, package=SAMPLE))

    assert problems == (
        "[server] is a table that no section claims: remove it from application.toml, or declare its section with "
        '@configuration_properties("server")',
    )


def test_a_key_inside_a_variant_leaves_out_the_name_pydantic_gives_the_variant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PROFILE_VARIABLE, "email")
    monkeypatch.setenv("GREETING__CHANNEL__KIND", "log")  # `server` of the email channel stays, and is refused

    problems = problems_of(lambda: load_configuration(ServerProperties, GreetingProperties, package=SAMPLE))

    assert problems == (
        "greeting.channel.server is unknown: remove it from application.toml, application-email.toml or "
        "GREETING__CHANNEL__SERVER",
    )


def test_a_table_that_is_invalid_as_a_whole_names_the_variables_of_its_keys() -> None:
    problems = problems_of(
        lambda: begin_configuration(
            ServerProperties,
            optional=(DatabaseProperties,),
            package=SAMPLE,
            properties={"database.file": "x.sqlite3", "database.host": "db"},
        )
    )

    assert problems == (
        "[database] is invalid ([database] is a server or a file, not both: leave out host): correct it in "
        "application.toml or DATABASE__<KEY>",
    )


def test_pydantic_s_error_stays_and_shows_the_problems_as_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVER__PORT", "eighty")

    with pytest.raises(ValidationError, match=r"server\.port") as stopped:
        load_configuration(ServerProperties, GreetingProperties, package=SAMPLE)

    assert stopped.value.__notes__ == list(configuration_problems(stopped.value))
    assert stopped.value.__notes__[0].startswith("server.port is invalid (")
    assert "eighty" not in "\n".join(stopped.value.__notes__)


def test_a_missing_file_is_one_problem() -> None:
    with pytest.raises(ConfigurationFileNotFoundError) as stopped:
        load_configuration(package="tests.configuration.without_files")

    assert configuration_problems(stopped.value) == (
        "tests.configuration.without_files has no application.toml: it holds every value of the application.",
    )


def test_another_error_is_no_problem_of_the_configuration() -> None:
    assert configuration_problems(ValueError("a bug in a component")) == ()
