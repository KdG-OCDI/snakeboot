import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from snakeboot.data.data_errors import InvalidRepositoryError


class Operator(StrEnum):
    """How a condition compares a field with its arguments, like the keywords of Spring Data's method names."""

    EQUALS = "equals"
    NOT = "not"
    LESS_THAN = "less_than"
    LESS_THAN_EQUAL = "less_than_equal"
    GREATER_THAN = "greater_than"
    GREATER_THAN_EQUAL = "greater_than_equal"
    BETWEEN = "between"
    IN = "in"
    NOT_IN = "not_in"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    LIKE = "like"
    NOT_LIKE = "not_like"
    STARTING_WITH = "starting_with"
    ENDING_WITH = "ending_with"
    CONTAINING = "containing"
    TRUE = "true"
    FALSE = "false"

    @property
    def arity(self) -> int:
        """How many arguments of the method the condition takes."""
        if self in {Operator.IS_NULL, Operator.IS_NOT_NULL, Operator.TRUE, Operator.FALSE}:
            return 0
        return 2 if self is Operator.BETWEEN else 1


_KEYWORDS: Final = {
    "": Operator.EQUALS,
    "is": Operator.EQUALS,
    "equals": Operator.EQUALS,
    "not": Operator.NOT,
    "is_not": Operator.NOT,
    "less_than": Operator.LESS_THAN,
    "before": Operator.LESS_THAN,
    "less_than_equal": Operator.LESS_THAN_EQUAL,
    "greater_than": Operator.GREATER_THAN,
    "after": Operator.GREATER_THAN,
    "greater_than_equal": Operator.GREATER_THAN_EQUAL,
    "between": Operator.BETWEEN,
    "in": Operator.IN,
    "not_in": Operator.NOT_IN,
    "is_null": Operator.IS_NULL,
    "null": Operator.IS_NULL,
    "is_not_null": Operator.IS_NOT_NULL,
    "not_null": Operator.IS_NOT_NULL,
    "like": Operator.LIKE,
    "not_like": Operator.NOT_LIKE,
    "starting_with": Operator.STARTING_WITH,
    "ending_with": Operator.ENDING_WITH,
    "containing": Operator.CONTAINING,
    "true": Operator.TRUE,
    "is_true": Operator.TRUE,
    "false": Operator.FALSE,
    "is_false": Operator.FALSE,
}
"""Every keyword after a field, as snake_case words; none is the field compared for equality."""


class Action(StrEnum):
    """What a derived query does with the rows its conditions select."""

    FIND = "find"
    COUNT = "count"
    EXISTS = "exists"
    DELETE = "delete"


_ACTIONS: Final = {
    "find": Action.FIND,
    "read": Action.FIND,
    "get": Action.FIND,
    "query": Action.FIND,
    "count": Action.COUNT,
    "exists": Action.EXISTS,
    "delete": Action.DELETE,
    "remove": Action.DELETE,
}

_SUBJECT: Final = re.compile(
    r"(?P<action>find|read|get|query|count|exists|delete|remove)(?:_all)?"
    r"(?:_(?:first|top)(?:_?(?P<limit>\d+))?(?P<limited>))?_by(?:_(?P<predicate>.+))?"
)


@dataclass(frozen=True, slots=True)
class Condition:
    """One comparison of a field, such as `status` or `join_deadline less_than_equal`."""

    field: str
    operator: Operator


@dataclass(frozen=True, slots=True)
class Ordering:
    """One key of the order: a field, ascending or descending."""

    field: str
    descending: bool


@dataclass(frozen=True, slots=True)
class DerivedQuery:
    """What a repository method's name asks for, like a Spring Data query derived from `findByStatusOrderByIdAsc`.

    `alternatives` are joined by `or`, the conditions within one by `and`; no alternative selects every row.
    """

    action: Action
    alternatives: tuple[tuple[Condition, ...], ...]
    ordering: tuple[Ordering, ...]
    limit: int | None

    @property
    def arity(self) -> int:
        """How many arguments the conditions take, in the order of the name."""
        return sum(condition.operator.arity for conditions in self.alternatives for condition in conditions)


