"""`load_configuration` reads application.toml, then the active profile, then the environment; nothing else."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from snakeboot.configuration import (
    PROFILE_VARIABLE,
    CacheProperties,
    Configuration,
    ConfigurationFileNotFoundError,
    DatabaseProperties,
    ServerProperties,
    load_configuration,
)
from tests.configuration.sample_service.greeting_properties import (
    EmailChannel,
    FarewellProperties,
    GreetingProperties,
)

SAMPLE = "tests.configuration.sample_service"


def load_sample() -> Configuration:
    return load_configuration(ServerProperties, GreetingProperties, package=SAMPLE)


def load_greeting() -> GreetingProperties:
    return load_sample().get(GreetingProperties)


def test_the_values_come_from_application_toml() -> None:
    greeting = load_greeting()

    assert greeting.text == "Hello"
    assert greeting.repeat == 1
    assert greeting.sender.name == "snakeboot"
    assert greeting.channel.kind == "log"


def test_without_a_profile_no_profile_is_active() -> None:
    assert load_sample().profile is None


def test_a_profile_overrides_only_the_keys_it_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PROFILE_VARIABLE, "local")

    configuration = load_sample()

    assert configuration.profile == "local"
    assert configuration.get(ServerProperties).debug is True
    assert configuration.get(GreetingProperties).sender.address == "dev@localhost"
    assert configuration.get(GreetingProperties).sender.name == "snakeboot"  # same table, kept from the base


def test_an_environment_variable_overrides_the_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PROFILE_VARIABLE, "local")
    monkeypatch.setenv("GREETING__SENDER__ADDRESS", "ops@greeting.example")

    assert load_greeting().sender.address == "ops@greeting.example"


def test_an_environment_variable_gets_the_declared_type(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GREETING__REPEAT", "3")

    assert load_greeting().repeat == 3


def test_environment_variables_can_choose_another_variant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GREETING__CHANNEL__KIND", "email")
    monkeypatch.setenv("GREETING__CHANNEL__SERVER", "smtp.greeting.example")

    assert load_greeting().channel == EmailChannel(kind="email", server="smtp.greeting.example")


def test_the_keys_of_a_replaced_variant_stay_and_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    # Tables are merged key by key, so `server` of the email channel stays when another variant is chosen.
    # Put the variant without keys of its own in application.toml; a profile or the environment adds the other.
    monkeypatch.setenv(PROFILE_VARIABLE, "email")
    monkeypatch.setenv("GREETING__CHANNEL__KIND", "log")

    with pytest.raises(ValidationError, match=r"greeting\.channel\.log\.server"):
        load_greeting()


def test_an_unknown_key_in_a_file_stops_the_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PROFILE_VARIABLE, "typo")

    with pytest.raises(ValidationError, match=r"greeting\.txt"):
        load_greeting()


def test_an_unknown_environment_variable_of_a_section_stops_the_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GREETING__SENDER__NAEM", "a typo of name")

    with pytest.raises(ValidationError, match=r"greeting\.sender\.naem"):
        load_greeting()


def test_a_value_of_the_wrong_type_stops_the_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GREETING__REPEAT", "often")

    with pytest.raises(ValidationError, match=r"greeting\.repeat"):
        load_greeting()


def test_a_missing_value_stops_the_start() -> None:
    with pytest.raises(ValidationError, match="farewell"):
        load_configuration(ServerProperties, GreetingProperties, FarewellProperties, package=SAMPLE)


def test_a_table_no_section_claims_stops_the_start() -> None:
    # application.toml has [server] and [greeting]; a table nobody reads is a typo or a forgotten section.
    with pytest.raises(ValidationError, match="server"):
        load_configuration(GreetingProperties, package=SAMPLE)


def test_a_dotenv_file_is_not_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("GREETING__TEXT=from a dotenv file\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert load_greeting().text == "Hello"


def test_without_application_toml_the_start_fails() -> None:
    with pytest.raises(ConfigurationFileNotFoundError, match=r"tests\.configuration\.without_files has no"):
        load_configuration(package="tests.configuration.without_files")


def test_an_unknown_profile_stops_the_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PROFILE_VARIABLE, "staging")

    with pytest.raises(ConfigurationFileNotFoundError, match=r"no application-staging\.toml"):
        load_greeting()


@pytest.mark.parametrize("profile", ["../sample_service/application", "Local", "local.toml"])
def test_a_profile_is_one_lowercase_name(monkeypatch: pytest.MonkeyPatch, profile: str) -> None:
    monkeypatch.setenv(PROFILE_VARIABLE, profile)

    with pytest.raises(ConfigurationFileNotFoundError, match="a profile is one lowercase name"):
        load_greeting()


def test_an_empty_profile_variable_activates_no_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PROFILE_VARIABLE, "")

    assert load_sample().profile is None


def test_no_sections_is_a_valid_configuration() -> None:
    configuration = load_configuration(package="tests.configuration.empty_service")

    assert dict(configuration.sections) == {}


def test_a_password_never_shows() -> None:
    sections = (ServerProperties, DatabaseProperties, CacheProperties)
    database = load_configuration(*sections, package="tests.configuration.infrastructure_service").get(
        DatabaseProperties
    )

    assert "test-only-password" not in repr(database)
    assert database.password.get_secret_value() == "test-only-password"


def test_a_section_cannot_be_changed_after_loading() -> None:
    greeting = load_greeting()

    with pytest.raises(ValidationError, match="frozen"):
        greeting.text = "Goodbye"
