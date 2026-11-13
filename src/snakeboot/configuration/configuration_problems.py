from collections.abc import Sequence
from dataclasses import dataclass, field
from types import NoneType, UnionType
from typing import Final, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo
from pydantic_core import ErrorDetails

from snakeboot.configuration.configuration_errors import ConfigurationFileNotFoundError
from snakeboot.configuration.properties_rules import models_named_by
from snakeboot.configuration.section_prefix import NESTED_DELIMITER

PROBLEMS_ATTRIBUTE: Final = "__configuration_problems__"
"""Where `describe_problems` keeps its sentences on pydantic's ValidationError, for `configuration_problems`."""

_VALUE_ERROR: Final = "Value error, "
"""What pydantic puts before the message of a ValueError that a validator raised."""


def configuration_problems(error: BaseException) -> tuple[str, ...]:
    """Returns what is wrong with the configuration that `error` stopped, one sentence per problem, or nothing.

    Each sentence names the key and where it is set, as whoever deploys the application sets it:
    `database.password is missing: set it in application.toml or DATABASE__PASSWORD`. A missing file is one problem;
    the ValidationError of a configuration that was read has one per error pydantic found; any other error, a bug
    in a section or in a component, is no problem of the configuration and has none.
    """
    if isinstance(error, ConfigurationFileNotFoundError):
        return (str(error),)
    problems: tuple[str, ...] = getattr(error, PROBLEMS_ATTRIBUTE, ())
    return problems


def describe_problems(error: ValidationError, root: type[BaseModel], files: Sequence[str]) -> None:
    """Puts one sentence per error of `error` on it, as a note and for `configuration_problems`.

    `root` is the model that was read, its fields the sections; `files` the names of the files that were read. The
    sentences show no value, since a value may be a secret.
    """
    where = ", ".join(files)
    problems = tuple(_problem_of(details, root, where) for details in error.errors(include_url=False))
    setattr(error, PROBLEMS_ATTRIBUTE, problems)
    for problem in problems:
        error.add_note(problem)


@dataclass(slots=True)
class _Key:
    """A key of the configuration as the files name it, `database.password`, and the variable that sets it."""

    names: list[str] = field(default_factory=list)
    variable_names: list[str] = field(default_factory=list)
    annotation: object = None
    in_a_list: bool = False

    def add(self, name: str, annotation: object) -> None:
        self.names.append(name)
        if not self.in_a_list:
            self.variable_names.append(name)
        self.annotation = annotation

    def index(self, position: int) -> None:
        # One variable sets a whole list, in JSON: the keys inside an item have none of their own.
        if self.names:
            self.names[-1] += f"[{position}]"
        self.in_a_list = True

    @property
    def table(self) -> bool:
        return not self.in_a_list and _names_a_table(self.annotation)

    @property
    def shown(self) -> str:
        name = ".".join(self.names)
        return f"[{name}]" if self.table else name

    @property
    def variable(self) -> str:
        variable = NESTED_DELIMITER.join(name.upper() for name in self.variable_names)
        return f"{variable}{NESTED_DELIMITER}<KEY>" if self.table else variable


def _problem_of(details: ErrorDetails, root: type[BaseModel], where: str) -> str:
    location = details["loc"]
    if details["type"] == "extra_forbidden":
        key = _key_at(location[:-1], root)
        key.add(str(location[-1]), None)
        return _unknown(key, where)
    key = _key_at(location, root)
    if details["type"] == "missing":
        return _missing(key, where)
    reason = details["msg"].removeprefix(_VALUE_ERROR).rstrip(".")
    return f"{key.shown} is invalid ({reason}): correct it in {where} or {key.variable}"


def _missing(key: _Key, where: str) -> str:
    if key.table:
        return f"{key.shown} is missing: add the table to {where}, or set its keys as {key.variable}"
    return f"{key.shown} is missing: set it in {where} or {key.variable}"


def _unknown(key: _Key, where: str) -> str:
    if len(key.names) == 1:
        name = key.names[0]
        return (
            f"[{name}] is a table that no section claims: remove it from {where}, or declare its section with "
            f'@configuration_properties("{name}")'
        )
    return f"{key.shown} is unknown: remove it from {where} or {key.variable}"


def _key_at(location: Sequence[int | str], root: type[BaseModel]) -> _Key:
    """Follows the fields of `root` along pydantic's location of an error, leaving out the members of a union."""
    key = _Key()
    models: tuple[type[BaseModel], ...] = (root,)
    member_named_next = False
    for element in location:
        if isinstance(element, int):
            key.index(element)
        elif member_named_next:
            # pydantic names the member of a union of tables, `log` of `channel`, before the keys inside it.
            member_named_next = False
        elif (found := _field_named(element, models)) is not None:
            key.add(element, found.annotation)
            models = tuple(models_named_by(found.annotation))
            member_named_next = len(models) > 1
    return key


def _field_named(name: str, models: tuple[type[BaseModel], ...]) -> FieldInfo | None:
    return next((model.model_fields[name] for model in models if name in model.model_fields), None)


def _names_a_table(annotation: object) -> bool:
    # A model, or a union of models that may be None: not a list of them, nor a value.
    is_union = isinstance(annotation, UnionType) or get_origin(annotation) is Union
    members = [member for member in (get_args(annotation) if is_union else (annotation,)) if member is not NoneType]
    return bool(members) and all(isinstance(member, type) and issubclass(member, BaseModel) for member in members)
