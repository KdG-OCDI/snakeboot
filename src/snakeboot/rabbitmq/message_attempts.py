"""How a listener tries a message: again after a failure that may pass, like Spring Boot's listener retry."""

import contextvars
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from functools import partial
from typing import Any

from snakeboot.rabbitmq.listener_timing import ListenerTiming
from snakeboot.rabbitmq.message_conversion import MessageConversionError
from snakeboot.rabbitmq.rabbit_listener import RejectAndDontRequeueError

logger = logging.getLogger(__name__)


class Attempted(Enum):
    """How the attempts at a message ended."""

    DONE = "handled"
    REFUSED = "refused for good: unreadable, or `RejectAndDontRequeueError`"
    EXHAUSTED = "failed on every attempt"
    STOPPED = "told to stop between two attempts"


@dataclass(frozen=True, slots=True)
class MessageAttempts:
    """Tries a message as often and as patiently as `timing` says, until `stopping` is set.

    A body the listener cannot read, or a `RejectAndDontRequeueError`, ends the attempts at once: the message can
    never succeed. Any other exception is a failure that may pass, such as a database that is down: after a pause
    that grows by `retry_multiplier`, the message is tried again, `attempts` times in all. During an attempt and
    during a pause the connection keeps answering the broker's heartbeats, so neither a long handling nor a long
    back-off loses it.
    """

    listener: str
    timing: ListenerTiming
    stopping: threading.Event

    def run(self, handle: Callable[[], None], connection: Any, message: str) -> Attempted:
        """Tries `handle` on `connection`; `message` names the message in the log."""
        attempted = partial(handled_beside, connection, handle, poll_seconds=self.timing.poll_seconds)
        pauses = self.timing.retry_pauses()
        for attempt in range(1, self.timing.attempts + 1):
            pause = next(pauses)
            if (outcome := self._attempt(attempted, message, attempt=attempt, pause=pause)) is not None:
                return outcome
            if paused_until_stopping(connection, pause, stopping=self.stopping, poll_seconds=self.timing.poll_seconds):
                return Attempted.STOPPED
        return Attempted.EXHAUSTED

    def _attempt(self, handle: Callable[[], None], message: str, *, attempt: int, pause: float) -> Attempted | None:
        attempts = self.timing.attempts
        try:
            handle()
        except (MessageConversionError, RejectAndDontRequeueError) as error:
            logger.warning("%s refused %s for good: %r", self.listener, message, error)
            return Attempted.REFUSED
        except Exception:
            if attempt == attempts:
                logger.exception("%s failed on %s %s times", self.listener, message, attempts)
                return Attempted.EXHAUSTED
            logger.warning(
                "%s failed on %s (attempt %s of %s); it tries again in %s s",
                self.listener,
                message,
                attempt,
                attempts,
                pause,
                exc_info=True,
            )
            return None
        return Attempted.DONE


def handled_beside(connection: Any, handle: Callable[[], None], *, poll_seconds: float) -> None:
    """Runs `handle` on a thread of its own while `connection` keeps answering the broker's heartbeats, and raises
    what `handle` raised.

    pika's `BlockingConnection` answers heartbeats only while its own thread works on the connection. A method that
    handled a message on that thread for longer than the heartbeat timeout, such as one that waits minutes for a
    language model, would lose the connection, and RabbitMQ would hand the message to another consumer while the
    first still works on it. So the listener's thread waits for the handling in slices of `poll_seconds` and lets the
    connection answer the broker in between; pika hands it no other message meanwhile, as it never calls a consumer
    from within a consumer. The handling sees the trace and every other context variable of the listener's thread.
    """
    failures: list[BaseException] = []
    context = contextvars.copy_context()

    def attempt() -> None:
        try:
            context.run(handle)
        except BaseException as error:  # noqa: BLE001  # reason: the listener's thread raises it again below
            failures.append(error)

    handling = threading.Thread(target=attempt, name=f"{threading.current_thread().name}-handling", daemon=True)
    handling.start()
    handling.join(poll_seconds)
    while handling.is_alive():
        connection.sleep(0)  # answers the broker, and delivers nothing else to this listener meanwhile
        handling.join(poll_seconds)
    if failures:
        raise failures[0]


def paused_until_stopping(connection: Any, seconds: float, *, stopping: threading.Event, poll_seconds: float) -> bool:
    """Waits `seconds` before the next attempt, or until `stopping` is set, and tells whether it must stop.

    The connection sleeps instead of the thread, in slices, so it keeps answering the broker's heartbeats: the
    broker closes a connection that stays silent longer than the heartbeat timeout and puts the message back on
    the queue, where its attempts start over.
    """
    deadline = time.monotonic() + seconds
    while not stopping.is_set() and (left := deadline - time.monotonic()) > 0:
        connection.sleep(min(left, poll_seconds))
    return stopping.is_set()
