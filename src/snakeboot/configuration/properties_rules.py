from collections.abc import Iterator
from typing import get_args, get_origin

from pydantic import BaseModel

from snakeboot.configuration.configuration_errors import InvalidConfigurationPropertiesError
from snakeboot.configuration.section import Section


def refuse_loose_models(section: type[Section]) -> None:
    """Refuses a section whose model, or a model nested in it, breaks one of two rules.

    Every model extends `Section` and keeps its `model_config`: a model that ignores unknown keys turns a typo
    into a setting that silently does nothing, and a mutable model lets a value change after start-up.

    No field has a default: a default in code is a second place for a value next to application.toml.
    """
    for model in _models_in(section):
        _refuse_model_outside_section(model)
        _refuse_reopened_model_config(model)
        _refuse_defaults(model)


def _models_in(section: type[BaseModel]) -> list[type[BaseModel]]:
    found: dict[type[BaseModel], None] = {}
    waiting = [section]
    while waiting:
        model = waiting.pop()
        if model not in found:
            found[model] = None
            for field in model.model_fields.values():
                waiting.extend(_models_named_by(field.annotation))
    return list(found)


def _models_named_by(annotation: object) -> Iterator[type[BaseModel]]:
    # `tuple[Llm, ...]`, `Llm | None` and `Annotated[Llm | Extractive, ...]` all name models in their arguments.
    if get_origin(annotation) is None and isinstance(annotation, type) and issubclass(annotation, BaseModel):
        yield annotation
        return
    for argument in get_args(annotation):
        yield from _models_named_by(argument)


def _refuse_model_outside_section(model: type[BaseModel]) -> None:
    # Checked by class, not by model_config alone: the contract is the base class, whose rules may grow.
    if not issubclass(model, Section):
        raise InvalidConfigurationPropertiesError(
            f"{model.__name__} must extend Section, like every configuration model and every table nested in one: "
            "an unknown key is a typo that must stop the start, and the configuration does not change while running."
        )


def _refuse_reopened_model_config(model: type[BaseModel]) -> None:
    if model.model_config.get("extra") != "forbid" or model.model_config.get("frozen") is not True:
        raise InvalidConfigurationPropertiesError(
            f"{model.__name__} changes the model_config of Section: keep extra='forbid' and frozen=True, so a typo "
            "stops the start and the configuration does not change while running."
        )


def _refuse_defaults(model: type[BaseModel]) -> None:
    for name, field in model.model_fields.items():
        if not field.is_required():
            raise InvalidConfigurationPropertiesError(
                f"{model.__name__}.{name} has a default in code. Give it its value in application.toml or a "
                "profile: every configuration value is written in one place."
            )
