"""A listener whose queue is bound with several routing keys, and a stream listener that handles several kinds."""

from pydantic import BaseModel

from snakeboot.rabbitmq import rabbit_listener, rabbit_stream_listener


class GameEvent(BaseModel):
    """Stands in for the facts a game platform publishes: which game, and what happened to it."""

    session_id: str
    what: str


class GameLifecycleListener:
    """Stands in for an inbound adapter that acts when a game starts or finishes, and on nothing else."""

    def __init__(self) -> None:
        self.received: list[GameEvent] = []

    @rabbit_listener(queue="arena.game-lifecycle", exchange="games", routing_key=("game.*.started", "game.*.finished"))
    def on_game_event(self, message: GameEvent) -> None:
        """Remembers the event; the body says which of the two it is."""
        self.received.append(message)


class GameResultProjection:
    """Stands in for a projection of the games that ended, whether finished or abandoned."""

    def __init__(self) -> None:
        self.results: list[GameEvent] = []

    @rabbit_stream_listener(
        stream="games.history", exchange="games", routing_key=("game.*.finished", "game.*.abandoned")
    )
    def on_result(self, message: GameEvent) -> None:
        """Keeps the result."""
        self.results.append(message)
