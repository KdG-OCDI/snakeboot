from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Final

from snakeboot.security.principal import Principal

_SIGNED_IN: Final[ContextVar[Principal | None]] = ContextVar("snakeboot-principal", default=None)


class SecurityContext:
    """Who the work in hand is done for, like Spring's `SecurityContextHolder`.

    The web binding signs the principal of a call in while its endpoint runs, so code that is not handed the
    `Principal` can still ask: the auditing of `CreatedBy` and `LastModifiedBy` does. Work outside a call (a scheduled
    method, a message, a command) runs for nobody, unless it signs a principal in itself:

        with SecurityContext.signed_in(Principal("nightly-report")):
            self._report.execute()

    The principal lives in a context variable, so each thread, and each task of an event loop, has its own.
    """

    @classmethod
    def current(cls) -> Principal | None:
        """Returns the principal the work in hand is done for, or None."""
        return _SIGNED_IN.get()

    @classmethod
    @contextmanager
    def signed_in(cls, principal: Principal) -> Iterator[Principal]:
        """Does the work of the block for `principal`, and for whoever it was before afterwards."""
        token = _SIGNED_IN.set(principal)
        try:
            yield principal
        finally:
            _SIGNED_IN.reset(token)
