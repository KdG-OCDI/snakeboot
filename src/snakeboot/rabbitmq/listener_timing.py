"""How patiently a listener waits: for a broker that is down, between two attempts at a message, and to stop."""

import math
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ListenerTiming:
    """How patiently a listener waits, like Spring AMQP's `recoveryInterval`, `shutdownTimeout` and Spring Boot's
    `spring.rabbitmq.listener.simple.retry.*`, whose defaults the retry takes."""

    reconnect_seconds: float = 5.0
    """Between attempts to reach a broker that is down."""
    attempts: int = 3
    """How often a message whose handling fails is tried before it is refused for good (`max-attempts`)."""
    retry_pause_seconds: float = 1.0
    """The pause after the first failed attempt, so a database that is down is not asked again at once
    (`initial-interval`)."""
    retry_multiplier: float = 1.0
    """How much longer each next pause is than the one before (`multiplier`): exponential back-off."""
    max_retry_pause_seconds: float = math.inf
    """The longest pause between two attempts (`max-interval`); no limit unless given, so a timing that only sets
    `retry_pause_seconds` keeps that pause, however long."""
    poll_seconds: float = 1.0
    """How long a listener waits for messages before it checks whether it must stop."""
    shutdown_seconds: float = 5.0
    """How long `stop` waits for a listener to finish the message in hand."""
    stream_check_seconds: float = 5.0
    """How long a stream listener waits for the message it handled last before it asks where its stream ends."""

    def retry_pauses(self) -> Iterator[float]:
        """Yields the pause after each failed attempt, in seconds: the first, then each `retry_multiplier` times
        longer, none longer than `max_retry_pause_seconds`."""
        pause = self.retry_pause_seconds
        while True:
            yield min(pause, self.max_retry_pause_seconds)
            pause = min(pause * self.retry_multiplier, self.max_retry_pause_seconds)
