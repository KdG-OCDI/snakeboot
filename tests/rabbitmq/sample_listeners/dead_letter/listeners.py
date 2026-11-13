"""A listener with a dead-letter queue, which keeps what it refuses."""

from pydantic import BaseModel

from snakeboot.rabbitmq import RejectAndDontRequeueError, rabbit_listener


class GameFinished(BaseModel):
    """Stands in for the message a game sends when it ends."""

    session_id: str


class GameFinishedListener:
    """Stands in for an inbound adapter whose refused messages a person looks at later."""

    def __init__(self) -> None:
        self.finished: list[str] = []
        self.attempts: dict[str, int] = {}

    @rabbit_listener(queue="platform.game-finished", exchange="games", routing_key="game.*.finished", dead_letter=True)
    def on_game_finished(self, message: GameFinished) -> None:
        """Ends a game. A session `refuse` breaks the rules, `crash` always meets a database that is down."""
        self.attempts[message.session_id] = self.attempts.get(message.session_id, 0) + 1
        if message.session_id == "refuse":
            raise RejectAndDontRequeueError("this game breaks the rules")
        if message.session_id == "crash":
            raise RuntimeError("the database is down")
        self.finished.append(message.session_id)
