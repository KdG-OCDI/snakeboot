import threading
from collections.abc import Iterator


class PublishedEvents:
    """Every event the application published during a test, in order, like Spring's `ApplicationEvents`.

        @application_test
        def test_closing_names_the_winner(client: Autowired[RestClient], events: Autowired[PublishedEvents]) -> None:
            close(client, auction_id)

            [closed] = events.of_type(AuctionClosed)
            assert closed.winner == "bob"

    Like Spring Modulith's `PublishedEvents`, it shows what one context tells the others without a listener of the
    test's own. An event counts once it is published, whether or not its transaction commits afterwards.
    """

    def __init__(self) -> None:
        self._events: list[object] = []
        self._lock = threading.Lock()

    def record(self, event: object) -> None:
        """Adds `event`: the application of a test calls it for every event it publishes."""
        with self._lock:
            self._events.append(event)

    def of_type[E](self, event_type: type[E]) -> list[E]:
        """Returns the events of `event_type`, its subclasses included, in the order they were published."""
        with self._lock:
            return [event for event in self._events if isinstance(event, event_type)]

    def clear(self) -> None:
        """Forgets the events so far, like `ApplicationEvents.clear()`, for a test that looks at a later step."""
        with self._lock:
            self._events.clear()

    def __iter__(self) -> Iterator[object]:
        """Returns the events so far, in the order they were published."""
        with self._lock:
            return iter(list(self._events))

    def __len__(self) -> int:
        """Returns how many events were published so far."""
        with self._lock:
            return len(self._events)
