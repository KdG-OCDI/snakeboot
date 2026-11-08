from collections.abc import Callable
from typing import Any, Final

from snakeboot.data.repository_operations import LockMode, NativeQuery

LOCK_ATTRIBUTE: Final = "__snakeboot_lock__"
QUERY_ATTRIBUTE: Final = "__snakeboot_query__"


def lock[F: Callable[..., Any]](mode: LockMode) -> Callable[[F], F]:
    """Locks the rows a repository method reads until the transaction ends, like Spring Data's `@Lock`.

        @lock(LockMode.PESSIMISTIC_WRITE)
        def find_by_status_and_join_deadline_less_than_equal(self, status: str, deadline: datetime) -> list[Game]: ...

    Use it in a `@transactional` use case: the lock holds until its transaction ends.
    """

    def mark(method: F) -> F:
        setattr(method, LOCK_ATTRIBUTE, mode)
        return method

    return mark


def query[F: Callable[..., Any]](sql: str, *, modifying: bool = False) -> Callable[[F], F]:
    """Gives a repository method its SQL instead of deriving it from its name, like Spring Data's native `@Query`.

        @query("SELECT scope, source, text, embedding <=> CAST(:embedding AS vector) AS distance "
               "FROM chatbot_knowledge_chunk WHERE scope = ANY(:scopes) ORDER BY distance LIMIT :limit")
        def search(self, embedding: list[float], scopes: list[str], limit: int) -> list[RetrievedRow]: ...

    The parameters are named in the SQL as `:name`; a list is passed as one array. The return annotation says what
    one row becomes: an entity, a scalar (`int`, `str`, ...) from the first column, or any other class made from the
    columns by name. `modifying=True`, like `@Modifying`, runs an UPDATE or a DELETE and returns how many rows it
    changed (`-> int`, or `-> None`).
    """

    def mark(method: F) -> F:
        setattr(method, QUERY_ATTRIBUTE, NativeQuery(sql, modifying=modifying, result_type=None))
        return method

    return mark
