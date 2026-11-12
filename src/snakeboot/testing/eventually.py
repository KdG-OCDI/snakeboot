import time
from collections.abc import Callable
from typing import Final

WITHIN_SECONDS: Final = 5.0
"""How long `eventually` keeps trying, unless the test says otherwise."""

EVERY_SECONDS: Final = 0.05
"""How long `eventually` waits between two tries, unless the test says otherwise."""


def eventually[T](check: Callable[[], T], *, within: float = WITHIN_SECONDS, every: float = EVERY_SECONDS) -> T:
    """Calls `check` until it holds and returns what it returned, like Awaitility's `await().untilAsserted(...)`.

        eventually(lambda: client.get(f"/api/auctions/{auction_id}").json()["status"] == "CLOSED")

        def the_invoice_is_issued() -> None:
            assert invoices.count() == 1

        eventually(the_invoice_is_issued, within=2)

    `check` holds when it returns anything but `False` without raising an `AssertionError`: a predicate or a function
    of asserts. Any other exception stops at once, since waiting cannot mend it. For code on a thread of its own: the
    scheduler or the listeners with the lifecycle running, or a `LocalServer`. After `within` seconds the last
    failure is raised.
    """
    deadline = time.monotonic() + within
    while True:
        try:
            result = check()
        except AssertionError:
            if time.monotonic() >= deadline:
                raise
        else:
            if result is not False:
                return result
            if time.monotonic() >= deadline:
                raise AssertionError(f"{check!r} did not hold within {within} seconds.")
        time.sleep(every)