def derive_query(method_name: str, fields: Sequence[str]) -> DerivedQuery:
    """Reads the query that `method_name` asks for, on an entity with `fields`; a name it cannot read stops the start.

    find_by_status_and_join_deadline_less_than_equal     status = ? and join_deadline <= ?
    find_by_game_id_order_by_played_at_asc_id_asc        game_id = ? order by played_at, id
    find_first_by_order_by_id_desc                       the one with the highest id
    count_by_game_type, exists_by_scope, delete_by_scope
    """
    subject = _SUBJECT.fullmatch(method_name)
    if subject is None:
        raise InvalidRepositoryError(
            f"{method_name}: a derived query starts with find_by, count_by, exists_by or delete_by "
            "(find_all_by, find_first_by and find_top_<n>_by too)."
        )
    limit = int(subject["limit"]) if subject["limit"] else (1 if subject["limited"] is not None else None)
    criteria, ordering = _split_order(subject["predicate"] or "")
    return DerivedQuery(
        action=_ACTIONS[subject["action"]],
        alternatives=_alternatives(method_name, criteria, fields),
        ordering=_ordering(method_name, ordering, fields),
        limit=limit,
    )


def _split_order(predicate: str) -> tuple[str, str]:
    if predicate.startswith("order_by_"):
        return "", predicate.removeprefix("order_by_")
    criteria, separator, ordering = predicate.partition("_order_by_")
    return criteria, ordering if separator else ""


def _alternatives(method_name: str, criteria: str, fields: Sequence[str]) -> tuple[tuple[Condition, ...], ...]:
    if not criteria:
        return ()
    parsed = next(_parse_alternatives(criteria.split("_"), _field_words(fields)), None)
    if parsed is None:
        raise InvalidRepositoryError(
            f"{method_name}: {criteria!r} is no condition on the fields {sorted(fields)}, joined by _and_ and _or_."
        )
    return parsed


def _parse_alternatives(words: list[str], fields: list[tuple[str, ...]]) -> Iterator[tuple[tuple[Condition, ...], ...]]:
    for conditions, rest in _parse_conjunction(words, fields):
        if not rest:
            yield (conditions,)
        elif rest[0] == "or":
            for others in _parse_alternatives(rest[1:], fields):
                yield (conditions, *others)


def _parse_conjunction(
    words: list[str], fields: list[tuple[str, ...]]
) -> Iterator[tuple[tuple[Condition, ...], list[str]]]:
    for condition, rest in _parse_condition(words, fields):
        yield (condition,), rest
        if rest and rest[0] == "and":
            for conditions, remainder in _parse_conjunction(rest[1:], fields):
                yield (condition, *conditions), remainder


def _parse_condition(words: list[str], fields: list[tuple[str, ...]]) -> Iterator[tuple[Condition, list[str]]]:
    for field in fields:
        if tuple(words[: len(field)]) != field:
            continue
        after_field = words[len(field) :]
        for keyword, operator in _KEYWORDS.items():
            keyword_words = keyword.split("_") if keyword else []
            if after_field[: len(keyword_words)] == keyword_words:
                yield Condition("_".join(field), operator), after_field[len(keyword_words) :]


def _ordering(method_name: str, ordering: str, fields: Sequence[str]) -> tuple[Ordering, ...]:
    words, keys = ordering.split("_") if ordering else [], []
    field_words = _field_words(fields)
    while words:
        field = next((field for field in field_words if tuple(words[: len(field)]) == field), None)
        if field is None:
            raise InvalidRepositoryError(f"{method_name}: the order {ordering!r} names a field the entity lacks.")
        words = words[len(field) :]
        descending = bool(words) and words[0] == "desc"
        if words and words[0] in {"asc", "desc"}:
            words = words[1:]
        keys.append(Ordering("_".join(field), descending))
    return tuple(keys)


def _field_words(fields: Sequence[str]) -> list[tuple[str, ...]]:
    # The longest field first: `played_at` before `played`.
    return sorted((tuple(field.split("_")) for field in fields), key=len, reverse=True)
