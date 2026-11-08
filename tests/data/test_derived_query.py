"""A repository method's name says its query, as in Spring Data; a name snakeboot cannot read stops the start."""

import pytest

from snakeboot.data import Action, Condition, InvalidRepositoryError, Operator, Ordering, derive_query

FIELDS = ("game_id", "status", "join_deadline", "played_at", "played", "id", "scope", "published_at")


def test_find_by_compares_a_field_for_equality() -> None:
    query = derive_query("find_by_status", FIELDS)

    assert (query.action, query.alternatives) == (Action.FIND, ((Condition("status", Operator.EQUALS),),))


def test_conditions_are_joined_by_and_and_or() -> None:
    query = derive_query("find_by_status_and_scope_or_game_id", FIELDS)

    assert query.alternatives == (
        (Condition("status", Operator.EQUALS), Condition("scope", Operator.EQUALS)),
        (Condition("game_id", Operator.EQUALS),),
    )


@pytest.mark.parametrize(
    ("keyword", "operator"),
    [
        ("less_than_equal", Operator.LESS_THAN_EQUAL),
        ("less_than", Operator.LESS_THAN),
        ("before", Operator.LESS_THAN),
        ("greater_than_equal", Operator.GREATER_THAN_EQUAL),
        ("after", Operator.GREATER_THAN),
        ("between", Operator.BETWEEN),
        ("in", Operator.IN),
        ("not_in", Operator.NOT_IN),
        ("is_null", Operator.IS_NULL),
        ("is_not_null", Operator.IS_NOT_NULL),
        ("not", Operator.NOT),
        ("starting_with", Operator.STARTING_WITH),
        ("containing", Operator.CONTAINING),
    ],
)
def test_a_keyword_after_a_field_says_how_to_compare(keyword: str, operator: Operator) -> None:
    query = derive_query(f"find_by_join_deadline_{keyword}", FIELDS)

    assert query.alternatives == ((Condition("join_deadline", operator),),)


def test_the_longest_field_wins_over_a_shorter_one_with_the_same_start() -> None:
    query = derive_query("find_by_played_at_before", FIELDS)

    assert query.alternatives == ((Condition("played_at", Operator.LESS_THAN),),)


def test_order_by_sorts_by_one_field_after_another() -> None:
    query = derive_query("find_by_game_id_order_by_played_at_asc_id_desc", FIELDS)

    assert query.ordering == (Ordering("played_at", descending=False), Ordering("id", descending=True))


def test_an_order_without_a_direction_is_ascending() -> None:
    assert derive_query("find_all_by_order_by_id", FIELDS).ordering == (Ordering("id", descending=False),)


def test_first_and_top_limit_the_results() -> None:
    assert derive_query("find_first_by_order_by_id_desc", FIELDS).limit == 1
    assert derive_query("find_top_100_by_published_at_is_null_order_by_id_asc", FIELDS).limit == 100
    assert derive_query("find_by_status", FIELDS).limit is None


def test_find_all_by_without_conditions_selects_every_row() -> None:
    assert derive_query("find_all_by_order_by_id", FIELDS).alternatives == ()


@pytest.mark.parametrize(
    ("name", "action"),
    [("count_by_status", Action.COUNT), ("exists_by_scope", Action.EXISTS), ("delete_by_scope", Action.DELETE)],
)
def test_the_verb_says_what_the_query_does(name: str, action: Action) -> None:
    assert derive_query(name, FIELDS).action is action


def test_the_arity_counts_the_arguments_of_every_condition() -> None:
    assert derive_query("find_by_status_and_join_deadline_between_or_game_id_is_null", FIELDS).arity == 3


def test_a_name_without_a_verb_stops_the_start() -> None:
    with pytest.raises(InvalidRepositoryError, match="starts with find_by"):
        derive_query("games_waiting", FIELDS)


def test_a_field_the_entity_lacks_stops_the_start() -> None:
    with pytest.raises(InvalidRepositoryError, match="no condition on the fields"):
        derive_query("find_by_colour", FIELDS)


def test_an_order_by_a_field_the_entity_lacks_stops_the_start() -> None:
    with pytest.raises(InvalidRepositoryError, match="names a field the entity lacks"):
        derive_query("find_by_status_order_by_colour_asc", FIELDS)
