"""A consumer of a stream claims each event once, and starts over when its stream turns out to be a new one."""

import pytest

from snakeboot.events import InMemoryStreamOffsets, StreamEvent, StreamPosition

CONSUMER = "myapp.Projection.on_event"


def claimed(offsets: InMemoryStreamOffsets, event: StreamEvent, generation: int = 0) -> bool:
    with offsets.claiming(CONSUMER, event, generation=generation) as new:
        return new


def test_a_consumer_that_handled_nothing_has_no_last_event() -> None:
    offsets = InMemoryStreamOffsets()

    assert offsets.position(CONSUMER) == StreamPosition()
    assert offsets.last_handled(CONSUMER) is None


def test_an_event_is_claimed_once_and_an_earlier_one_never() -> None:
    offsets = InMemoryStreamOffsets()

    outcomes = [claimed(offsets, StreamEvent(offset)) for offset in (5, 5, 4, 6)]

    assert outcomes == [True, False, False, True]
    assert offsets.last_handled(CONSUMER) == 6


def test_an_event_whose_handling_fails_is_not_claimed() -> None:
    offsets = InMemoryStreamOffsets()

    with pytest.raises(RuntimeError), offsets.claiming(CONSUMER, StreamEvent(5)):
        raise RuntimeError("The projection fails.")

    assert offsets.last_handled(CONSUMER) is None


def test_the_fingerprint_tells_an_event_from_another_at_the_same_offset() -> None:
    event = StreamEvent.of(7, b'{"auction_id": "a1"}', "publication-1")

    assert event == StreamEvent.of(7, b'{"auction_id": "a1"}', "publication-1")
    assert event != StreamEvent.of(7, b'{"auction_id": "a2"}', "publication-1")
    assert event != StreamEvent.of(7, b'{"auction_id": "a1"}', "publication-2")
    assert event != StreamEvent.of(7, b'{"auction_id": "a1"}')


def test_of_two_processes_that_find_a_new_stream_one_starts_over() -> None:
    offsets = InMemoryStreamOffsets()
    claimed(offsets, StreamEvent(1000, "old"))
    seen = offsets.position(CONSUMER)

    assert [offsets.start_over(CONSUMER, seen), offsets.start_over(CONSUMER, seen)] == [True, False]
    assert offsets.position(CONSUMER) == StreamPosition(generation=1)


def test_a_consumer_that_moved_on_meanwhile_does_not_start_over() -> None:
    offsets = InMemoryStreamOffsets()
    claimed(offsets, StreamEvent(1000, "old"))
    seen = offsets.position(CONSUMER)
    claimed(offsets, StreamEvent(1001, "old"))

    assert not offsets.start_over(CONSUMER, seen)
    assert offsets.last_handled(CONSUMER) == 1001


def test_a_claim_of_the_stream_that_is_gone_does_not_move_the_new_one() -> None:
    offsets = InMemoryStreamOffsets()
    claimed(offsets, StreamEvent(1000, "old"))
    offsets.start_over(CONSUMER, offsets.position(CONSUMER))

    of_the_old_stream = claimed(offsets, StreamEvent(1001, "old"))  # a process that had it in hand still
    of_the_new_stream = claimed(offsets, StreamEvent(0, "new"), generation=1)

    assert (of_the_old_stream, of_the_new_stream) == (False, True)
    assert offsets.position(CONSUMER) == StreamPosition(1, StreamEvent(0, "new"))
