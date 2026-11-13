"""Only `SECTION__KEY` sets a key: a variable named like the section itself, which a host may set, is no table."""

import pytest
from pydantic import ValidationError

from snakeboot.configuration import (
    CacheProperties,
    DatabaseProperties,
    ServerProperties,
    begin_configuration,
    load_configuration,
)
from tests.configuration.ai_agent_service.ai_agent_properties import AiAgentProperties

AI_AGENT_SERVICE = "tests.configuration.ai_agent_service"
SAMPLE = "tests.configuration.sample_service"
EMPTY_SERVICE = "tests.configuration.empty_service"


def load_ai_agent() -> AiAgentProperties:
    return load_configuration(AiAgentProperties, package=AI_AGENT_SERVICE).get(AiAgentProperties)


def test_a_variable_named_like_a_section_leaves_the_table_as_the_files_have_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_AGENT", "claude-code_2-1-321_agent")  # what coding agents set: no JSON

    assert load_ai_agent() == AiAgentProperties(model="claude", temperature=0.2)


def test_a_variable_named_like_a_section_is_left_out_when_it_is_json_too(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_AGENT", '{"model": "gpt", "temperature": 1.0}')

    assert load_ai_agent() == AiAgentProperties(model="claude", temperature=0.2)


def test_a_key_of_the_section_still_overrides_the_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_AGENT", "claude-code_2-1-321_agent")
    monkeypatch.setenv("AI_AGENT__MODEL", "x")

    assert load_ai_agent() == AiAgentProperties(model="x", temperature=0.2)


@pytest.mark.parametrize("value", ["postgres", "{}", '{"file": "x.sqlite3"}'])
def test_an_optional_section_stays_absent_next_to_a_variable_of_its_name(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("DATABASE", value)
    monkeypatch.setenv("CACHE", value)

    configuration = begin_configuration(
        ServerProperties, optional=(DatabaseProperties, CacheProperties), package=SAMPLE
    )

    assert set(configuration.sections) == {ServerProperties}


def test_a_variable_named_like_a_required_section_does_not_stand_in_for_its_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SERVER", '{"host": "0.0.0.0"}')

    with pytest.raises(ValidationError) as stopped:
        load_configuration(ServerProperties, package=EMPTY_SERVICE)  # application.toml has no [server]

    assert [(error["loc"], error["type"]) for error in stopped.value.errors()] == [(("server",), "missing")]
